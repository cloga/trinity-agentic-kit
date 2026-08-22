"""Evidence-bound, provider-neutral value-investing explanations."""

from .audit_adapter import candidate_from_value_audit_result
from .contracts import (
    DISCLAIMER,
    EXPLAINER_INPUT_SCHEMA_VERSION,
    EXPLAINER_OUTPUT_SCHEMA_VERSION,
    EXPLANATION_PACKAGE_SCHEMA,
    PACKAGE_VERSION,
    TOPIC_CANDIDATE_SCHEMA,
    EvidenceClaim,
    EvidenceSource,
    ExplanationPackage,
    QACheck,
    QAResult,
    ScriptScene,
    TopicCandidate,
)
from .orchestrator import explain_value_topic, validate_explanation_package
from .providers import (
    DeterministicFakeProvider,
    DraftScene,
    SemanticDraft,
    SemanticGenerationPort,
    SemanticRequest,
)

__all__ = [
    "DISCLAIMER",
    "EXPLAINER_INPUT_SCHEMA_VERSION",
    "EXPLAINER_OUTPUT_SCHEMA_VERSION",
    "EXPLANATION_PACKAGE_SCHEMA",
    "PACKAGE_VERSION",
    "TOPIC_CANDIDATE_SCHEMA",
    "DeterministicFakeProvider",
    "DraftScene",
    "EvidenceClaim",
    "EvidenceSource",
    "ExplanationPackage",
    "QACheck",
    "QAResult",
    "ScriptScene",
    "SemanticDraft",
    "SemanticGenerationPort",
    "SemanticRequest",
    "TopicCandidate",
    "candidate_from_value_audit_result",
    "explain_value_topic",
    "validate_explanation_package",
]
