"""Learned heuristic weights from behaviour profile."""

from __future__ import annotations

from typing import Dict, Optional

DEFAULT_WEIGHTS = {
    "proximity": 0.28,
    "lifestyle": 0.10,
    "age": 0.08,
    "interest": 0.14,
    "intent": 0.12,
    "prompt": 0.14,
    "checkin_overlap": 0.08,
    "comm": 0.06,
}

MIN_INTERACTIONS = 10


def get_heuristic_weights(dynamic_weights: Optional[dict]) -> dict:
    if not dynamic_weights:
        return DEFAULT_WEIGHTS.copy()
    merged = DEFAULT_WEIGHTS.copy()
    merged.update(dynamic_weights)
    return merged


def get_ensemble_weights(behaviour_profile: dict) -> dict:
    return get_heuristic_weights(behaviour_profile.get("dynamic_weights"))


def learn_all_weights(profile: dict) -> dict:
    counts = profile.get("interaction_counts") or {}
    total = sum(counts.values()) if counts else 0
    if total < MIN_INTERACTIONS:
        return DEFAULT_WEIGHTS.copy()
    weights = DEFAULT_WEIGHTS.copy()
    taste = profile.get("taste_vibes") or {}
    skip = profile.get("skip_vibes") or {}
    if taste:
        weights["interest"] = min(0.22, weights["interest"] + 0.04)
    if skip:
        weights["interest"] = max(0.08, weights["interest"] - 0.03)
    if profile.get("skip_intent"):
        weights["intent"] = min(0.18, weights["intent"] + 0.03)
    s = sum(weights.values()) or 1.0
    return {k: v / s for k, v in weights.items()}
