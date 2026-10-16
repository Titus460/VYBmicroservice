"""Final re-rank: exploration bandit + MMR diversity."""

from __future__ import annotations

import json
import os
import random
from typing import Dict, List, Tuple

from Model.recsys.config import BANDIT_STATE_PATH, DIVERSITY_LAMBDA, EXPLORATION_EPSILON


class PerUserBandit:
    def __init__(self):
        self._state: Dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if os.path.exists(BANDIT_STATE_PATH):
            try:
                with open(BANDIT_STATE_PATH, encoding="utf-8") as f:
                    self._state = json.load(f)
            except Exception:
                self._state = {}

    def save(self) -> None:
        os.makedirs(os.path.dirname(BANDIT_STATE_PATH), exist_ok=True)
        with open(BANDIT_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(self._state, f)

    def update(self, user_id: int, action: str) -> None:
        key = str(user_id)
        row = self._state.setdefault(key, {"pulls": 0, "reward": 0.0})
        row["pulls"] += 1
        if action in ("like", "like_back", "accept_request"):
            row["reward"] += 1.0

    def epsilon(self, user_id: int) -> float:
        return EXPLORATION_EPSILON


def final_rerank(
    scored: List[Tuple[int, float, dict]],
    embeddings: Dict[int, object],
    bandit: PerUserBandit,
    viewer_id: int,
    top_k: int = 50,
) -> List[Tuple[int, float, dict]]:
    if not scored:
        return []
    if random.random() < bandit.epsilon(viewer_id):
        pool = list(scored)
        random.shuffle(pool)
        return pool[:top_k]

    selected: List[Tuple[int, float, dict]] = []
    remaining = list(scored)
    while remaining and len(selected) < top_k:
        best_idx = 0
        best_val = -1e9
        for i, (uid, score, bd) in enumerate(remaining):
            penalty = 0.0
            uid_emb = embeddings.get(uid)
            for sel_uid, _, _ in selected:
                sel_emb = embeddings.get(sel_uid)
                if uid_emb is not None and sel_emb is not None:
                    try:
                        import numpy as np
                        penalty = max(penalty, float(np.dot(uid_emb, sel_emb)))
                    except Exception:
                        pass
            val = score - DIVERSITY_LAMBDA * penalty
            if val > best_val:
                best_val = val
                best_idx = i
        selected.append(remaining.pop(best_idx))
    return selected
