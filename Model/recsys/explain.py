"""Human-readable match explanations."""

from typing import Dict, List, Optional, Set


def _top_factors(breakdown: dict, limit: int = 3) -> List[str]:
    labels = {
        "proximity_score": "You're nearby",
        "lifestyle_similarity": "Similar hangout spots",
        "age_gap": "Age preference match",
        "shared_interest_count": "Shared vibes",
        "intent_compat": "Compatible dating goals",
        "prompt1_sim": "Similar prompt answers",
        "prompt2_sim": "Similar prompt answers",
        "checkin_overlap": "Same places checked in",
        "comm_style_compat": "Communication style fit",
    }
    ranked = sorted(
        ((k, v) for k, v in breakdown.items() if isinstance(v, (int, float))),
        key=lambda x: x[1],
        reverse=True,
    )
    out = []
    for key, val in ranked:
        if val >= 0.45 and key in labels:
            out.append(labels[key])
        if len(out) >= limit:
            break
    return out


def build_match_explanation(
    breakdown: dict,
    user_row=None,
    my_vibes_set: Optional[Set[str]] = None,
    wave_status: str = "no_wave",
    extras: Optional[dict] = None,
) -> dict:
    factors = _top_factors(breakdown)
    headline = factors[0] if factors else "Recommended for you"
    return {
        "headline": headline,
        "factors": factors,
        "wave_status": wave_status,
        "breakdown": breakdown,
        "extras": extras or {},
    }
