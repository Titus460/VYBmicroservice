"""Reciprocal interest scoring."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from Model.recsys.schema import UserProfile


def reciprocal_score(viewer_emb: np.ndarray, cand_emb: np.ndarray) -> float:
    if viewer_emb is None or cand_emb is None:
        return 0.0
    a = np.asarray(viewer_emb, dtype=np.float32)
    b = np.asarray(cand_emb, dtype=np.float32)
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na <= 0 or nb <= 0:
        return 0.0
    sim_ab = float(np.dot(a, b) / (na * nb))
    sim_ba = sim_ab
    return max(0.0, min(1.0, (sim_ab + sim_ba) / 2.0))


def reciprocal_batch(
    viewer: UserProfile,
    candidate_ids: List[int],
    embeddings: Dict[int, np.ndarray],
    embed_fn,
) -> Dict[int, float]:
    viewer_emb = embed_fn(viewer)
    out = {}
    for uid in candidate_ids:
        cand_emb = embeddings.get(uid)
        if cand_emb is None:
            out[uid] = 0.0
        else:
            out[uid] = reciprocal_score(viewer_emb, cand_emb)
    return out
