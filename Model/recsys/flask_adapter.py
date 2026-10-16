"""
Flask / MySQL adapter — connects get_user_list_offline to Amazon Personalize.

SQL still builds the eligible candidate pool (blocks, hides, gender, age, etc.).
Personalize ranks that pool using behavioural data trained in AWS.
If Personalize returns no scores, SQL fallback ranks that same pool: nearer
latitude/longitude first, using vibes, answer3, answer4, prompt1answer, and
prompt2answer only to reorder people within about 5km.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Dict, List, Optional, Set, Tuple

from Model.recsys.compat import COMM_STYLE_MAP, INTENT_MAP, comm_style_compat, intent_compat
from Model.recsys.config import RANKING_TOP_K
from Model.recsys.feed_cache import get_offline_feed_cache
from Model.recsys.offline_feed_dashboard import record_offline_feed_event
from Model.recsys.personalize_client import get_personalize_scores, is_personalize_enabled
from Model.recsys.schema import UserProfile

logger = logging.getLogger(__name__)


def _parse_vibes(vibes_raw: Optional[str]) -> List[str]:
    if not vibes_raw:
        return []
    return [v.strip() for v in vibes_raw.split(",") if v.strip()]


# A full profile match is worth just under this many kilometres, so a nearer
# user still ranks first once the gap is larger than this.
_SQL_FALLBACK_MAX_KM = 200.0
_SQL_FALLBACK_PROFILE_KM = 5.0


def _norm_text(val) -> str:
    if val is None:
        return ""
    if isinstance(val, (bytes, bytearray)):
        return val.decode("utf-8", errors="replace").strip().lower()
    return str(val).strip().lower()


def _as_coords(lat, lng) -> Optional[Tuple[float, float]]:
    if lat is None or lng is None or lat == "" or lng == "":
        return None
    try:
        return (float(lat), float(lng))
    except (TypeError, ValueError):
        return None


def _jaccard(left: Set[str], right: Set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


def _vibe_similarity(mine, theirs) -> float:
    mine_set = {part.strip() for part in _norm_text(mine).split(",") if part.strip()}
    their_set = {part.strip() for part in _norm_text(theirs).split(",") if part.strip()}
    return _jaccard(mine_set, their_set)


def _answer_similarity(mine, theirs, index_map: dict, compat_fn) -> float:
    left = _norm_text(mine)
    right = _norm_text(theirs)
    if not left or not right:
        return 0.0
    left_idx = index_map.get(left)
    right_idx = index_map.get(right)
    if left_idx is not None and right_idx is not None:
        return float(compat_fn(left_idx, right_idx))
    return 1.0 if left == right else 0.0


def _prompt_similarity(service, my_emb, their_emb, my_text, their_text) -> float:
    if my_emb is not None and their_emb is not None:
        sim = service._cosine_similarity_fast(my_emb, their_emb)
        if sim is None:
            return 0.0
        return max(0.0, min(1.0, float(sim)))
    mine = {tok for tok in _norm_text(my_text).split() if tok}
    theirs = {tok for tok in _norm_text(their_text).split() if tok}
    return _jaccard(mine, theirs)


def _profile_similarity(vibe: float, answer3: float, answer4: float, prompt1: float, prompt2: float) -> float:
    return 0.20 * vibe + 0.20 * answer3 + 0.20 * answer4 + 0.20 * prompt1 + 0.20 * prompt2


def _sql_fallback_score(distance_km: Optional[float], profile: float) -> float:
    """Higher is better. Profile match cannot outrank someone more than ~5km closer."""
    profile = max(0.0, min(1.0, float(profile)))
    boost_cap = (_SQL_FALLBACK_PROFILE_KM / _SQL_FALLBACK_MAX_KM) * 0.95
    if distance_km is None:
        raw = profile * 0.001
    else:
        dist = max(0.0, float(distance_km))
        if dist >= _SQL_FALLBACK_MAX_KM:
            raw = 0.002 + profile * 0.001
        else:
            proximity = 1.0 - (dist / _SQL_FALLBACK_MAX_KM)
            raw = proximity + profile * boost_cap
    return raw / (1.0 + boost_cap)


def _row_value(row, idx):
    if row is None or len(row) <= idx:
        return None
    return row[idx]


def _log_impressions_background(viewer_id: int, ranked: list, pipeline_version: str) -> None:
    """Persist impressions without blocking the API response."""
    snapshot = [(uid, score, dict(bd) if isinstance(bd, dict) else {}) for uid, score, bd in ranked[:10]]

    def _worker():
        try:
            from Model.netwirk_DB import DB
            from Model.recsys.db_feedback import log_impressions

            db = DB()
            cur = db.cur()
            try:
                log_impressions(cur, viewer_id, snapshot, pipeline_version, max_rows=10)
                db.conn.commit()
            finally:
                try:
                    cur.close()
                except Exception:
                    pass
                try:
                    db.conn.close()
                except Exception:
                    pass
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


def profile_from_sql_row(
    service,
    row,
    coords_map: dict,
    tag_counts_map: Optional[dict] = None,
    places_map: Optional[dict] = None,
) -> UserProfile:
    uid = row[0]
    coords = coords_map.get(uid) or (None, None)
    from Model.recsys.compat import COMM_STYLE_MAP, INTENT_MAP

    ans3 = (row[24] or "").strip().lower() if len(row) > 24 else ""
    ans4 = (row[25] or "").strip().lower() if len(row) > 25 else ""
    dob = row[10]
    age = service._age_from_dob(dob) if dob else None
    emb1 = service._load_embedding(row[34]) if len(row) > 34 else None
    emb2 = service._load_embedding(row[35]) if len(row) > 35 else None

    return UserProfile(
        user_id=uid,
        age=age,
        gender=row[8],
        preference=row[9],
        lat=coords[0] if coords else None,
        lng=coords[1] if coords else None,
        interests=_parse_vibes(row[11] if len(row) > 11 else ""),
        comm_style=ans3,
        intent=ans4,
        comm_idx=COMM_STYLE_MAP.get(ans3),
        intent_idx=INTENT_MAP.get(ans4),
        prompt1=row[31] if len(row) > 31 else "",
        prompt2=row[33] if len(row) > 33 else "",
        emb1=emb1,
        emb2=emb2,
        tag_counts=(tag_counts_map or {}).get(uid, {}),
        places=(places_map or {}).get(uid, set()),
        full_name=row[3] if len(row) > 3 else "",
        vibes_raw=row[11] if len(row) > 11 else "",
    )


class OfflineRecsysRunner:
    VERSION = "personalize_offline_v1"

    def __init__(self, service):
        self.service = service

    def _viewer_name(self, cursor, user_id: int) -> str:
        try:
            cursor.execute(
                "SELECT fullName FROM icebreaker.registration WHERE userId = %s",
                (user_id,),
            )
            row = cursor.fetchone()
            return (row[0] or "").strip() if row else ""
        except Exception:
            return ""

    def _rank_with_personalize(
        self,
        user_id: int,
        candidate_ids: List[int],
        cfg: dict,
        ranking_k: int,
    ) -> Tuple[List[Tuple[int, float, dict]], str, dict]:
        scores, meta = get_personalize_scores(user_id, candidate_ids, cfg)
        ranker = "amazon_personalize" if scores else "sql_fallback"

        ranked: List[Tuple[int, float, dict]] = []
        for uid in candidate_ids:
            if uid in scores:
                score = scores[uid]
                ranked.append((uid, score, {"personalize_score": score}))

        ranked.sort(key=lambda x: x[1], reverse=True)

        seen = {uid for uid, _, _ in ranked}
        for uid in candidate_ids:
            if uid not in seen:
                ranked.append((uid, 0.0, {"personalize_score": 0.0}))

        return ranked[:ranking_k], ranker, meta

    def _rank_sql_fallback(
        self,
        cursor,
        user_id: int,
        sql_candidates: list,
        candidate_ids: List[int],
        ranking_k: int,
        viewer_profile: Optional[dict] = None,
    ) -> List[Tuple[int, float, dict]]:
        """Rank the SQL pool when Personalize returns nothing.

        Nearest live location comes first. Vibes, answer3, answer4,
        prompt1answer, and prompt2answer reorder people only inside ~5km.
        """
        if not candidate_ids:
            return []
        try:
            return self._score_sql_fallback_candidates(
                cursor, user_id, sql_candidates, candidate_ids, ranking_k,
                viewer_profile=viewer_profile,
            )
        except Exception:
            logger.exception(
                "offline_feed event=error stage=sql_fallback user_id=%s",
                user_id,
            )
            return [
                (uid, 0.0, {"personalize_score": 0.0})
                for uid in candidate_ids[:ranking_k]
            ]

    def _score_sql_fallback_candidates(
        self,
        cursor,
        user_id: int,
        sql_candidates: list,
        candidate_ids: List[int],
        ranking_k: int,
        viewer_profile: Optional[dict] = None,
    ) -> List[Tuple[int, float, dict]]:
        if viewer_profile is None:
            cursor.execute(
                """
                SELECT p.vibes, p.answer3, p.answer4,
                       p.prompt1answer, p.prompt2answer,
                       loc.latitude, loc.longitude
                FROM icebreaker.profile p
                LEFT JOIN icebreaker.user_live_location_offline loc
                    ON loc.user_id = p.userId
                WHERE p.userId = %s
                """,
                (user_id,),
            )
            viewer = cursor.fetchone()
            if not viewer:
                return [
                    (uid, 0.0, {"personalize_score": 0.0})
                    for uid in candidate_ids[:ranking_k]
                ]
            viewer_profile = {
                "vibes": viewer[0],
                "answer3": viewer[1],
                "answer4": viewer[2],
                "prompt1": viewer[3],
                "prompt2": viewer[4],
                "lat": viewer[5],
                "lng": viewer[6],
            }

        my_vibes = viewer_profile.get("vibes")
        my_answer3 = viewer_profile.get("answer3")
        my_answer4 = viewer_profile.get("answer4")
        my_prompt1 = viewer_profile.get("prompt1")
        my_prompt2 = viewer_profile.get("prompt2")
        my_coords = _as_coords(viewer_profile.get("lat"), viewer_profile.get("lng"))

        # Slim pool rows: 0 id, 1 name, 2 vibes, 3 answer3, 4 answer4,
        # 5 prompt1answer, 6 prompt2answer, 7 latitude, 8 longitude.
        row_by_id = {row[0]: row for row in sql_candidates}

        scored: List[Tuple[int, float, dict]] = []
        for uid in candidate_ids:
            row = row_by_id.get(uid)
            their_coords = _as_coords(_row_value(row, 7), _row_value(row, 8))
            if my_coords and their_coords:
                distance_km = self.service._haversine_km(my_coords, their_coords)
            else:
                distance_km = None

            vibe = _vibe_similarity(my_vibes, _row_value(row, 2))
            answer3 = _answer_similarity(
                my_answer3, _row_value(row, 3), COMM_STYLE_MAP, comm_style_compat,
            )
            answer4 = _answer_similarity(
                my_answer4, _row_value(row, 4), INTENT_MAP, intent_compat,
            )
            prompt1 = _prompt_similarity(
                self.service, None, None, my_prompt1, _row_value(row, 5),
            )
            prompt2 = _prompt_similarity(
                self.service, None, None, my_prompt2, _row_value(row, 6),
            )
            profile = _profile_similarity(vibe, answer3, answer4, prompt1, prompt2)
            score = _sql_fallback_score(distance_km, profile)

            if distance_km is None:
                proximity = 0.0
            else:
                proximity = max(
                    0.0,
                    1.0 - min(float(distance_km), _SQL_FALLBACK_MAX_KM) / _SQL_FALLBACK_MAX_KM,
                )
            breakdown = {
                "proximity_score": round(proximity, 4),
                "shared_interest_count": round(vibe, 4),
                "comm_style_compat": round(answer3, 4),
                "intent_compat": round(answer4, 4),
                "prompt1_sim": round(prompt1, 4),
                "prompt2_sim": round(prompt2, 4),
            }
            if distance_km is not None:
                breakdown["distance_km"] = round(float(distance_km), 2)
            scored.append((uid, score, breakdown))

        scored.sort(key=lambda item: (-item[1], item[0]))
        return scored[:ranking_k]

    @staticmethod
    def _apply_current_candidates(
        ranked: List[Tuple[int, float, dict]],
        candidate_ids: List[int],
        ranking_k: int,
    ) -> List[Tuple[int, float, dict]]:
        """Keep cached Personalize order, drop people who left the SQL pool."""
        allowed = set(candidate_ids)
        filtered = [(uid, score, bd) for uid, score, bd in ranked if uid in allowed]
        seen = {uid for uid, _, _ in filtered}
        for uid in candidate_ids:
            if uid not in seen:
                filtered.append((uid, 0.0, {"personalize_score": 0.0}))
        return filtered[:ranking_k]

    def run(
        self,
        cursor,
        user_id: int,
        sql_candidates: list,
        session_hidden_ids: Optional[List[int]] = None,
        ranking_k: int = RANKING_TOP_K,
        viewer_profile: Optional[dict] = None,
    ) -> dict:
        session_hidden: Set[int] = set(session_hidden_ids or [])
        if viewer_profile is not None and "full_name" in viewer_profile:
            viewer_name = viewer_profile.get("full_name") or ""
        else:
            viewer_name = self._viewer_name(cursor, user_id)
        if not sql_candidates:
            event = {
                "user_id": user_id,
                "viewer_name": viewer_name,
                "ranker": "none",
                "cache_hit": False,
                "latency_ms": 0,
                "personalize_returned": 0,
                "candidates": 0,
                "matches": 0,
                "suggested": [],
            }
            record_offline_feed_event(event)
            logger.info(
                "offline_feed event=rank ranker=none cache_hit=false "
                "latency_ms=0 personalize_returned=0 candidates=0 matches=0 "
                "viewer_name=%s user_id=%s",
                viewer_name or "-",
                user_id,
            )
            return {"Status": "Success", "Matches": [], "TotalMatches": 0}

        candidate_ids = [c[0] for c in sql_candidates if c[0] not in session_hidden]
        effective_k = min(ranking_k, len(candidate_ids)) if candidate_ids else ranking_k

        cache = get_offline_feed_cache()
        cache_key = cache.make_key(user_id)
        cached = cache.get_ranked(cache_key)
        personalize_meta: dict = {
            "latency_ms": 0,
            "personalize_returned": 0,
            "personalize_matched": 0,
            "error": None,
        }
        if cached is not None and cached[1] == "sql_fallback":
            reranked, ranker = cached
        elif not is_personalize_enabled():
            reranked, ranker = [], "sql_fallback"
            personalize_meta["error"] = "personalize_disabled"
        elif cached is not None:
            reranked, ranker = cached
            if ranker != "sql_fallback":
                reranked = self._apply_current_candidates(
                    reranked, candidate_ids, effective_k,
                )
        else:
            cfg = self.service._load_vibr_config()
            if not is_personalize_enabled(cfg):
                reranked, ranker = [], "sql_fallback"
                personalize_meta["error"] = "personalize_disabled"
            else:
                reranked, ranker, personalize_meta = self._rank_with_personalize(
                    user_id, candidate_ids, cfg, effective_k,
                )
                cache.set_ranked(cache_key, reranked, ranker)

        if ranker == "sql_fallback":
            reranked = self._rank_sql_fallback(
                cursor, user_id, sql_candidates, candidate_ids, effective_k,
                viewer_profile=viewer_profile,
            )

        cache_hit = cached is not None
        latency_ms = 0 if cache_hit else int(personalize_meta.get("latency_ms") or 0)
        personalize_returned = (
            None if cache_hit else int(personalize_meta.get("personalize_returned") or 0)
        )

        row_by_id = {r[0]: r for r in sql_candidates}
        top_n = int(os.getenv("OFFLINE_FEED_DASHBOARD_TOP_N", "15"))
        suggested = []
        for uid, score, _breakdown in reranked[:top_n]:
            row = row_by_id.get(uid)
            suggested.append({
                "user_id": uid,
                "full_name": (row[1] if row and len(row) > 1 else "") or "",
                "score": round(float(score), 4),
            })

        event = {
            "user_id": user_id,
            "viewer_name": viewer_name,
            "ranker": ranker,
            "cache_hit": cache_hit,
            "latency_ms": latency_ms,
            "personalize_returned": personalize_returned,
            "candidates": len(candidate_ids),
            "matches": len(reranked),
            "suggested": suggested,
            "error": personalize_meta.get("error") if not cache_hit else None,
        }
        record_offline_feed_event(event)
        suggested_ids = ",".join(str(s["user_id"]) for s in suggested)
        logger.info(
            "offline_feed event=rank ranker=%s cache_hit=%s latency_ms=%s "
            "personalize_returned=%s candidates=%s matches=%s "
            "suggested_ids=%s viewer_name=%s user_id=%s",
            ranker,
            str(cache_hit).lower(),
            latency_ms,
            personalize_returned if personalize_returned is not None else "n/a",
            len(candidate_ids),
            len(reranked),
            suggested_ids or "-",
            viewer_name or "-",
            user_id,
        )

        _log_impressions_background(user_id, reranked, self.VERSION)

        results = []
        for uid, score, _breakdown in reranked:
            user = row_by_id.get(uid)
            if not user:
                continue
            results.append({
                "userId": uid,
                "fullName": user[1] or "",
                "similarity_score": round(float(score) * 100, 2),
                "ranker": ranker,
            })

        return {
            "Status": "Success",
            "Matches": results,
            "TotalMatches": len(results),
            "pipeline_version": self.VERSION,
            "ranker": ranker,
            "cache_hit": cache_hit,
        }
