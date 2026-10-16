"""Core data types and action mapping for the recsys pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set


class InteractionAction(str, Enum):
    LIKE = "like"
    LIKE_BACK = "like_back"
    UNLIKE = "unlike"
    HIDE_1_DAY = "hide_1_day"
    HIDE_1_MONTH = "hide_1_month"
    SEND_REQUEST = "send_request"
    ACCEPT_REQUEST = "accept_request"
    REJECT_REQUEST = "reject_request"
    WITHDRAW_REQUEST = "withdraw_request"
    SKIP = "skip"
    VIEW = "view"


@dataclass
class UserProfile:
    user_id: int
    age: Optional[int] = None
    gender: Optional[str] = None
    preference: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    interests: List[str] = field(default_factory=list)
    comm_style: Optional[str] = None
    intent: Optional[str] = None
    comm_idx: Optional[int] = None
    intent_idx: Optional[int] = None
    prompt1: str = ""
    prompt2: str = ""
    emb1: Optional[List[float]] = None
    emb2: Optional[List[float]] = None
    tag_counts: Dict[str, int] = field(default_factory=dict)
    places: Set[str] = field(default_factory=set)
    last_active: Optional[datetime] = None
    full_name: str = ""
    vibes_raw: str = ""

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "age": self.age,
            "interests": self.interests,
            "comm_style": self.comm_style,
            "intent": self.intent,
        }


@dataclass
class Interaction:
    user_a_id: int
    user_b_id: int
    action: InteractionAction
    timestamp: datetime
    source_function: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "user_a_id": self.user_a_id,
            "user_b_id": self.user_b_id,
            "action": self.action.value,
            "timestamp": self.timestamp.isoformat(),
            "source_function": self.source_function,
            "metadata": self.metadata,
        }


def coerce_timestamp(value) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def wave_toggle_action(existing_like: bool, wave_status: Optional[str], source_fn: str) -> InteractionAction:
    if existing_like or wave_status in ("already_waved", "wave_back"):
        return InteractionAction.UNLIKE
    return InteractionAction.LIKE


def wave_source_fn(source_fn: str, action: InteractionAction) -> str:
    base = source_fn.split(":")[0] if ":" in source_fn else source_fn
    return f"{base}:{action.value}"


def confirm_netwirk_action(status: Optional[str]) -> InteractionAction:
    st = (status or "").strip().lower()
    if st in ("accepted", "accept"):
        return InteractionAction.ACCEPT_REQUEST
    return InteractionAction.REJECT_REQUEST


def confirm_netwirk_source(status: Optional[str]) -> str:
    st = (status or "unknown").strip()
    return f"confirmNetwirkAPI:{st}"


def hide_action(duration: str) -> InteractionAction:
    d = (duration or "").lower().replace("-", "_")
    if "month" in d:
        return InteractionAction.HIDE_1_MONTH
    return InteractionAction.HIDE_1_DAY


def hide_source(duration: str) -> str:
    act = hide_action(duration)
    return f"hide_user_from_offline_list:{act.value}"
