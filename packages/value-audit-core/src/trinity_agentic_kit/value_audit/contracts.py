from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from importlib.resources import files
from typing import Literal, cast

VALUE_AUDIT_INPUT_SCHEMA_VERSION = "1.0"
VALUE_AUDIT_RESULT_SCHEMA_VERSION = "1.0"
PACKAGE_VERSION = "0.1.0"

MonetaryUnit = Literal["ones", "thousands", "millions"]
ShareUnit = Literal["shares", "thousands", "millions"]
PeriodType = Literal["annual", "interim"]
ModelStatus = Literal["complete", "partial", "unavailable"]
Scalar = str | int | float | bool | None


def _load_schema(filename: str) -> dict[str, object]:
    value: object = json.loads(
        files("trinity_agentic_kit.value_audit.schemas")
        .joinpath(filename)
        .read_text(encoding="utf-8")
    )
    if not isinstance(value, dict):
        raise RuntimeError(f"Invalid bundled JSON Schema: {filename}")
    return cast(dict[str, object], value)


COMPANY_FINANCIAL_PAYLOAD_SCHEMA = _load_schema("company-financial-payload-v1.json")
VALUE_AUDIT_RESULT_SCHEMA = _load_schema("value-audit-result-v1.json")


def _parse_date(value: object, path: str) -> date:
    if not isinstance(value, str):
        raise ValueError(f"{path} must be an ISO date string")
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ValueError(f"{path} must be a valid ISO date") from error


def _as_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{path} must be an object")
    mapping = cast(Mapping[object, object], value)
    if not all(isinstance(key, str) for key in mapping):
        raise ValueError(f"{path} keys must be strings")
    return cast(Mapping[str, object], mapping)


def _as_sequence(value: object, path: str) -> Sequence[object]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{path} must be an array")
    return cast(Sequence[object], value)


def _required_string(mapping: Mapping[str, object], key: str, path: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}.{key} must be a non-empty string")
    return value.strip()


def _optional_string(mapping: Mapping[str, object], key: str) -> str:
    value = mapping.get(key, "")
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value.strip()


def _number(value: object, path: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{path} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{path} must be finite")
    if positive and number <= 0:
        raise ValueError(f"{path} must be greater than zero")
    return number


def _source_ids(value: object, path: str) -> tuple[str, ...]:
    values = _as_sequence(value, path)
    result: list[str] = []
    for index, item in enumerate(values):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{path}[{index}] must be a non-empty string")
        result.append(item.strip())
    return tuple(result)


@dataclass(frozen=True, slots=True)
class ProvenanceRecord:
    source_id: str
    source_type: str
    as_of_date: date
    label: str = ""
    uri: str = ""

    @classmethod
    def from_dict(cls, value: object) -> ProvenanceRecord:
        mapping = _as_mapping(value, "provenance[]")
        return cls(
            source_id=_required_string(mapping, "source_id", "provenance[]"),
            source_type=_required_string(mapping, "source_type", "provenance[]"),
            as_of_date=_parse_date(
                mapping.get("as_of_date"), "provenance[].as_of_date"
            ),
            label=_optional_string(mapping, "label"),
            uri=_optional_string(mapping, "uri"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "source_id": self.source_id,
            "source_type": self.source_type,
            "as_of_date": self.as_of_date.isoformat(),
            "label": self.label,
            "uri": self.uri,
        }


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    date: date
    price: float
    shares_outstanding: float
    dividend_per_share_ttm: float = 0.0
    source_ids: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, value: object) -> MarketSnapshot:
        mapping = _as_mapping(value, "market")
        dividend = mapping.get("dividend_per_share_ttm", 0.0)
        return cls(
            date=_parse_date(mapping.get("date"), "market.date"),
            price=_number(mapping.get("price"), "market.price", positive=True),
            shares_outstanding=_number(
                mapping.get("shares_outstanding"),
                "market.shares_outstanding",
                positive=True,
            ),
            dividend_per_share_ttm=_number(dividend, "market.dividend_per_share_ttm"),
            source_ids=_source_ids(mapping.get("source_ids", []), "market.source_ids"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "date": self.date.isoformat(),
            "price": self.price,
            "shares_outstanding": self.shares_outstanding,
            "dividend_per_share_ttm": self.dividend_per_share_ttm,
            "source_ids": list(self.source_ids),
        }


@dataclass(frozen=True, slots=True)
class FinancialPeriod:
    period_end: date
    visible_at: date
    period_type: PeriodType
    months: int
    values: Mapping[str, float]
    source_ids: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: object) -> FinancialPeriod:
        mapping = _as_mapping(value, "periods[]")
        period_type_value = mapping.get("period_type")
        if period_type_value not in ("annual", "interim"):
            raise ValueError("periods[].period_type must be annual or interim")
        months_value = mapping.get("months")
        if isinstance(months_value, bool) or not isinstance(months_value, int):
            raise ValueError("periods[].months must be an integer")
        if months_value < 1 or months_value > 12:
            raise ValueError("periods[].months must be between 1 and 12")
        if period_type_value == "annual" and months_value != 12:
            raise ValueError("Annual periods must contain 12 months")

        raw_values = _as_mapping(mapping.get("values"), "periods[].values")
        parsed_values = {
            key: _number(item, f"periods[].values.{key}")
            for key, item in raw_values.items()
        }
        if not parsed_values:
            raise ValueError("periods[].values cannot be empty")
        return cls(
            period_end=_parse_date(mapping.get("period_end"), "periods[].period_end"),
            visible_at=_parse_date(mapping.get("visible_at"), "periods[].visible_at"),
            period_type=period_type_value,
            months=months_value,
            values=parsed_values,
            source_ids=_source_ids(
                mapping.get("source_ids", []), "periods[].source_ids"
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "period_end": self.period_end.isoformat(),
            "visible_at": self.visible_at.isoformat(),
            "period_type": self.period_type,
            "months": self.months,
            "values": dict(self.values),
            "source_ids": list(self.source_ids),
        }


@dataclass(frozen=True, slots=True)
class CompanyFinancialPayload:
    company_id: str
    company_name: str
    industry: str
    as_of_date: date
    currency: str
    monetary_unit: MonetaryUnit
    share_unit: ShareUnit
    market: MarketSnapshot
    periods: tuple[FinancialPeriod, ...]
    provenance: tuple[ProvenanceRecord, ...]
    is_financial: bool = False
    schema_version: str = VALUE_AUDIT_INPUT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != VALUE_AUDIT_INPUT_SCHEMA_VERSION:
            raise ValueError(f"Unsupported input schema version: {self.schema_version}")
        if len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("currency must be a three-letter alphabetic code")
        if self.market.date > self.as_of_date:
            raise ValueError("market.date cannot be after as_of_date")
        known_sources = {item.source_id for item in self.provenance}
        referenced_sources = set(self.market.source_ids)
        for period in self.periods:
            referenced_sources.update(period.source_ids)
        unknown = referenced_sources - known_sources
        if unknown:
            raise ValueError(
                "Referenced source_ids missing from provenance: "
                + ", ".join(sorted(unknown))
            )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> CompanyFinancialPayload:
        schema_version = _required_string(value, "schema_version", "payload")
        monetary_unit = value.get("monetary_unit")
        if monetary_unit not in ("ones", "thousands", "millions"):
            raise ValueError("monetary_unit must be ones, thousands, or millions")
        share_unit = value.get("share_unit")
        if share_unit not in ("shares", "thousands", "millions"):
            raise ValueError("share_unit must be shares, thousands, or millions")
        is_financial = value.get("is_financial", False)
        if not isinstance(is_financial, bool):
            raise ValueError("is_financial must be a boolean")
        periods = tuple(
            FinancialPeriod.from_dict(item)
            for item in _as_sequence(value.get("periods"), "periods")
        )
        provenance = tuple(
            ProvenanceRecord.from_dict(item)
            for item in _as_sequence(value.get("provenance"), "provenance")
        )
        return cls(
            schema_version=schema_version,
            company_id=_required_string(value, "company_id", "payload"),
            company_name=_required_string(value, "company_name", "payload"),
            industry=_required_string(value, "industry", "payload"),
            is_financial=is_financial,
            as_of_date=_parse_date(value.get("as_of_date"), "as_of_date"),
            currency=_required_string(value, "currency", "payload").upper(),
            monetary_unit=monetary_unit,
            share_unit=share_unit,
            market=MarketSnapshot.from_dict(value.get("market")),
            periods=periods,
            provenance=provenance,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "company_id": self.company_id,
            "company_name": self.company_name,
            "industry": self.industry,
            "is_financial": self.is_financial,
            "as_of_date": self.as_of_date.isoformat(),
            "currency": self.currency,
            "monetary_unit": self.monetary_unit,
            "share_unit": self.share_unit,
            "market": self.market.to_dict(),
            "periods": [period.to_dict() for period in self.periods],
            "provenance": [item.to_dict() for item in self.provenance],
        }


@dataclass(frozen=True, slots=True)
class ModelResult:
    model: str
    status: ModelStatus
    metrics: Mapping[str, Scalar]
    assumption_ids: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    data_gaps: tuple[str, ...] = ()
    provenance_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "model": self.model,
            "status": self.status,
            "metrics": dict(self.metrics),
            "assumption_ids": list(self.assumption_ids),
            "warnings": list(self.warnings),
            "data_gaps": list(self.data_gaps),
            "provenance_ids": list(self.provenance_ids),
        }


def _empty_models() -> dict[str, ModelResult]:
    return {}


def _empty_assumptions() -> dict[str, float | int]:
    return {}


@dataclass(frozen=True, slots=True)
class AuditResult:
    company_id: str
    company_name: str
    as_of_date: date
    currency: str
    monetary_unit: Literal["ones"] = "ones"
    models: Mapping[str, ModelResult] = field(default_factory=_empty_models)
    assumptions: Mapping[str, float | int] = field(default_factory=_empty_assumptions)
    warnings: tuple[str, ...] = ()
    data_gaps: tuple[str, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()
    input_schema_version: str = VALUE_AUDIT_INPUT_SCHEMA_VERSION
    schema_version: str = VALUE_AUDIT_RESULT_SCHEMA_VERSION
    package_version: str = PACKAGE_VERSION
    disclaimer: str = (
        "Research calculations only; not investment, legal, tax, or accounting "
        "advice. No affiliation or endorsement by the people or organizations "
        "whose names identify the analytical styles."
    )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "package_version": self.package_version,
            "input_schema_version": self.input_schema_version,
            "company_id": self.company_id,
            "company_name": self.company_name,
            "as_of_date": self.as_of_date.isoformat(),
            "currency": self.currency,
            "monetary_unit": self.monetary_unit,
            "models": {key: model.to_dict() for key, model in self.models.items()},
            "assumptions": dict(self.assumptions),
            "warnings": list(self.warnings),
            "data_gaps": list(self.data_gaps),
            "provenance": [item.to_dict() for item in self.provenance],
            "disclaimer": self.disclaimer,
        }
