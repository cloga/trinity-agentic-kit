from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Protocol, cast

from trinity_agentic_kit.value_audit import (
    CompanyFinancialPayload,
    FinancialPeriod,
    MarketSnapshot,
    ProvenanceRecord,
)

from .contracts import TushareMappingError


class _RecordsFrame(Protocol):
    def to_dict(self, orient: str) -> object: ...


_INCOME_MAP = {
    "revenue": "revenue",
    "operate_profit": "operating_profit",
    "total_profit": "pretax_income",
    "income_tax": "income_tax",
    "n_income_attr_p": "net_income",
    "rd_exp": "research_development",
}
_BALANCE_MAP = {
    "total_hldr_eqy_exc_min_int": "equity",
    "total_cur_assets": "current_assets",
    "total_cur_liab": "current_liabilities",
    "total_liab": "total_liabilities",
    "total_assets": "total_assets",
    "intan_assets": "intangible_assets",
    "goodwill": "goodwill",
    "money_cap": "cash",
    "st_borr": "short_term_debt",
    "non_cur_liab_due_1y": "current_portion_long_term_debt",
    "lt_borr": "long_term_debt",
    "bond_payable": "bonds_payable",
    "acct_payable": "accounts_payable",
    "notes_payable": "notes_payable",
    "contract_liab": "contract_liabilities",
    "adv_receipts": "advance_receipts",
    "oth_payable": "other_payables",
}
_CASHFLOW_MAP = {
    "c_pay_acq_const_fiolta": "capital_expenditure",
    "n_cashflow_act": "operating_cash_flow",
}
_FINANCIAL_INDUSTRIES = (
    "bank",
    "banking",
    "finance",
    "financial",
    "insurance",
    "securities",
    "银行",
    "保险",
    "证券",
    "金融",
    "多元金融",
)
_CUMULATIVE_REPORT_RANK = {"": 0, "5": 1, "1": 2, "4": 3}


def _records(value: object) -> tuple[Mapping[str, object], ...]:
    if value is None:
        return ()
    raw: object = value
    if hasattr(value, "to_dict"):
        raw = cast(_RecordsFrame, value).to_dict("records")
    if isinstance(raw, Mapping):
        return (cast(Mapping[str, object], raw),)
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise TushareMappingError("Each frame must provide record mappings")
    records: list[Mapping[str, object]] = []
    for item in cast(Sequence[object], raw):
        if isinstance(item, Mapping):
            records.append(cast(Mapping[str, object], item))
        else:
            records.extend(_records(item))
    return tuple(records)


def _date(value: object, path: str) -> date:
    text = str(value or "").strip()
    for format_string in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, format_string).date()
        except ValueError:
            continue
    raise TushareMappingError(f"{path} must be YYYYMMDD or YYYY-MM-DD")


def _optional_date(value: object) -> date | None:
    try:
        return _date(value, "date")
    except TushareMappingError:
        return None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _text(value: object) -> str:
    if isinstance(value, float) and not math.isfinite(value):
        return ""
    return str(value or "").strip()


def _visible_at(row: Mapping[str, object]) -> date | None:
    return _optional_date(row.get("f_ann_date")) or _optional_date(row.get("ann_date"))


def _latest_market(
    rows: tuple[Mapping[str, object], ...],
    *,
    as_of: date,
) -> Mapping[str, object]:
    candidates = [
        row
        for row in rows
        if (trade_date := _optional_date(row.get("trade_date"))) is not None
        and trade_date <= as_of
        and (_number(row.get("close")) or 0) > 0
        and (_number(row.get("total_share")) or 0) > 0
    ]
    if not candidates:
        raise TushareMappingError(
            "daily_basic requires a positive close and total_share on or before as_of"
        )
    return max(candidates, key=lambda row: _date(row.get("trade_date"), "trade_date"))


def _latest_statement_rows(
    rows: tuple[Mapping[str, object], ...],
    *,
    as_of: date,
) -> dict[date, tuple[date, Mapping[str, object]]]:
    selected: dict[
        date,
        tuple[date, int, int, tuple[tuple[str, str], ...], Mapping[str, object]],
    ] = {}
    for row in rows:
        period_end = _optional_date(row.get("end_date"))
        visible_at = _visible_at(row)
        report_type = _text(row.get("report_type"))
        if period_end is None or visible_at is None or visible_at > as_of:
            continue
        if report_type not in _CUMULATIVE_REPORT_RANK:
            continue
        report_rank = _CUMULATIVE_REPORT_RANK[report_type]
        update_rank = 1 if _text(row.get("update_flag")) == "1" else 0
        fingerprint = tuple((str(key), str(row[key])) for key in sorted(row, key=str))
        current = selected.get(period_end)
        ordering = (visible_at, report_rank, update_rank, fingerprint)
        if current is None or ordering > current[:4]:
            selected[period_end] = (*ordering, row)
    return {
        period_end: (visible_at, row)
        for period_end, (visible_at, _, _, _, row) in selected.items()
    }


def _mapped_values(
    row: Mapping[str, object],
    field_map: Mapping[str, str],
) -> dict[str, float]:
    result: dict[str, float] = {}
    for source_field, target_field in field_map.items():
        number = _number(row.get(source_field))
        if number is not None:
            result[target_field] = (
                abs(number) if target_field == "capital_expenditure" else number
            )
    return result


def _income_values(row: Mapping[str, object]) -> dict[str, float]:
    result = _mapped_values(row, _INCOME_MAP)
    if "net_income" not in result:
        fallback = _number(row.get("n_income"))
        if fallback is not None:
            result["net_income"] = fallback
    revenue = _number(row.get("revenue"))
    operating_cost = _number(row.get("oper_cost"))
    if revenue is not None and operating_cost is not None:
        result["gross_profit"] = revenue - operating_cost
    return result


def _cashflow_values(row: Mapping[str, object]) -> dict[str, float]:
    result = _mapped_values(row, _CASHFLOW_MAP)
    depreciation = _number(row.get("c_depr_fina_amort"))
    if depreciation is None:
        components = [
            _number(row.get(field))
            for field in (
                "depr_fa_coga_dpba",
                "amort_intang_assets",
                "lt_amort_deferred_exp",
                "use_right_asset_dep",
            )
        ]
        known = [component for component in components if component is not None]
        depreciation = sum(known) if known else None
    if depreciation is not None:
        result["depreciation_amortization"] = depreciation
    return result


def _source_id(
    endpoint: str,
    ticker: str,
    period_end: date,
    visible_at: date,
) -> str:
    return (
        f"tushare:{endpoint}:{ticker}:{period_end.isoformat()}:{visible_at.isoformat()}"
    )


def _listed_on(row: Mapping[str, object], as_of: date) -> bool:
    list_date = _optional_date(row.get("list_date"))
    delist_date = _optional_date(row.get("delist_date"))
    return (list_date is None or list_date <= as_of) and (
        delist_date is None or as_of <= delist_date
    )


def map_tushare_frames_to_payload(
    frames: Mapping[str, object],
    ticker: str,
    as_of: date,
    *,
    is_financial: bool | None = None,
) -> CompanyFinancialPayload:
    normalized_ticker = ticker.strip().upper()
    stock_rows = _records(frames.get("stock_basic"))
    identity = next(
        (
            row
            for row in stock_rows
            if _text(row.get("ts_code")).upper() in ("", normalized_ticker)
            and _listed_on(row, as_of)
        ),
        None,
    )
    if identity is None:
        raise TushareMappingError("stock_basic requires a matching company row")
    company_name = _text(identity.get("name"))
    industry = _text(identity.get("industry")) or "unclassified"
    if not company_name:
        raise TushareMappingError("stock_basic.name must be non-empty")

    market_row = _latest_market(_records(frames.get("daily_basic")), as_of=as_of)
    market_date = _date(market_row.get("trade_date"), "trade_date")
    price = cast(float, _number(market_row.get("close")))
    shares = cast(float, _number(market_row.get("total_share"))) * 10_000.0
    dividend_yield = _number(market_row.get("dv_ttm")) or 0.0
    market_source_id = (
        f"tushare:daily_basic:{normalized_ticker}:{market_date.isoformat()}"
    )

    endpoint_rows = {
        "income": _latest_statement_rows(_records(frames.get("income")), as_of=as_of),
        "balancesheet": _latest_statement_rows(
            _records(frames.get("balancesheet")), as_of=as_of
        ),
        "cashflow": _latest_statement_rows(
            _records(frames.get("cashflow")), as_of=as_of
        ),
    }
    period_end_set: set[date] = set()
    for rows in endpoint_rows.values():
        period_end_set.update(rows)
    period_ends = sorted(period_end_set)
    if not period_ends:
        raise TushareMappingError(
            "No financial rows with announcement dates visible at as_of"
        )

    periods: list[FinancialPeriod] = []
    provenance = [
        ProvenanceRecord(
            source_id=f"tushare:stock_basic:{normalized_ticker}",
            source_type="tushare.stock_basic",
            as_of_date=as_of,
            label=(
                "Company identity and current industry classification; listing "
                "dates checked at audit date"
            ),
        ),
        ProvenanceRecord(
            source_id=market_source_id,
            source_type="tushare.daily_basic",
            as_of_date=market_date,
            label="Close, total shares, and trailing dividend yield",
        ),
    ]
    for period_end in period_ends:
        values: dict[str, float] = {}
        source_ids: list[str] = []
        visible_dates: list[date] = []
        for endpoint, rows in endpoint_rows.items():
            selected = rows.get(period_end)
            if selected is None:
                continue
            visible_at, row = selected
            endpoint_values = (
                _income_values(row)
                if endpoint == "income"
                else (
                    _mapped_values(row, _BALANCE_MAP)
                    if endpoint == "balancesheet"
                    else _cashflow_values(row)
                )
            )
            if not endpoint_values:
                continue
            values.update(endpoint_values)
            source_id = _source_id(endpoint, normalized_ticker, period_end, visible_at)
            source_ids.append(source_id)
            visible_dates.append(visible_at)
            provenance.append(
                ProvenanceRecord(
                    source_id=source_id,
                    source_type=f"tushare.{endpoint}",
                    as_of_date=visible_at,
                    label=f"{endpoint} row for {period_end.isoformat()}",
                )
            )
        if not values:
            continue
        months = period_end.month
        periods.append(
            FinancialPeriod(
                period_end=period_end,
                visible_at=max(visible_dates),
                period_type="annual" if months == 12 else "interim",
                months=12 if months == 12 else months,
                values=values,
                source_ids=tuple(source_ids),
            )
        )

    return CompanyFinancialPayload(
        company_id=normalized_ticker,
        company_name=company_name,
        industry=industry,
        is_financial=(
            is_financial
            if is_financial is not None
            else any(
                keyword in industry.casefold() for keyword in _FINANCIAL_INDUSTRIES
            )
        ),
        as_of_date=as_of,
        currency="CNY",
        monetary_unit="ones",
        share_unit="shares",
        market=MarketSnapshot(
            date=market_date,
            price=price,
            shares_outstanding=shares,
            dividend_per_share_ttm=price * dividend_yield / 100.0,
            source_ids=(market_source_id,),
        ),
        periods=tuple(periods),
        provenance=tuple(provenance),
    )
