# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false

from __future__ import annotations

import importlib.util
import json
from collections.abc import Callable
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

from trinity_agentic_kit.value_explainer import (
    EXPLANATION_PACKAGE_SCHEMA,
    PACKAGE_VERSION,
    TOPIC_CANDIDATE_SCHEMA,
    DeterministicFakeProvider,
    DraftScene,
    EvidenceClaim,
    SemanticDraft,
    SemanticGenerationPort,
    SemanticRequest,
    TopicCandidate,
    candidate_from_value_audit_result,
    explain_value_topic,
)

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "value_explainer_topic_v1.json"


class ProviderFactory(Protocol):
    def __call__(self) -> SemanticGenerationPort: ...


def _fixture() -> dict[str, object]:
    return cast(dict[str, object], json.loads(FIXTURE.read_text(encoding="utf-8")))


def _load_validator() -> ModuleType:
    path = ROOT / "skills" / "value-investing-explainer" / "validate.py"
    spec = importlib.util.spec_from_file_location("value_explainer_validator", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_versioned_contracts_and_deterministic_orchestration() -> None:
    candidate = _fixture()
    Draft202012Validator(
        TOPIC_CANDIDATE_SCHEMA, format_checker=FormatChecker()
    ).validate(candidate)

    first = explain_value_topic(candidate, provider=DeterministicFakeProvider())
    second = explain_value_topic(candidate, provider=DeterministicFakeProvider())

    assert first == second
    assert first.qa.passed
    assert first.package_version == PACKAGE_VERSION == "0.1.0"
    assert first.scenes[0].index == 1
    assert first.scenes[0].source_ids == ("public-like.lesson",)
    Draft202012Validator(
        EXPLANATION_PACKAGE_SCHEMA, format_checker=FormatChecker()
    ).validate(first.to_dict())


def test_evidence_attribution_round_trips_into_explanation_output() -> None:
    legacy = TopicCandidate.from_dict(_fixture())
    legacy_dict = legacy.to_dict()
    legacy_evidence = cast(list[dict[str, object]], legacy_dict["evidence"])
    assert "attribution" not in legacy_evidence[0]
    assert TopicCandidate.from_dict(legacy_dict) == legacy

    candidate_data = _fixture()
    evidence = cast(list[dict[str, object]], candidate_data["evidence"])
    evidence[0]["attribution"] = {
        "author": "Synthetic Author",
        "work_title": "Synthetic Work",
        "source_location": "chapter 2",
        "license_name": "Declared License",
        "license_uri": "https://example.invalid/license",
        "attribution_text": "Credit Synthetic Author",
    }
    candidate = TopicCandidate.from_dict(candidate_data)
    expected_attribution = {
        "author": "Synthetic Author",
        "work_title": "Synthetic Work",
        "source_location": "chapter 2",
        "license_name": "Declared License",
        "license_uri": "https://example.invalid/license",
        "attribution_text": "Credit Synthetic Author",
    }
    serialized_candidate = candidate.to_dict()
    serialized_evidence = cast(
        list[dict[str, object]], serialized_candidate["evidence"]
    )
    assert serialized_evidence[0]["attribution"] == expected_attribution
    Draft202012Validator(
        TOPIC_CANDIDATE_SCHEMA, format_checker=FormatChecker()
    ).validate(serialized_candidate)

    result = explain_value_topic(candidate, provider=DeterministicFakeProvider())
    output = result.to_dict()
    output_evidence = cast(list[dict[str, object]], output["evidence"])
    assert output_evidence[0]["attribution"] == expected_attribution
    Draft202012Validator(
        EXPLANATION_PACKAGE_SCHEMA, format_checker=FormatChecker()
    ).validate(output)


def test_attribution_rejects_unknown_fields_instead_of_dropping_them() -> None:
    candidate_data = _fixture()
    evidence = cast(list[dict[str, object]], candidate_data["evidence"])
    evidence[0]["attribution"] = {
        "author": "Synthetic Author",
        "rights_status": "cleared",
    }

    try:
        TopicCandidate.from_dict(candidate_data)
    except ValueError as error:
        assert "unsupported fields" in str(error)
    else:
        raise AssertionError("Unknown attribution metadata must not be discarded")


def test_evidence_rejects_top_level_author_and_license_fields() -> None:
    for field in ("author", "license"):
        candidate_data = _fixture()
        evidence = cast(list[dict[str, object]], candidate_data["evidence"])
        evidence[0][field] = "Synthetic declaration"

        try:
            TopicCandidate.from_dict(candidate_data)
        except ValueError as error:
            assert field in str(error)
        else:
            raise AssertionError(
                f"Undeclared evidence field {field!r} must not be discarded"
            )

        try:
            Draft202012Validator(
                TOPIC_CANDIDATE_SCHEMA, format_checker=FormatChecker()
            ).validate(candidate_data)
        except ValidationError:
            pass
        else:
            raise AssertionError(f"The input schema must reject top-level {field!r}")


def test_partial_attribution_round_trips_through_both_schemas() -> None:
    partial_attributions = (
        {"author": "Synthetic Author"},
        {
            "license_name": "Declared License",
            "license_uri": "https://example.invalid/license",
        },
    )
    for attribution in partial_attributions:
        candidate_data = _fixture()
        evidence = cast(list[dict[str, object]], candidate_data["evidence"])
        evidence[0]["attribution"] = attribution

        candidate = TopicCandidate.from_dict(candidate_data)
        candidate_evidence = cast(
            list[dict[str, object]], candidate.to_dict()["evidence"]
        )
        assert candidate_evidence[0]["attribution"] == attribution
        Draft202012Validator(
            TOPIC_CANDIDATE_SCHEMA, format_checker=FormatChecker()
        ).validate(candidate.to_dict())

        result = explain_value_topic(candidate, provider=DeterministicFakeProvider())
        output = result.to_dict()
        output_evidence = cast(list[dict[str, object]], output["evidence"])
        assert output_evidence[0]["attribution"] == attribution
        Draft202012Validator(
            EXPLANATION_PACKAGE_SCHEMA, format_checker=FormatChecker()
        ).validate(output)

        round_tripped = TopicCandidate.from_dict(candidate.to_dict())
        assert round_tripped == candidate


def test_empty_attribution_is_rejected_by_parser_and_input_schema() -> None:
    candidate_data = _fixture()
    evidence = cast(list[dict[str, object]], candidate_data["evidence"])
    evidence[0]["attribution"] = {}
    try:
        TopicCandidate.from_dict(candidate_data)
    except ValueError as error:
        assert "at least one value" in str(error)
    else:
        raise AssertionError("Empty attribution metadata must be rejected")

    try:
        Draft202012Validator(
            TOPIC_CANDIDATE_SCHEMA, format_checker=FormatChecker()
        ).validate(candidate_data)
    except ValidationError as error:
        assert "attribution" in str(error)
    else:
        raise AssertionError("The input schema must reject empty attribution")


def test_fake_provider_satisfies_public_port() -> None:
    factory: ProviderFactory = DeterministicFakeProvider
    provider = factory()
    request = SemanticRequest(candidate=TopicCandidate.from_dict(_fixture()))
    assert provider.name == "deterministic-fake"
    assert provider.generate(request).scenes


def test_unknown_provider_source_fails_closed_qa() -> None:
    claim = EvidenceClaim(text="An unsupported claim.", source_ids=("invented",))
    provider = DeterministicFakeProvider(
        draft=SemanticDraft(
            summary=EvidenceClaim(
                text="A summary constrained by supplied evidence.",
                source_ids=("public-like.lesson",),
            ),
            key_points=(claim,),
            caveats=(
                EvidenceClaim(
                    text="Evidence may be incomplete.",
                    source_ids=("public-like.lesson",),
                ),
            ),
            scenes=(
                DraftScene(
                    narration=claim.text,
                    visual_direction="Show a neutral comparison.",
                    source_ids=claim.source_ids,
                ),
            ),
        )
    )

    result = explain_value_topic(_fixture(), provider=provider)

    assert not result.qa.passed
    assert "known evidence IDs" in " ".join(result.qa.issues)


def test_empty_claim_provenance_fails_closed_qa() -> None:
    candidate = TopicCandidate.from_dict(_fixture())
    claim = EvidenceClaim(text="A claim without provenance.", source_ids=())
    provider = DeterministicFakeProvider(
        draft=SemanticDraft(
            summary=EvidenceClaim(
                text="A summary constrained by supplied evidence.",
                source_ids=candidate.claims[0].source_ids,
            ),
            key_points=(claim,),
            caveats=(
                EvidenceClaim(
                    text="Evidence may be incomplete.",
                    source_ids=candidate.claims[0].source_ids,
                ),
            ),
            scenes=(
                DraftScene(
                    narration=candidate.claims[0].text,
                    visual_direction="Show a neutral comparison.",
                    source_ids=candidate.claims[0].source_ids,
                ),
            ),
        )
    )

    result = explain_value_topic(candidate, provider=provider)

    assert not result.qa.passed
    assert "known evidence IDs" in " ".join(result.qa.issues)


def test_recommendation_and_verbatim_reuse_fail_qa() -> None:
    candidate = TopicCandidate.from_dict(_fixture())
    source = candidate.evidence[0]
    provider = DeterministicFakeProvider(
        draft=SemanticDraft(
            summary=EvidenceClaim(
                text=source.content_summary,
                source_ids=(source.source_id,),
            ),
            key_points=candidate.claims,
            caveats=(),
            scenes=(
                DraftScene(
                    narration="Buy this security for a guaranteed return.",
                    visual_direction="Show a neutral comparison.",
                    source_ids=(source.source_id,),
                ),
            ),
        )
    )

    result = explain_value_topic(candidate, provider=provider)

    assert not result.qa.passed
    assert {check.check_id for check in result.qa.checks if not check.passed} == {
        "advice-language",
        "copyright",
    }


def test_affiliation_claim_and_near_verbatim_reuse_fail_qa() -> None:
    candidate = TopicCandidate.from_dict(_fixture())
    source = candidate.evidence[0]
    provider = DeterministicFakeProvider(
        draft=SemanticDraft(
            summary=EvidenceClaim(
                text=source.content_summary[:-1],
                source_ids=(source.source_id,),
            ),
            key_points=candidate.claims,
            caveats=(),
            scenes=(
                DraftScene(
                    narration="This is an official investor-endorsed explanation.",
                    visual_direction="Show a neutral comparison.",
                    source_ids=(source.source_id,),
                ),
            ),
        )
    )

    result = explain_value_topic(candidate, provider=provider)

    assert not result.qa.passed
    assert {"affiliation-language", "copyright"} <= {
        check.check_id for check in result.qa.checks if not check.passed
    }


def test_candidate_rejects_missing_provenance() -> None:
    candidate = _fixture()
    claims = cast(list[dict[str, object]], candidate["claims"])
    claims[0]["source_ids"] = ["missing"]

    try:
        TopicCandidate.from_dict(candidate)
    except ValueError as error:
        assert "missing from evidence" in str(error)
    else:
        raise AssertionError("Missing provenance must fail")


def test_value_audit_adapter_consumes_public_result_mapping() -> None:
    audit_result: dict[str, object] = {
        "schema_version": "1.0",
        "package_version": "0.1.0",
        "company_id": "SYNTH-001",
        "company_name": "Synthetic Tools",
        "as_of_date": "2026-01-01",
        "models": {
            "lynch": {
                "status": "complete",
                "metrics": {"category": "stalwart", "pe": 14.0},
                "assumption_ids": ["lynch.category.thresholds"],
                "warnings": ["Synthetic warning."],
                "data_gaps": ["Synthetic gap."],
                "provenance_ids": ["filing.synthetic"],
            }
        },
        "assumptions": {"lynch_fast_grower_min": 0.2},
        "warnings": ["Top-level warning."],
        "data_gaps": ["Top-level gap."],
    }

    candidate = candidate_from_value_audit_result(
        audit_result,
        topic_id="synthetic-audit",
        title="Reading a synthetic audit",
        concept="audit evidence",
        model_names=("lynch",),
    )
    result = explain_value_topic(candidate, provider=DeterministicFakeProvider())

    assert candidate.evidence[0].content_kind == "audit_output"
    assert candidate.evidence[0].provenance_ids == ("filing.synthetic",)
    assert "category=stalwart" in candidate.evidence[0].content_summary
    assert "Synthetic warning." in candidate.evidence[0].content_summary
    assert "Synthetic gap." in candidate.evidence[0].content_summary
    assert "lynch_fast_grower_min=0.2" in candidate.evidence[0].content_summary
    assert result.qa.passed


def test_skill_validator_enforces_input_output_binding() -> None:
    module = _load_validator()
    validate_input = cast(Callable[[object], list[str]], module.validate_input)
    validate_output = cast(Callable[..., list[str]], module.validate_output)
    candidate = _fixture()
    result = explain_value_topic(
        candidate, provider=DeterministicFakeProvider()
    ).to_dict()

    assert validate_input(candidate) == []
    assert validate_output(result, explainer_input=candidate) == []
    cast(dict[str, object], cast(list[object], candidate["claims"])[0])[
        "source_ids"
    ] = []
    assert "must cite evidence" in " ".join(validate_input(candidate))
    result["topic_id"] = "different"
    result.pop("provider_name")
    errors = " ".join(validate_output(result, explainer_input=candidate))
    assert "must match" in errors
    assert "provider_name" in errors
