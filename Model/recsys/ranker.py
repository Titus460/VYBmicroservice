"""XGBoost connection ranker with heuristic fallback."""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

import numpy as np

from Model.recsys.config import (
    FEATURE_NAMES,
    HEURISTIC_FALLBACK_WEIGHTS,
    LEGACY_RANKER_PATH,
    RANKER_META_PATH,
    RANKER_MODEL_PATH,
)
from Model.recsys.features import build_feature_dict, build_feature_vector
from Model.recsys.schema import UserProfile


class ConnectionRanker:
    def __init__(self):
        self._model = None
        self._load()

    @property
    def is_trained(self) -> bool:
        return self._model is not None

    def _load(self) -> None:
        path = RANKER_MODEL_PATH if os.path.exists(RANKER_MODEL_PATH) else LEGACY_RANKER_PATH
        if not os.path.exists(path):
            return
        try:
            import xgboost as xgb
            self._model = xgb.XGBClassifier()
            self._model.load_model(path)
        except Exception:
            self._model = None

    def predict_proba(self, viewer: UserProfile, candidate: UserProfile) -> float:
        vec = build_feature_vector(viewer, candidate)
        if self._model is not None:
            try:
                proba = self._model.predict_proba(vec.reshape(1, -1))[0]
                return float(proba[1] if len(proba) > 1 else proba[0])
            except Exception:
                pass
        fd = build_feature_dict(viewer, candidate)
        score = sum(HEURISTIC_FALLBACK_WEIGHTS.get(k, 0.0) * fd.get(k, 0.0) for k in FEATURE_NAMES)
        return float(min(1.0, max(0.0, score)))

    def rank(
        self,
        viewer: UserProfile,
        candidates: Dict[int, UserProfile],
        top_k: int = 50,
    ) -> List[Tuple[int, float, dict]]:
        scored = []
        for uid, cand in candidates.items():
            if uid == viewer.user_id:
                continue
            fd = build_feature_dict(viewer, cand)
            score = self.predict_proba(viewer, cand)
            scored.append((uid, score, fd))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def save(self, path: Optional[str] = None, meta: Optional[dict] = None) -> None:
        if self._model is None:
            return
        out = path or RANKER_MODEL_PATH
        os.makedirs(os.path.dirname(out), exist_ok=True)
        self._model.save_model(out)
        if meta is not None:
            with open(RANKER_META_PATH, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)
