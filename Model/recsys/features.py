"""Feature engineering for connection ranking."""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from Model.recsys.checkin_features import checkin_overlap, lifestyle_similarity
from Model.recsys.compat import comm_style_compat, intent_compat
from Model.recsys.config import FEATURE_NAMES, ST_MODEL_NAME
from Model.recsys.schema import UserProfile

_st_model = None


def _get_st_model():
    global _st_model
    if _st_model is None:
        try:
            from sentence_transformers import SentenceTransformer
            _st_model = SentenceTransformer(ST_MODEL_NAME)
        except Exception:
            _st_model = False
    return _st_model if _st_model is not False else None


def _cosine(a: Optional[List[float]], b: Optional[List[float]]) -> float:
    if not a or not b:
        return 0.0
    va = np.array(a, dtype=np.float32)
    vb = np.array(b, dtype=np.float32)
    na = np.linalg.norm(va)
    nb = np.linalg.norm(vb)
    if na <= 0 or nb <= 0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def proximity_score(
    my_lat: Optional[float],
    my_lng: Optional[float],
    cand_lat: Optional[float],
    cand_lng: Optional[float],
    falloff_km: float = 25.0,
) -> float:
    if None in (my_lat, my_lng, cand_lat, cand_lng):
        return 0.0
    dlat = math.radians(cand_lat - my_lat)
    dlng = math.radians(cand_lng - my_lng)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(my_lat))
        * math.cos(math.radians(cand_lat))
        * math.sin(dlng / 2) ** 2
    )
    km = 6371.0 * 2 * math.asin(min(1.0, math.sqrt(a)))
    return max(0.0, 1.0 - km / falloff_km)


def shared_interest_count(viewer: UserProfile, candidate: UserProfile) -> float:
    a = {i.lower() for i in viewer.interests}
    b = {i.lower() for i in candidate.interests}
    if not a or not b:
        return 0.0
    return float(len(a & b))


def age_gap_score(viewer: UserProfile, candidate: UserProfile) -> float:
    if viewer.age is None or candidate.age is None:
        return 0.5
    gap = abs(viewer.age - candidate.age)
    return max(0.0, 1.0 - gap / 15.0)


def build_feature_dict(viewer: UserProfile, candidate: UserProfile) -> Dict[str, float]:
    return {
        "proximity_score": proximity_score(viewer.lat, viewer.lng, candidate.lat, candidate.lng),
        "shared_interest_count": shared_interest_count(viewer, candidate),
        "comm_style_compat": comm_style_compat(viewer.comm_idx, candidate.comm_idx),
        "intent_compat": intent_compat(viewer.intent_idx, candidate.intent_idx),
        "prompt1_sim": _cosine(viewer.emb1, candidate.emb1),
        "prompt2_sim": _cosine(viewer.emb2, candidate.emb2),
        "age_gap": age_gap_score(viewer, candidate),
        "lifestyle_similarity": lifestyle_similarity(viewer.tag_counts, candidate.tag_counts),
        "checkin_overlap": checkin_overlap(viewer.places, candidate.places),
    }


def build_feature_vector(viewer: UserProfile, candidate: UserProfile) -> np.ndarray:
    fd = build_feature_dict(viewer, candidate)
    return np.array([fd[name] for name in FEATURE_NAMES], dtype=np.float32)


def profile_input_vector(profile: UserProfile) -> np.ndarray:
    parts = []
    parts.extend([profile.age or 25, profile.comm_idx or 0, profile.intent_idx or 0])
    parts.extend([len(profile.interests), len(profile.places)])
    if profile.emb1:
        parts.extend(profile.emb1[:16])
    else:
        parts.extend([0.0] * 16)
    return np.array(parts[:21], dtype=np.float32)
