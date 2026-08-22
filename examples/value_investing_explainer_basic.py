from trinity_agentic_kit.value_explainer import (
    DeterministicFakeProvider,
    explain_value_topic,
)

candidate = {
    "schema_version": "1.0",
    "topic_id": "synthetic-cash-flow",
    "title": "Cash flow in plain language",
    "concept": "cash generation",
    "audience": "general learners",
    "objective": "Separate reported earnings from cash generation.",
    "evidence": [
        {
            "source_id": "synthetic.note",
            "title": "Synthetic educational note",
            "source_type": "educational_note",
            "as_of_date": "2026-01-01",
            "content_summary": (
                "Reported earnings and cash generation can differ because accounting "
                "recognition and cash movement do not always happen together."
            ),
            "content_kind": "public_domain_like",
        }
    ],
    "claims": [
        {
            "text": (
                "Earnings and cash generation answer related but different questions."
            ),
            "source_ids": ["synthetic.note"],
        }
    ],
}

result = explain_value_topic(candidate, provider=DeterministicFakeProvider())
print(result.to_dict())
