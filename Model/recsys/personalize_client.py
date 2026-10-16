"""Amazon Personalize runtime client for offline feed ranking."""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import Dict, List, Tuple

import boto3
from botocore.config import Config

logger = logging.getLogger(__name__)

PersonalizeMeta = Dict[str, object]

_LOCK = threading.Lock()
_CLIENT = None
_CLIENT_KEY = None
_SKIP_UNTIL = 0.0
_COOLDOWN_SEC = int(os.getenv("PERSONALIZE_FAILURE_COOLDOWN_SEC", "300"))

# False skips Amazon Personalize and ranks the offline feed with the SQL fallback.
PERSONALIZE_ENABLED = False


def is_personalize_enabled(cfg: dict | None = None) -> bool:
    if not PERSONALIZE_ENABLED:
        return False
    if cfg is None:
        return True
    return bool(cfg.get("personalize_enabled", True))


def _runtime_client(cfg: dict):
    global _CLIENT, _CLIENT_KEY
    key = (
        cfg.get("region", "ap-south-1"),
        cfg.get("aws_access_key_id"),
        cfg.get("personalize_campaign_arn"),
    )
    with _LOCK:
        if _CLIENT is not None and _CLIENT_KEY == key:
            return _CLIENT
        _CLIENT = boto3.client(
            "personalize-runtime",
            region_name=key[0],
            aws_access_key_id=cfg.get("aws_access_key_id"),
            aws_secret_access_key=cfg.get("aws_secret_access_key"),
            config=Config(
                connect_timeout=1,
                read_timeout=2,
                retries={"max_attempts": 1},
            ),
        )
        _CLIENT_KEY = key
        return _CLIENT


def _start_cooldown(reason: str) -> None:
    global _SKIP_UNTIL
    with _LOCK:
        _SKIP_UNTIL = time.time() + _COOLDOWN_SEC
    logger.warning(
        "offline_feed event=personalize_cooldown sec=%s reason=%s",
        _COOLDOWN_SEC,
        reason,
    )


def get_personalize_scores(
    user_id: int,
    candidate_ids: List[int],
    cfg: dict,
) -> Tuple[Dict[int, float], PersonalizeMeta]:
    """Return ({candidate_user_id: score}, meta) intersected with the SQL pool."""
    meta: PersonalizeMeta = {
        "latency_ms": 0,
        "personalize_returned": 0,
        "personalize_matched": 0,
        "error": None,
    }

    if not candidate_ids:
        return {}, meta

    if not is_personalize_enabled(cfg):
        meta["error"] = "personalize_disabled"
        return {}, meta

    campaign_arn = cfg.get("personalize_campaign_arn")
    if not campaign_arn:
        logger.warning("personalize_campaign_arn missing from vibr_config.json")
        meta["error"] = "missing_campaign_arn"
        return {}, meta

    if time.time() < _SKIP_UNTIL:
        meta["error"] = "personalize_cooldown"
        return {}, meta

    try:
        client = _runtime_client(cfg)
        kwargs = {
            "campaignArn": campaign_arn,
            "userId": str(user_id),
            "numResults": min(500, len(candidate_ids)) if candidate_ids else 25,
        }
        filter_arn = cfg.get("personalize_filter_arn")
        if filter_arn:
            kwargs["filterArn"] = filter_arn

        started = time.perf_counter()
        resp = client.get_recommendations(**kwargs)
        meta["latency_ms"] = int((time.perf_counter() - started) * 1000)

        item_list = resp.get("itemList", []) or []
        meta["personalize_returned"] = len(item_list)

        allowed = {str(cid) for cid in candidate_ids}
        scores: Dict[int, float] = {}
        for i, item in enumerate(item_list):
            item_id = item["itemId"]
            if item_id not in allowed:
                continue
            uid = int(item_id)
            raw = item.get("score")
            scores[uid] = float(raw) if raw is not None else max(0.0, 1.0 - i * 0.01)

        meta["personalize_matched"] = len(scores)
        if not scores:
            meta["error"] = "empty_scores"
        return scores, meta
    except Exception as exc:
        logger.exception(
            "offline_feed event=error stage=personalize user_id=%s reason=%s",
            user_id,
            type(exc).__name__,
        )
        meta["error"] = type(exc).__name__
        _start_cooldown(type(exc).__name__)
        return {}, meta
