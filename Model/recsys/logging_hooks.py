"""Production logging hooks for Flask routes."""

from __future__ import annotations

from datetime import datetime, timezone

from Model.recsys.db_feedback import insert_interaction_row
from Model.recsys.schema import (
    InteractionAction,
    confirm_netwirk_action,
    confirm_netwirk_source,
    hide_action,
    hide_source,
    wave_source_fn,
    wave_toggle_action,
)


def log_wave_interaction(cursor, sender_id: int, receiver_id: int, existing_like: bool, wave_status: str, source_fn: str) -> None:
    act = wave_toggle_action(existing_like, wave_status, source_fn)
    src = wave_source_fn(source_fn, act)
    insert_interaction_row(cursor, sender_id, receiver_id, act.value, src, {})


def log_hide_interaction(cursor, user_id: int, hidden_id: int, duration: str) -> None:
    act = hide_action(duration)
    insert_interaction_row(cursor, user_id, hidden_id, act.value, hide_source(duration), {"duration": duration})


def log_confirm_netwirk_interaction(cursor, user_id: int, other_id: int, status: str) -> None:
    act = confirm_netwirk_action(status)
    insert_interaction_row(cursor, user_id, other_id, act.value, confirm_netwirk_source(status), {"status": status})
