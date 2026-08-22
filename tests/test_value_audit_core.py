# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false

from __future__ import annotations

import copy
import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from trinity_agentic_kit.value_audit import (
    COMPANY_FINANCIAL_PAYLOAD_SCHEMA,
    PACKAGE_VERSION,
    VALUE_AUDIT_RESULT_SCHEMA,
    AuditConfig,
    CompanyFinancialPayload,
    audit_company,
)

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "value_audit_company_v1.json"


def _fixture() -> dict[str, object]:
    return cast(dict[str, object], json.loads(FIXTURE.read_text(encoding="utf-8")))


def _load_validator() -> ModuleType:
    path = ROOT / "skills" / "lynch-research" / "validate.py"
    spec = importlib.util.spec_from_file_location("lynch_research_validator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_contracts_and_public_result_are_versioned() -> None:
    payload = _fixture()
    Draft202012Validator(
        COMPANY_FINANCIAL_PAYLOAD_SCHEMA, format_checker=FormatChecker()
    ).validate(payload)

    parsed = CompanyFinancialPayload.from_dict(payload)
    result = audit_company(parsed).to_dict()

    Draft202012Validator(
        VALUE_AUDIT_RESULT_SCHEMA, format_checker=FormatChecker()
    ).validate(result)
    assert result["package_version"] == PACKAGE_VERSION == "0.1.0"
    assert set(cast(dict[str, object], result["models"])) == {
        "graham",
        "buffett",
        "greenwald",
        "lynch",
    }
    assert "not investment" in str(result["disclaimer"]).lower()


def test_regression_metrics_are_deterministic() -> None:
    payload = _fixture()
    first = audit_company(payload).to_dict()
    second = audit_company(payload).to_dict()
    assert first == second

    models = cast(dict[str, dict[str, object]], first["models"])
    graham = cast(dict[str, object], models["graham"]["metrics"])
    buffett = cast(dict[str, object], models["buffett"]["metrics"])
    greenwald = cast(dict[str, object], models["greenwald"]["metrics"])
    lynch = cast(dict[str, object], models["lynch"]["metrics"])
    assert graham["restated_eps"] == pytest.approx(1.0)
    assert graham["graham_number"] == pytest.approx((22.5 * 1.0 * 6.5) ** 0.5)
    assert buffett["owner_earnings"] == pytest.approx(
        (35.0 + 42.0 + 49.0 + 60.0 + 72.0 + 90.0) / 6 * 1_000_000
    )
    assert cast(float, greenwald["epv"]) > cast(float, greenwald["reproduction_cost"])
    assert lynch["category"] == "fast_grower"
    assert lynch["pe"] == pytest.approx(24.0)
    assert lynch["dividend_yield_percent"] == pytest.approx(2.0)


def test_future_restatement_is_excluded_at_point_in_time() -> None:
    baseline_payload = _fixture()
    baseline = audit_company(baseline_payload)
    payload = copy.deepcopy(baseline_payload)
    periods = cast(list[dict[str, object]], payload["periods"])
    future = copy.deepcopy(periods[-1])
    future["visible_at"] = "2025-07-01"
    values = cast(dict[str, float], future["values"])
    values["net_income"] = 900.0
    future["source_ids"] = ["filing.future"]
    periods.append(future)
    provenance = cast(list[dict[str, object]], payload["provenance"])
    provenance.append(
        {
            "source_id": "filing.future",
            "source_type": "synthetic_restatement",
            "as_of_date": "2025-07-01",
        }
    )

    result = audit_company(payload)

    assert result.models["lynch"].metrics == baseline.models["lynch"].metrics
    assert result.models["graham"].metrics == baseline.models["graham"].metrics
    assert result.warnings == ("Excluded 1 period(s) not visible at the audit date.",)


def test_latest_visible_restatement_wins_and_restates_all_eps() -> None:
    payload = _fixture()
    payload["as_of_date"] = "2025-07-02"
    periods = cast(list[dict[str, object]], payload["periods"])
    restatement = copy.deepcopy(periods[-1])
    restatement["visible_at"] = "2025-07-01"
    cast(dict[str, float], restatement["values"])["net_income"] = 120.0
    restatement["source_ids"] = ["filing.restatement"]
    periods.append(restatement)
    cast(list[dict[str, object]], payload["provenance"]).append(
        {
            "source_id": "filing.restatement",
            "source_type": "synthetic_restatement",
            "as_of_date": "2025-07-01",
        }
    )
    result = audit_company(payload)

    assert result.models["lynch"].metrics["latest_restated_eps"] == pytest.approx(1.2)
    assert result.models["graham"].metrics["restated_eps"] == pytest.approx(1.2)
    assert "filing.restatement" in result.models["lynch"].provenance_ids


def test_units_normalize_to_identical_results() -> None:
    millions = _fixture()
    ones = copy.deepcopy(millions)
    ones["monetary_unit"] = "ones"
    ones["share_unit"] = "shares"
    market = cast(dict[str, object], ones["market"])
    market["shares_outstanding"] = cast(float, market["shares_outstanding"]) * 1_000_000
    for period in cast(list[dict[str, object]], ones["periods"]):
        values = cast(dict[str, float], period["values"])
        for key in values:
            values[key] *= 1_000_000

    million_result = audit_company(millions)
    one_result = audit_company(ones)

    for model_name in ("graham", "buffett", "greenwald", "lynch"):
        assert (
            million_result.models[model_name].metrics
            == one_result.models[model_name].metrics
        )


def test_missing_data_is_explicit_not_success_shaped() -> None:
    payload = _fixture()
    payload["periods"] = []
    payload["provenance"] = [
        {
            "source_id": "market.synthetic",
            "source_type": "synthetic_market_snapshot",
            "as_of_date": "2025-06-30",
        }
    ]

    result = audit_company(payload)

    assert result.data_gaps
    assert "No financial periods were visible" in result.warnings[0]
    assert result.models["greenwald"].status == "partial"
    assert result.models["greenwald"].data_gaps


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("as_of_date", "2025-02-30", "valid ISO date"),
        ("currency", "US", "three-letter"),
        ("schema_version", "2.0", "Unsupported input schema"),
    ],
)
def test_invalid_contract_values_are_rejected(
    field: str, value: object, message: str
) -> None:
    payload = _fixture()
    payload[field] = value
    with pytest.raises(ValueError, match=message):
        CompanyFinancialPayload.from_dict(payload)


def test_market_snapshot_cannot_look_past_audit_date() -> None:
    payload = _fixture()
    cast(dict[str, object], payload["market"])["date"] = "2025-07-01"
    with pytest.raises(ValueError, match="after as_of_date"):
        CompanyFinancialPayload.from_dict(payload)


def test_config_thresholds_are_overridable_and_guarded() -> None:
    result = audit_company(
        _fixture(),
        config=AuditConfig(lynch_fast_grower_min=0.25, lynch_stalwart_max=0.25),
    )
    assert result.models["lynch"].metrics["category"] == "stalwart"
    assert result.assumptions["lynch_fast_grower_min"] == 0.25
    with pytest.raises(ValueError, match="must exceed"):
        AuditConfig(standard_discount_rate=0.04)


def test_skill_validator_consumes_public_result_only() -> None:
    module = _load_validator()
    validate_input = cast(Callable[[object], list[str]], module.validate_audit_input)
    validate_output = cast(Callable[..., list[str]], module.validate_research_output)
    audit_input = audit_company(_fixture()).to_dict()
    decision = {
        "schema_version": "1.0",
        "company_id": "SYNTH-001",
        "verified_category": "stalwart",
        "ranking_framework": "stalwart",
        "verdict": "watchlist",
        "confidence": "medium",
        "thesis": "Synthetic evidence supports a moderate-growth watchlist case.",
        "evidence": [{"claim": "Restated EPS grew.", "source_ids": ["filing.2024"]}],
        "vetoes": [],
        "warnings": [],
        "data_gaps": [],
        "follow_up_checks": [],
    }
    assert validate_input(audit_input) == []
    assert validate_output(decision, audit_input=audit_input) == []

    decision["company_id"] = "OTHER"
    assert "must match" in " ".join(validate_output(decision, audit_input=audit_input))
