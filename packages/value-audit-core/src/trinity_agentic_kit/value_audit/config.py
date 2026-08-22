from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class AuditConfig:
    """Documented, overridable implementation assumptions."""

    graham_coefficient: float = 22.5
    graham_no_growth_pe: float = 8.5
    earnings_stability_years: int = 10
    standard_discount_rate: float = 0.09
    utility_discount_rate: float = 0.06
    bank_discount_rate: float = 0.07
    standard_growth_cap: float = 0.05
    utility_growth_cap: float = 0.03
    max_owner_earnings_multiple: float = 35.0
    default_tax_rate: float = 0.15
    maximum_tax_rate: float = 0.25
    rd_addback_ratio: float = 1.0
    technology_rd_addback_ratio: float = 0.20
    greenwald_growth_rate: float = 0.03
    lynch_fast_grower_min: float = 0.20
    lynch_stalwart_min: float = 0.10
    lynch_stalwart_max: float = 0.20
    lynch_growth_warning_percent: float = 25.0
    lynch_growth_cap_percent: float = 50.0
    debt_ratio_warning: float = 0.60
    current_ratio_minimum: float = 1.0

    def __post_init__(self) -> None:
        rates = (
            self.standard_discount_rate,
            self.utility_discount_rate,
            self.bank_discount_rate,
            self.standard_growth_cap,
            self.utility_growth_cap,
            self.default_tax_rate,
            self.maximum_tax_rate,
            self.rd_addback_ratio,
            self.technology_rd_addback_ratio,
            self.greenwald_growth_rate,
            self.lynch_fast_grower_min,
            self.lynch_stalwart_min,
            self.lynch_stalwart_max,
            self.debt_ratio_warning,
            self.current_ratio_minimum,
        )
        if any(value < 0 for value in rates):
            raise ValueError("Audit assumptions cannot be negative")
        if self.standard_discount_rate <= self.standard_growth_cap:
            raise ValueError("Standard discount rate must exceed its growth cap")
        if self.utility_discount_rate <= self.utility_growth_cap:
            raise ValueError("Utility discount rate must exceed its growth cap")
        if self.earnings_stability_years < 2:
            raise ValueError("earnings_stability_years must be at least 2")

    def to_dict(self) -> dict[str, float | int]:
        return asdict(self)


DEFAULT_CONFIG = AuditConfig()
