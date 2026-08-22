from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from .config import DEFAULT_CONFIG, AuditConfig
from .contracts import (
    AuditResult,
    CompanyFinancialPayload,
    FinancialPeriod,
    ModelResult,
    ModelStatus,
    Scalar,
)

_MONEY_FACTORS = {"ones": 1.0, "thousands": 1_000.0, "millions": 1_000_000.0}
_SHARE_FACTORS = {"shares": 1.0, "thousands": 1_000.0, "millions": 1_000_000.0}
_CYCLICAL_KEYWORDS = (
    "mining",
    "steel",
    "coal",
    "oil",
    "gas",
    "chemical",
    "shipping",
    "construction",
    "real estate",
    "materials",
)
_UTILITY_KEYWORDS = ("utility", "utilities", "power", "water")
_TECHNOLOGY_KEYWORDS = ("technology", "semiconductor", "hardware")


@dataclass(frozen=True, slots=True)
class _TtmMetric:
    value: float
    basis: str
    source_ids: tuple[str, ...]


class _Context:
    def __init__(self, payload: CompanyFinancialPayload, config: AuditConfig) -> None:
        self.payload = payload
        self.config = config
        self.money_factor = _MONEY_FACTORS[payload.monetary_unit]
        self.shares = (
            payload.market.shares_outstanding * _SHARE_FACTORS[payload.share_unit]
        )
        visible = [
            period
            for period in payload.periods
            if period.visible_at <= payload.as_of_date
        ]
        deduplicated: dict[date, FinancialPeriod] = {}
        for period in sorted(visible, key=lambda item: item.visible_at):
            deduplicated[period.period_end] = period
        self.periods = tuple(
            sorted(deduplicated.values(), key=lambda item: item.period_end)
        )
        self.excluded_period_count = len(payload.periods) - len(visible)

    @property
    def annual(self) -> tuple[FinancialPeriod, ...]:
        return tuple(
            period for period in self.periods if period.period_type == "annual"
        )

    @property
    def latest(self) -> FinancialPeriod | None:
        return self.periods[-1] if self.periods else None

    @property
    def industry_lower(self) -> str:
        return self.payload.industry.casefold()

    @property
    def is_utility(self) -> bool:
        return any(key in self.industry_lower for key in _UTILITY_KEYWORDS)

    @property
    def is_technology(self) -> bool:
        return any(key in self.industry_lower for key in _TECHNOLOGY_KEYWORDS)

    @property
    def is_cyclical(self) -> bool:
        return any(key in self.industry_lower for key in _CYCLICAL_KEYWORDS)

    def amount(self, period: FinancialPeriod, field: str) -> float | None:
        value = period.values.get(field)
        return value * self.money_factor if value is not None else None

    def latest_amount(self, field: str) -> float | None:
        if self.latest is None:
            return None
        return self.amount(self.latest, field)

    def source_ids(
        self, periods: Sequence[FinancialPeriod] | None = None
    ) -> tuple[str, ...]:
        selected = self.periods if periods is None else periods
        return tuple(
            sorted(
                {source_id for period in selected for source_id in period.source_ids}
                | set(self.payload.market.source_ids)
            )
        )

    def ttm(self, field: str) -> _TtmMetric | None:
        latest = self.latest
        if latest is None:
            return None
        latest_value = self.amount(latest, field)
        if latest_value is None:
            return None
        if latest.period_type == "annual":
            return _TtmMetric(latest_value, "latest_annual", latest.source_ids)

        prior_annual = next(
            (
                item
                for item in reversed(self.periods)
                if item.period_type == "annual" and item.period_end < latest.period_end
            ),
            None,
        )
        prior_comparable = next(
            (
                item
                for item in reversed(self.periods)
                if item.months == latest.months
                and item.period_end.year == latest.period_end.year - 1
            ),
            None,
        )
        if prior_annual is None or prior_comparable is None:
            return None
        annual_value = self.amount(prior_annual, field)
        comparable_value = self.amount(prior_comparable, field)
        if annual_value is None or comparable_value is None:
            return None
        return _TtmMetric(
            latest_value + annual_value - comparable_value,
            "interim_ttm_bridge",
            tuple(
                sorted(
                    set(latest.source_ids)
                    | set(prior_annual.source_ids)
                    | set(prior_comparable.source_ids)
                )
            ),
        )


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def _mean(values: Sequence[float]) -> float | None:
    return sum(values) / len(values) if values else None


def _cagr(
    start_value: float | None,
    end_value: float | None,
    start_date: date,
    end_date: date,
) -> float | None:
    if start_value is None or end_value is None:
        return None
    years = (end_date - start_date).days / 365.25
    if start_value <= 0 or end_value <= 0 or years < 0.5:
        return None
    return (end_value / start_value) ** (1.0 / years) - 1.0


def _status(metrics: Mapping[str, Scalar], gaps: Sequence[str]) -> ModelStatus:
    populated = sum(value is not None for value in metrics.values())
    if populated == 0:
        return "unavailable"
    return "partial" if gaps else "complete"


def _graham(context: _Context) -> ModelResult:
    gaps: list[str] = []
    warnings: list[str] = []
    annual = context.annual
    latest = context.latest
    earnings = [
        context.amount(period, "net_income")
        for period in annual[-context.config.earnings_stability_years :]
    ]
    known_earnings = [value for value in earnings if value is not None]
    stability = bool(known_earnings) and all(value >= 0 for value in known_earnings)
    if len(known_earnings) < context.config.earnings_stability_years:
        warnings.append(
            "Less than the configured earnings-stability history is visible."
        )

    latest_net_income = context.amount(annual[-1], "net_income") if annual else None
    latest_equity = context.latest_amount("equity")
    restated_eps = _ratio(latest_net_income, context.shares)
    book_value_per_share = _ratio(latest_equity, context.shares)
    graham_number: float | None = None
    if (
        restated_eps is not None
        and restated_eps > 0
        and book_value_per_share is not None
        and book_value_per_share > 0
    ):
        graham_number = math.sqrt(
            context.config.graham_coefficient * restated_eps * book_value_per_share
        )
    else:
        gaps.append(
            "Positive annual net income and equity are required for the Graham number."
        )

    safety_margin = (
        (graham_number - context.payload.market.price) / graham_number
        if graham_number is not None
        else None
    )
    current_assets = context.latest_amount("current_assets")
    current_liabilities = context.latest_amount("current_liabilities")
    total_liabilities = context.latest_amount("total_liabilities")
    total_assets = context.latest_amount("total_assets")
    ncav_per_share = (
        _ratio(current_assets - total_liabilities, context.shares)
        if current_assets is not None and total_liabilities is not None
        else None
    )
    intangible_assets = context.latest_amount("intangible_assets") or 0.0
    goodwill = context.latest_amount("goodwill") or 0.0
    tangible_book_per_share = (
        _ratio(latest_equity - intangible_assets - goodwill, context.shares)
        if latest_equity is not None
        else None
    )
    growth = (
        _cagr(
            context.amount(annual[0], "net_income"),
            context.amount(annual[-1], "net_income"),
            annual[0].period_end,
            annual[-1].period_end,
        )
        if len(annual) >= 2
        else None
    )
    if latest is None:
        gaps.append("No visible financial period is available.")
    metrics: dict[str, Scalar] = {
        "earnings_stable": stability,
        "earnings_history_years": len(known_earnings),
        "earnings_cagr": growth,
        "restated_eps": restated_eps,
        "book_value_per_share": book_value_per_share,
        "graham_number": graham_number,
        "safety_margin": safety_margin,
        "ncav_per_share": ncav_per_share,
        "tangible_book_value_per_share": tangible_book_per_share,
        "debt_to_asset_ratio": _ratio(total_liabilities, total_assets),
        "current_ratio": _ratio(current_assets, current_liabilities),
    }
    return ModelResult(
        model="graham",
        status=_status(metrics, gaps),
        metrics=metrics,
        assumption_ids=(
            "graham_coefficient",
            "graham_no_growth_pe",
            "earnings_stability_years",
            "debt_ratio_warning",
            "current_ratio_minimum",
        ),
        warnings=tuple(warnings),
        data_gaps=tuple(gaps),
        provenance_ids=context.source_ids(annual),
    )


def _annual_growth(context: _Context, field: str) -> float | None:
    annual = [
        period for period in context.annual if context.amount(period, field) is not None
    ]
    if len(annual) < 2:
        return None
    return _cagr(
        context.amount(annual[0], field),
        context.amount(annual[-1], field),
        annual[0].period_end,
        annual[-1].period_end,
    )


def _buffett(context: _Context) -> ModelResult:
    gaps: list[str] = []
    annual = context.annual
    roe_values = [
        value
        for period in annual[-10:]
        if (
            value := _ratio(
                context.amount(period, "net_income"),
                context.amount(period, "equity"),
            )
        )
        is not None
    ]
    mean_roe = _mean(roe_values)
    roe_std = (
        math.sqrt(
            sum((value - mean_roe) ** 2 for value in roe_values) / (len(roe_values) - 1)
        )
        if mean_roe is not None and len(roe_values) >= 2
        else None
    )
    roe_cv = (
        abs(roe_std / mean_roe)
        if roe_std is not None and mean_roe not in (None, 0)
        else None
    )

    owner_earnings_values: list[float] = []
    gross_margins: list[float] = []
    capex_values: list[float] = []
    net_income_values: list[float] = []
    for period in annual[-10:]:
        net_income = context.amount(period, "net_income")
        depreciation = context.amount(period, "depreciation_amortization")
        capex = context.amount(period, "capital_expenditure")
        if net_income is not None and depreciation is not None and capex is not None:
            owner_earnings_values.append(net_income + depreciation - capex)
        revenue = context.amount(period, "revenue")
        gross_profit = context.amount(period, "gross_profit")
        margin = _ratio(gross_profit, revenue)
        if margin is not None:
            gross_margins.append(margin)
        if capex is not None:
            capex_values.append(capex)
        if net_income is not None:
            net_income_values.append(net_income)
    owner_earnings = _mean(owner_earnings_values)
    if owner_earnings is None:
        gaps.append(
            "Annual net income, depreciation/amortization, and capital "
            "expenditure are required."
        )
    revenue_growth = _annual_growth(context, "revenue")
    growth_cap = (
        context.config.utility_growth_cap
        if context.is_utility
        else context.config.standard_growth_cap
    )
    growth_rate = min(max(revenue_growth or 0.0, 0.0), growth_cap)
    discount_rate = (
        context.config.utility_discount_rate
        if context.is_utility
        else context.config.standard_discount_rate
    )
    intrinsic_value = (
        min(
            owner_earnings / (discount_rate - growth_rate),
            owner_earnings * context.config.max_owner_earnings_multiple,
        )
        if owner_earnings is not None and owner_earnings > 0
        else None
    )
    intrinsic_value_per_share = _ratio(intrinsic_value, context.shares)
    margin_of_safety = (
        (intrinsic_value_per_share - context.payload.market.price)
        / intrinsic_value_per_share
        if intrinsic_value_per_share is not None and intrinsic_value_per_share > 0
        else None
    )
    debt = sum(
        context.latest_amount(field) or 0.0
        for field in (
            "short_term_debt",
            "current_portion_long_term_debt",
            "long_term_debt",
            "bonds_payable",
        )
    )
    latest_net_income = context.ttm("net_income")
    metrics: dict[str, Scalar] = {
        "mean_roe": mean_roe,
        "roe_standard_deviation": roe_std,
        "roe_coefficient_of_variation": roe_cv,
        "owner_earnings": owner_earnings,
        "owner_earnings_basis": "visible_annual_mean",
        "revenue_cagr": revenue_growth,
        "growth_rate_capped": growth_rate,
        "discount_rate": discount_rate,
        "intrinsic_value": intrinsic_value,
        "intrinsic_value_per_share": intrinsic_value_per_share,
        "safety_margin": margin_of_safety,
        "average_gross_margin": _mean(gross_margins[-5:]),
        "capex_to_net_income": _ratio(
            sum(capex_values[-5:]), sum(net_income_values[-5:])
        ),
        "debt_payback_years": (
            _ratio(debt, latest_net_income.value)
            if latest_net_income is not None
            else None
        ),
    }
    return ModelResult(
        model="buffett",
        status=_status(metrics, gaps),
        metrics=metrics,
        assumption_ids=(
            "standard_discount_rate",
            "utility_discount_rate",
            "standard_growth_cap",
            "utility_growth_cap",
            "max_owner_earnings_multiple",
        ),
        data_gaps=tuple(gaps),
        provenance_ids=context.source_ids(annual),
    )


def _greenwald(context: _Context) -> ModelResult:
    gaps: list[str] = []
    recent = context.annual[-3:]
    adjusted_operating_profits: list[float] = []
    tax_rates: list[float] = []
    addback = (
        context.config.technology_rd_addback_ratio
        if context.is_technology
        else context.config.rd_addback_ratio
    )
    for period in recent:
        operating_profit = context.amount(period, "operating_profit")
        if operating_profit is not None:
            research = context.amount(period, "research_development") or 0.0
            adjusted_operating_profits.append(operating_profit + research * addback)
        tax = context.amount(period, "income_tax")
        pretax = context.amount(period, "pretax_income")
        rate = _ratio(tax, pretax)
        if rate is not None:
            tax_rates.append(min(max(rate, 0.0), context.config.maximum_tax_rate))
    normalized_operating_profit = _mean(adjusted_operating_profits)
    tax_rate = _mean(tax_rates) or context.config.default_tax_rate
    cost_of_capital = (
        context.config.bank_discount_rate
        if context.payload.is_financial
        else (
            context.config.utility_discount_rate
            if context.is_utility
            else context.config.standard_discount_rate
        )
    )
    debt = sum(
        context.latest_amount(field) or 0.0
        for field in (
            "short_term_debt",
            "current_portion_long_term_debt",
            "long_term_debt",
            "bonds_payable",
        )
    )
    cash = context.latest_amount("cash") or 0.0
    if context.payload.is_financial:
        normalized_net_income = _mean(
            [
                value
                for period in recent
                if (value := context.amount(period, "net_income")) is not None
            ]
        )
        epv = (
            normalized_net_income / cost_of_capital
            if normalized_net_income is not None and normalized_net_income > 0
            else None
        )
    else:
        nopat = (
            normalized_operating_profit * (1.0 - tax_rate)
            if normalized_operating_profit is not None
            else None
        )
        epv = (
            nopat / cost_of_capital - (debt - cash)
            if nopat is not None and nopat > 0
            else None
        )
    if epv is None:
        gaps.append(
            "Three years of positive operating-profit history are required for EPV."
        )

    if context.payload.is_financial:
        reproduction_cost = context.latest_amount("equity")
    else:
        total_assets = context.latest_amount("total_assets")
        non_interest_liabilities = sum(
            context.latest_amount(field) or 0.0
            for field in (
                "accounts_payable",
                "notes_payable",
                "contract_liabilities",
                "advance_receipts",
                "other_payables",
            )
        )
        reproduction_cost = (
            total_assets - non_interest_liabilities
            if total_assets is not None
            else None
        )
    if reproduction_cost is None:
        gaps.append(
            "Total assets or financial-company equity is required for "
            "reproduction cost."
        )
    moat = _ratio(epv, reproduction_cost)
    growth_value = 0.0
    if (
        epv is not None
        and reproduction_cost is not None
        and reproduction_cost > 0
        and epv > reproduction_cost
    ):
        firm_epv = epv + (0.0 if context.payload.is_financial else debt - cash)
        nopat_value = firm_epv * cost_of_capital
        roic = nopat_value / reproduction_cost
        growth = min(context.config.greenwald_growth_rate, cost_of_capital - 0.01)
        if roic > cost_of_capital and growth > 0:
            value_with_growth = (nopat_value * (1.0 - growth / roic)) / (
                cost_of_capital - growth
            )
            growth_value = max(value_with_growth - firm_epv, 0.0)
    metrics: dict[str, Scalar] = {
        "normalized_operating_profit": normalized_operating_profit,
        "effective_tax_rate": tax_rate,
        "cost_of_capital": cost_of_capital,
        "net_debt": debt - cash,
        "epv": epv,
        "epv_per_share": _ratio(epv, context.shares),
        "reproduction_cost": reproduction_cost,
        "reproduction_cost_per_share": _ratio(reproduction_cost, context.shares),
        "moat_ratio": moat,
        "growth_value": growth_value,
    }
    return ModelResult(
        model="greenwald",
        status=_status(metrics, gaps),
        metrics=metrics,
        assumption_ids=(
            "standard_discount_rate",
            "utility_discount_rate",
            "bank_discount_rate",
            "default_tax_rate",
            "maximum_tax_rate",
            "rd_addback_ratio",
            "technology_rd_addback_ratio",
            "greenwald_growth_rate",
        ),
        data_gaps=tuple(gaps),
        provenance_ids=context.source_ids(recent),
    )


def _lynch(context: _Context) -> ModelResult:
    gaps: list[str] = []
    warnings: list[str] = []
    annual = [
        period
        for period in context.annual
        if context.amount(period, "net_income") is not None
    ]
    restated_eps = [
        (
            period,
            (context.amount(period, "net_income") or 0.0) / context.shares,
        )
        for period in annual
    ]
    latest_eps = restated_eps[-1][1] if restated_eps else None
    growth_3y: float | None = None
    growth_5y: float | None = None
    if len(restated_eps) >= 2:
        latest_period, latest_value = restated_eps[-1]
        three_year_start = min(
            restated_eps,
            key=lambda item: abs(
                (latest_period.period_end - item[0].period_end).days - int(3 * 365.25)
            ),
        )
        five_year_start = min(
            restated_eps,
            key=lambda item: abs(
                (latest_period.period_end - item[0].period_end).days - int(5 * 365.25)
            ),
        )
        growth_3y = _cagr(
            three_year_start[1],
            latest_value,
            three_year_start[0].period_end,
            latest_period.period_end,
        )
        growth_5y = _cagr(
            five_year_start[1],
            latest_value,
            five_year_start[0].period_end,
            latest_period.period_end,
        )
    else:
        gaps.append(
            "At least two visible annual net-income periods are required for "
            "EPS growth."
        )
    selected_growth = growth_3y if growth_3y is not None else growth_5y
    pe = (
        context.payload.market.price / latest_eps
        if latest_eps is not None and latest_eps > 0
        else None
    )
    dividend_yield_percent = (
        context.payload.market.dividend_per_share_ttm
        / context.payload.market.price
        * 100.0
    )
    growth_percent = selected_growth * 100.0 if selected_growth is not None else None
    growth_for_valuation = (
        min(growth_percent, context.config.lynch_growth_cap_percent)
        if growth_percent is not None and growth_percent > 0
        else None
    )
    if (
        growth_percent is not None
        and growth_percent > context.config.lynch_growth_warning_percent
    ):
        warnings.append(
            "EPS growth exceeds the configured sustainability warning threshold."
        )
    peg = _ratio(pe, growth_for_valuation)
    lynch_ratio = (
        (growth_for_valuation + dividend_yield_percent) / pe
        if growth_for_valuation is not None and pe not in (None, 0)
        else None
    )

    if context.payload.is_financial:
        category = "unverified"
        warnings.append(
            "Financial companies require sector-specific underwriting; "
            "ordinary PEG is not decisive."
        )
    elif context.is_cyclical:
        category = "cyclical"
        warnings.append(
            "Cyclical classification requires external cycle-position evidence "
            "before valuation conclusions."
        )
    elif latest_eps is not None and latest_eps <= 0:
        category = "turnaround"
    elif selected_growth is None:
        category = "unverified"
    elif selected_growth >= context.config.lynch_fast_grower_min:
        category = "fast_grower"
    elif (
        context.config.lynch_stalwart_min
        <= selected_growth
        < context.config.lynch_stalwart_max
    ):
        category = "stalwart"
    else:
        category = "slow_grower"
    metrics: dict[str, Scalar] = {
        "category": category,
        "latest_restated_eps": latest_eps,
        "restated_eps_growth_3y": growth_3y,
        "restated_eps_growth_5y": growth_5y,
        "pe": pe,
        "dividend_yield_percent": dividend_yield_percent,
        "growth_percent_for_valuation": growth_for_valuation,
        "peg": peg,
        "lynch_ratio": lynch_ratio,
        "is_financial": context.payload.is_financial,
        "is_cyclical": context.is_cyclical,
    }
    return ModelResult(
        model="lynch",
        status=_status(metrics, gaps),
        metrics=metrics,
        assumption_ids=(
            "lynch_fast_grower_min",
            "lynch_stalwart_min",
            "lynch_stalwart_max",
            "lynch_growth_warning_percent",
            "lynch_growth_cap_percent",
        ),
        warnings=tuple(warnings),
        data_gaps=tuple(gaps),
        provenance_ids=context.source_ids(annual),
    )


def audit_company(
    payload: CompanyFinancialPayload | Mapping[str, object],
    *,
    config: AuditConfig = DEFAULT_CONFIG,
) -> AuditResult:
    """Run all deterministic value-audit models for a point-in-time payload."""
    parsed = (
        payload
        if isinstance(payload, CompanyFinancialPayload)
        else CompanyFinancialPayload.from_dict(payload)
    )
    context = _Context(parsed, config)
    models = {
        "graham": _graham(context),
        "buffett": _buffett(context),
        "greenwald": _greenwald(context),
        "lynch": _lynch(context),
    }
    warnings: list[str] = []
    if context.excluded_period_count:
        warnings.append(
            f"Excluded {context.excluded_period_count} period(s) not visible "
            "at the audit date."
        )
    if not context.periods:
        warnings.append("No financial periods were visible at the audit date.")
    gaps = tuple(
        sorted(
            {
                f"{name}: {gap}"
                for name, model in models.items()
                for gap in model.data_gaps
            }
        )
    )
    return AuditResult(
        company_id=parsed.company_id,
        company_name=parsed.company_name,
        as_of_date=parsed.as_of_date,
        currency=parsed.currency,
        models=models,
        assumptions=config.to_dict(),
        warnings=tuple(warnings),
        data_gaps=gaps,
        provenance=parsed.provenance,
    )
