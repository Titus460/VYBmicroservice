"""Offline retraining entrypoint — loads MySQL data and updates ranker / FAISS artifacts."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

import numpy as np

from Model.recsys.config import ARTIFACTS_DIR, FEATURE_NAMES, RANKER_META_PATH
from Model.recsys.db_feedback import (
    backfill_rec_interactions_from_legacy,
    ensure_rec_impressions_table,
    ensure_rec_interactions_table,
    load_interactions_from_cursor,
)
from Model.recsys.features import build_feature_vector
from Model.recsys.flask_adapter import profile_from_sql_row
from Model.recsys.ranker import ConnectionRanker
from Model.recsys.schema import Interaction, InteractionAction
from Model.recsys.two_tower import TwoTowerModel

logger = logging.getLogger(__name__)

POSITIVE_ACTIONS = {
    InteractionAction.LIKE,
    InteractionAction.LIKE_BACK,
    InteractionAction.SEND_REQUEST,
    InteractionAction.ACCEPT_REQUEST,
}
NEGATIVE_ACTIONS = {
    InteractionAction.HIDE_1_DAY,
    InteractionAction.HIDE_1_MONTH,
    InteractionAction.REJECT_REQUEST,
    InteractionAction.WITHDRAW_REQUEST,
    InteractionAction.UNLIKE,
    InteractionAction.SKIP,
}


def _label_for_action(action: InteractionAction) -> int | None:
    if action in POSITIVE_ACTIONS:
        return 1
    if action in NEGATIVE_ACTIONS:
        return 0
    return None


def build_directed_training_samples(
    interactions: List[Interaction],
    profiles: Dict[int, object],
) -> Tuple[np.ndarray, np.ndarray]:
    """Viewer = user_a_id, candidate = user_b_id (preserves wave/hide direction)."""
    rows_x = []
    rows_y = []
    for row in interactions:
        label = _label_for_action(row.action)
        if label is None:
            continue
        viewer = profiles.get(row.user_a_id)
        cand = profiles.get(row.user_b_id)
        if viewer is None or cand is None:
            continue
        rows_x.append(build_feature_vector(viewer, cand))
        rows_y.append(label)
    if not rows_x:
        return np.zeros((0, len(FEATURE_NAMES))), np.array([], dtype=np.int32)
    return np.array(rows_x), np.array(rows_y, dtype=np.int32)


def load_training_user_rows(cursor, limit: int = 5000) -> list:
    cursor.execute(
        """
        SELECT
            p.userId,
            p.profilePic,
            p.selfiePic,
            r.fullName,
            r.email,
            r.firebaseId,
            r.signupType,
            r.authenticationId,
            r.Gender,
            r.Preference,
            r.DOB,
            p.vibes,
            p.vibing,
            r.state,
            r.city,
            p.zodiac_sign,
            p.aesthetic_score,
            0 AS incognito,
            r.countryCode,
            r.phoneNo,
            r.country,
            r.deviceToken,
            p.answer1,
            p.answer2,
            p.answer3,
            p.answer4,
            p.answer5,
            p.answer6,
            p.height,
            p.age_preference,
            p.prompt1question,
            p.prompt1answer,
            p.prompt2question,
            p.prompt2answer
        FROM icebreaker.profile p
        JOIN icebreaker.registration r ON p.userId = r.userId
        WHERE p.profilePic IS NOT NULL AND p.profilePic != ''
          AND p.answer3 IS NOT NULL AND p.answer3 != ''
          AND p.answer4 IS NOT NULL AND p.answer4 != ''
          AND p.prompt1answer IS NOT NULL AND p.prompt1answer != ''
          AND p.prompt2answer IS NOT NULL AND p.prompt2answer != ''
        ORDER BY p.userId DESC
        LIMIT %s
        """,
        (limit,),
    )
    return cursor.fetchall()


def build_profiles_for_training(service, cursor, limit: int = 5000) -> Dict[int, object]:
    from Model.recsys.schema import UserProfile

    rows = load_training_user_rows(cursor, limit=limit)
    if not rows:
        return {}

    user_ids = [r[0] for r in rows]
    coords_map = service._batch_fetch_coords(cursor, user_ids)
    tag_counts_map = service._batch_get_user_tag_counts(cursor, user_ids)
    places_map = service._batch_get_places(cursor, user_ids)

    profiles: Dict[int, UserProfile] = {}
    for row in rows:
        profiles[row[0]] = profile_from_sql_row(
            service,
            row,
            coords_map,
            tag_counts_map=tag_counts_map,
            places_map=places_map,
        )
    return profiles


def retrain_from_mysql(
    service,
    cursor,
    *,
    backfill_legacy: bool = True,
    since_days: int | None = None,
    profile_limit: int = 5000,
    min_samples: int = 20,
) -> dict:
    import os

    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    ensure_rec_interactions_table(cursor)
    ensure_rec_impressions_table(cursor)

    backfill_count = 0
    if backfill_legacy:
        backfill_count = backfill_rec_interactions_from_legacy(cursor)
        service.db.conn.commit()

    since = None
    if since_days is not None:
        since = datetime.now(timezone.utc) - timedelta(days=since_days)

    interactions = load_interactions_from_cursor(cursor, since=since)
    profiles = build_profiles_for_training(service, cursor, limit=profile_limit)

    X, y = build_directed_training_samples(interactions, profiles)
    summary = {
        "samples": int(len(y)),
        "positives": int(y.sum()) if len(y) else 0,
        "positive_rate": float(y.mean()) if len(y) else 0.0,
    }

    ranker_result = {
        "trained": False,
        "samples": int(len(y)),
        "positives": int(y.sum()) if len(y) else 0,
        "profiles": len(profiles),
        "backfill_rows": backfill_count,
    }

    ranker = ConnectionRanker()
    if len(y) >= min_samples and len(set(y.tolist())) > 1:
        try:
            import xgboost as xgb

            model = xgb.XGBClassifier(
                n_estimators=120,
                max_depth=5,
                learning_rate=0.06,
                subsample=0.9,
                colsample_bytree=0.9,
                eval_metric="logloss",
            )
            model.fit(X, y)
            ranker._model = model
            ranker.save(
                meta={
                    "feature_names": FEATURE_NAMES,
                    "samples": int(len(y)),
                    "positives": int(y.sum()),
                    "trained_at": datetime.now(timezone.utc).isoformat(),
                    "since_days": since_days,
                }
            )
            ranker_result["trained"] = True
            ranker_result["model_path"] = ranker._model is not None
        except Exception as exc:
            logger.exception("XGBoost training failed")
            ranker_result["error"] = str(exc)
    else:
        ranker_result["reason"] = (
            f"need >={min_samples} labelled samples and both classes; got {len(y)}"
        )

    tower = TwoTowerModel()
    tower.set_profiles(profiles)
    faiss_users = tower.rebuild_faiss(profiles)
    tower.save()

    result = {
        "ranker": ranker_result,
        "two_tower": {"faiss_index_users": faiss_users, "saved": faiss_users > 0},
        "interactions_loaded": len(interactions),
        "label_summary": summary,
    }

    with open(RANKER_META_PATH.replace("connection_ranker_meta.json", "last_train_report.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)

    return result
