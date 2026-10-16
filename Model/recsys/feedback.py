"""Feedback loop: retrain ranker and two-tower from interactions."""

from __future__ import annotations

from typing import Dict, List, Tuple

import numpy as np

from Model.recsys.config import ARTIFACTS_DIR, FEATURE_NAMES
from Model.recsys.features import build_feature_vector
from Model.recsys.labels import label_from_interactions_weighted
from Model.recsys.ranker import ConnectionRanker
from Model.recsys.schema import UserProfile
from Model.recsys.two_tower import TwoTowerModel


def retrain_from_store(store, profiles: Dict[int, UserProfile]) -> dict:
    import os
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)

    interactions = store.list_all()
    labeled = label_from_interactions_weighted(interactions)

    X = []
    y = []
    for (a, b), label in labeled.items():
        if a not in profiles or b not in profiles:
            continue
        viewer = profiles[a]
        cand = profiles[b]
        X.append(build_feature_vector(viewer, cand))
        y.append(label)
        X.append(build_feature_vector(profiles[b], profiles[a]))
        y.append(label)

    ranker_result = {"trained": False, "samples": len(y)}
    ranker = ConnectionRanker()
    if len(y) >= 20 and len(set(y)) > 1:
        try:
            import xgboost as xgb
            model = xgb.XGBClassifier(
                n_estimators=80,
                max_depth=4,
                learning_rate=0.08,
                eval_metric="logloss",
            )
            model.fit(np.array(X), np.array(y))
            ranker._model = model
            ranker.save(meta={
                "feature_names": FEATURE_NAMES,
                "samples": len(y),
                "positives": int(sum(y)),
            })
            ranker_result = {"trained": True, "samples": len(y), "positives": int(sum(y))}
        except Exception as exc:
            ranker_result = {"trained": False, "error": str(exc), "samples": len(y)}

    tower = TwoTowerModel()
    tower.set_profiles(profiles)
    faiss_users = tower.rebuild_faiss(profiles)
    tower.save()

    return {
        "ranker": ranker_result,
        "two_tower": {"saved": True},
        "faiss_index_users": faiss_users,
    }
