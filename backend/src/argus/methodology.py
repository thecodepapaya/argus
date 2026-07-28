"""Versioned, user-facing description of the methodology implemented by ARGUS."""

from __future__ import annotations

from typing import Any


METHODOLOGY_VERSION = "public-metadata-explainable-v5"

GLOSSARY: dict[str, dict[str, str]] = {
    "attention": {
        "label": "Attention",
        "definition": "Relative volume of attributable public discussion and project activity. Attention measures visibility, not quality or adoption.",
    },
    "expectations": {
        "label": "Expectations",
        "definition": "Strength of forward-looking claims about impact, replacement, growth, or future capability in the collected evidence.",
    },
    "disappointment": {
        "label": "Disappointment",
        "definition": "Evidence of setbacks, limitations, security or reliability incidents, abandonment, and downward revisions to earlier claims.",
    },
    "adoption": {
        "label": "Verified adoption",
        "definition": "Public evidence that people or organizations are using the technology. Repository activity is only a proxy and is not treated as proof of production use.",
    },
    "maturity": {
        "label": "Operational maturity",
        "definition": "Evidence of repeatability, maintenance, governance, security practices, stable interfaces, integrations, and production operating knowledge.",
    },
    "momentum": {
        "label": "Momentum",
        "definition": "Direction of completed weekly signals compared with their trailing baseline. ARGUS withholds it while the current week is still settling, rather than treating incomplete activity as a contraction.",
    },
    "coverage": {
        "label": "Evidence coverage",
        "definition": "Share of configured public-source families that completed for this estimate. It is not the percentage of the entire internet that ARGUS observed.",
    },
    "hype_gap": {
        "label": "Hype gap",
        "definition": "Expectations score minus verified-adoption score. A positive value means public claims are running ahead of observed use; it is not a forecast of success or failure.",
    },
    "confidence": {
        "label": "Confidence",
        "definition": "A bounded indication of evidence coverage and separation between competing lifecycle phases. It does not represent statistical accuracy.",
    },
    "phase": {
        "label": "Lifecycle phase",
        "definition": "The most supported qualitative stage from ARGUS's five-stage scoring model. The result is an estimate, not an official Gartner classification.",
    },
    "evidence_weight": {
        "label": "Evidence weight",
        "definition": "Relative influence assigned from source class and claim context. It expresses analytical priority, not the probability that a source is true.",
    },
}

PHASES = (
    ("innovation_trigger", "Innovation Trigger", "A category is forming and attention is rising while adoption and operating knowledge remain early."),
    ("peak_of_inflated_expectations", "Peak of Inflated Expectations", "Ambitious claims and attention substantially outpace independently observed adoption."),
    ("trough_of_disillusionment", "Trough of Disillusionment", "Setbacks and revised expectations outweigh momentum, even if useful work continues."),
    ("slope_of_enlightenment", "Slope of Enlightenment", "Adoption and operating practice grow while expectations become more grounded."),
    ("plateau_of_productivity", "Plateau of Productivity", "Adoption and maturity are sustained with less dependence on media attention."),
)


def public_methodology() -> dict[str, Any]:
    """Return the canonical public contract used by API documentation and tooltips."""
    dimensions = []
    for key in ("attention", "expectations", "disappointment", "adoption", "maturity", "momentum", "coverage"):
        item = GLOSSARY[key]
        dimensions.append({
            "id": key,
            **item,
            "range": "-100 to 100" if key == "momentum" else "0 to 100",
        })
    return {
        "version": METHODOLOGY_VERSION,
        "approach": "Interpretable weighted scoring with modest adjacent-phase continuity; no LLM assigns lifecycle phases.",
        "dimensions": dimensions,
        "derived_metrics": [{"id": "hype_gap", **GLOSSARY["hype_gap"], "formula": "expectations - adoption"}],
        "phases": [{"id": key, "label": label, "definition": definition} for key, label, definition in PHASES],
        "confidence": GLOSSARY["confidence"],
        "glossary": GLOSSARY,
        "limitations": [
            "Public signals are incomplete and can overrepresent English-language and open-source activity.",
            "Repository activity is a maturity and attention proxy, not direct production-adoption proof.",
            "Historical estimates are reconstructed from the evidence available to the collector and are not official Gartner research.",
        ],
        "affiliation": "ARGUS is independent and is not affiliated with Gartner.",
    }
