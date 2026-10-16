"""Full recsys pipeline orchestrator."""

from __future__ import annotations

from typing import Dict, List, Optional

import numpy as np

from Model.recsys.config import RANKING_TOP_K, RETRIEVAL_TOP_K
from Model.recsys.explain import build_match_explanation
from Model.recsys.features import build_feature_dict
from Model.recsys.ranker import ConnectionRanker
from Model.recsys.reciprocal import reciprocal_batch
from Model.recsys.rerank import PerUserBandit, final_rerank
from Model.recsys.schema import UserProfile
from Model.recsys.two_tower import TwoTowerModel


class RecsysPipeline:
    VERSION = "recsys_v1"

    def __init__(self, profiles: Dict[int, UserProfile], store):
        self.profiles = profiles
        self.store = store
        self.two_tower = TwoTowerModel()
        self.two_tower.set_profiles(profiles)
        self.ranker = ConnectionRanker()
        self.bandit = PerUserBandit()

    def run_feed(self, viewer_id: int, retrieval_k: int = RETRIEVAL_TOP_K, ranking_k: int = RANKING_TOP_K) -> dict:
        viewer = self.profiles.get(viewer_id)
        if not viewer:
            return {"status": "error", "message": f"viewer {viewer_id} not found"}

        hits = self.two_tower.query_nearest(viewer, top_k=retrieval_k, exclude_ids={viewer_id})
        pool_ids = [uid for uid, _ in hits]
        pool = {uid: self.profiles[uid] for uid in pool_ids if uid in self.profiles}

        ranked_raw = self.ranker.rank(viewer, pool, top_k=ranking_k)
        embeddings = {uid: self.two_tower.embed_user(p) for uid, p in pool.items()}
        recip = reciprocal_batch(viewer, [uid for uid, _, _ in ranked_raw], embeddings, self.two_tower.embed_user)

        merged = []
        for uid, score, bd in ranked_raw:
            r = recip.get(uid, 0.0)
            combined = 0.75 * score + 0.25 * r
            merged.append((uid, combined, {**bd, "reciprocal": r, "xgb_score": score}))

        reranked = final_rerank(merged, embeddings, self.bandit, viewer_id, top_k=ranking_k)
        feed = []
        for rank, (uid, score, bd) in enumerate(reranked, start=1):
            prof = self.profiles[uid]
            feed.append({
                "rank": rank,
                "user_id": uid,
                "score": round(float(score), 4),
                "reciprocal": round(float(bd.get("reciprocal", 0.0)), 4),
                "profile_summary": {
                    "interests": prof.interests[:5],
                    "age": prof.age,
                    "intent": prof.intent,
                },
                "feature_breakdown": bd,
            })

        return {
            "status": "ok",
            "viewer_id": viewer_id,
            "pipeline_version": self.VERSION,
            "retrieval_pool": len(pool_ids),
            "feed": feed,
        }

    def explain(self, viewer_id: int, candidate_id: int) -> dict:
        viewer = self.profiles.get(viewer_id)
        cand = self.profiles.get(candidate_id)
        if not viewer or not cand:
            return {"error": "not found"}
        bd = build_feature_dict(viewer, cand)
        p = self.ranker.predict_proba(viewer, cand)
        shap = {k: round(v * p, 4) for k, v in bd.items()}
        return {
            "viewer_id": viewer_id,
            "candidate_id": candidate_id,
            "p_connection": round(p, 4),
            "shap_contributions": shap,
            "explanation": build_match_explanation(bd),
        }
