"""Explainable five-stage hype-and-maturity inference for ARGUS."""

from __future__ import annotations

from math import exp
from typing import Any


PHASES = (
    ("innovation_trigger", "Innovation Trigger"),
    ("peak_of_inflated_expectations", "Peak of Inflated Expectations"),
    ("trough_of_disillusionment", "Trough of Disillusionment"),
    ("slope_of_enlightenment", "Slope of Enlightenment"),
    ("plateau_of_productivity", "Plateau of Productivity"),
)


def _clip(value: float) -> float:
    return max(0.0, min(100.0, value))


def _softmax(scores: dict[str, float]) -> dict[str, float]:
    ceiling = max(scores.values())
    scaled = {key: exp((value - ceiling) / 7.5) for key, value in scores.items()}
    total = sum(scaled.values())
    return {key: round(value / total, 4) for key, value in scaled.items()}


def infer(features: dict[str, Any], previous_phase: str | None = None) -> dict[str, Any]:
    """Return a transparent phase estimate from normalized 0–100 feature values.

    This intentionally uses interpretable scoring rather than an opaque trained model.
    Adjacent state continuity gives modest preference to a stable/next lifecycle phase.
    """

    attention = _clip(features["attention"])
    expectations = _clip(features["expectations"])
    disappointment = _clip(features["disappointment"])
    adoption = _clip(features["adoption"])
    maturity = _clip(features["maturity"])
    momentum = max(-100.0, min(100.0, features["momentum"]))
    momentum_available = features.get("momentum_available", True) is not False
    positive_momentum = max(momentum, 0) if momentum_available else 0
    negative_momentum = max(-momentum, 0) if momentum_available else 0
    stable_momentum = max(35 - abs(momentum), 0) if momentum_available else 0
    hype_gap = expectations - adoption

    scores = {
        "innovation_trigger": (
            0.46 * positive_momentum + 0.22 * attention + 0.18 * expectations
            + 0.24 * (100 - adoption) + 0.12 * (100 - maturity) - 0.24 * disappointment
        ),
        "peak_of_inflated_expectations": (
            0.42 * attention + 0.57 * expectations + 0.56 * max(hype_gap, 0)
            + 0.20 * positive_momentum - 0.26 * adoption - 0.18 * maturity
        ),
        "trough_of_disillusionment": (
            0.63 * disappointment + 0.30 * negative_momentum
            + 0.24 * max(45 - attention, 0) + 0.15 * max(55 - adoption, 0)
            - 0.17 * maturity
        ),
        "slope_of_enlightenment": (
            0.50 * adoption + 0.56 * maturity + 0.22 * positive_momentum
            + 0.24 * max(35 - abs(hype_gap), 0) + 0.10 * attention
            - 0.27 * disappointment
        ),
        "plateau_of_productivity": (
            0.61 * adoption + 0.64 * maturity + 0.20 * stable_momentum
            + 0.14 * max(35 - abs(hype_gap), 0) - 0.17 * attention - 0.20 * disappointment
        ),
    }

    phase_keys = [phase[0] for phase in PHASES]
    if previous_phase in phase_keys:
        prior_index = phase_keys.index(previous_phase)
        for index, key in enumerate(phase_keys):
            distance = abs(index - prior_index)
            if distance == 0:
                scores[key] += 5.5
            elif distance == 1:
                scores[key] += 2.0
            elif distance > 2:
                scores[key] -= 6.0

    probabilities = _softmax(scores)
    selected_key = max(probabilities, key=probabilities.get)
    selected_label = dict(PHASES)[selected_key]
    ordered = sorted(probabilities.values(), reverse=True)
    separation = ordered[0] - ordered[1]
    coverage = float(features.get("coverage", 85))
    conflict = min(35.0, abs(hype_gap) * 0.25 + disappointment * 0.18)
    # A decisive model output is not enough on its own. Coverage caps confidence
    # so sparse public data cannot become a falsely certain lifecycle label.
    raw_confidence = 30 + coverage * 0.35 + separation * 35 - conflict * 0.22
    confidence_score = min(_clip(raw_confidence), coverage * 0.95)
    confidence_band = "high" if confidence_score >= 72 else "moderate" if confidence_score >= 52 else "low"

    previous_index = phase_keys.index(previous_phase) if previous_phase in phase_keys else None
    selected_index = phase_keys.index(selected_key)
    if previous_index is None or selected_index == previous_index:
        movement = "stable"
    elif selected_index > previous_index:
        movement = "advancing"
    else:
        movement = "regressing"

    drivers = [
        {"feature": "Expectations", "value": round(expectations), "effect": "raises the hype gap" if hype_gap > 0 else "is below adoption"},
        {"feature": "Verified adoption", "value": round(adoption), "effect": "anchors the estimate in real-world use"},
        {"feature": "Operational maturity", "value": round(maturity), "effect": "signals repeatability and governance"},
        {"feature": "Disappointment", "value": round(disappointment), "effect": "captures setbacks and reliability concerns"},
    ]
    summary_map = {
        "innovation_trigger": "Technical attention is rising, while verified use and operating maturity are still early.",
        "peak_of_inflated_expectations": "Attention and ambitious claims are outpacing independently verified adoption.",
        "trough_of_disillusionment": "Setbacks and revised expectations are outweighing momentum, though useful work may continue.",
        "slope_of_enlightenment": "Independent adoption and operating practice are growing as expectations become more grounded.",
        "plateau_of_productivity": "Adoption and maturity are sustained across the ecosystem, with less dependence on media excitement.",
    }
    return {
        "phase": selected_key,
        "phase_label": selected_label,
        "probabilities": probabilities,
        "confidence_score": round(confidence_score),
        "confidence_band": confidence_band,
        "movement": movement,
        "hype_gap": round(hype_gap),
        "summary": summary_map[selected_key],
        "drivers": drivers,
    }
