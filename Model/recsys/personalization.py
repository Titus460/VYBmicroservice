"""Blend ML scores with per-user behaviour profile."""

from __future__ import annotations

from typing import Dict, Optional


def blend_with_personalization(
    xgb_score: float,
    behaviour_profile: dict,
    feature_breakdown: dict,
) -> float:
    weights = behaviour_profile.get("dynamic_weights") or {}
    boost = 0.0
    taste = behaviour_profile.get("taste_vibes") or {}
    skip = behaviour_profile.get("skip_vibes") or {}
    vibes_overlap = feature_breakdown.get("shared_interest_count", 0.0)
    if taste and vibes_overlap > 0:
        boost += min(0.08, 0.02 * vibes_overlap)
    if skip and vibes_overlap > 0:
        boost -= min(0.06, 0.015 * vibes_overlap)
    proximity_w = float(weights.get("proximity", weights.get("proximity_score", 0.0)) or 0.0)
    if proximity_w > 0.2:
        boost += 0.03 * feature_breakdown.get("proximity_score", 0.0)
    return max(0.0, min(1.0, xgb_score + boost))
