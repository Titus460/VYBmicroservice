"""Interaction storage (in-memory and MySQL-backed)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Protocol

from Model.recsys.schema import Interaction, InteractionAction, coerce_timestamp


class InteractionStore(Protocol):
    def list_all(self) -> List[Interaction]:
        ...

    def list_since(self, since: datetime) -> List[Interaction]:
        ...


class InMemoryInteractionStore:
    def __init__(self):
        self._rows: List[Interaction] = []

    def list_all(self) -> List[Interaction]:
        return list(self._rows)

    def list_since(self, since: datetime) -> List[Interaction]:
        return [r for r in self._rows if r.timestamp >= since]

    def append(self, row: Interaction) -> None:
        self._rows.append(row)


class MySQLInteractionStore:
    def __init__(self, cursor_factory):
        self._cursor_factory = cursor_factory

    def list_all(self) -> List[Interaction]:
        from Model.recsys.db_feedback import load_interactions_from_cursor
        cursor = self._cursor_factory()
        try:
            return load_interactions_from_cursor(cursor)
        finally:
            cursor.close()

    def list_since(self, since: datetime) -> List[Interaction]:
        from Model.recsys.db_feedback import load_interactions_from_cursor
        cursor = self._cursor_factory()
        try:
            return load_interactions_from_cursor(cursor, since=since)
        finally:
            cursor.close()


def log_interaction(
    store: InMemoryInteractionStore,
    user_a_id: int,
    user_b_id: int,
    action: InteractionAction,
    source_function: str,
    timestamp: Optional[datetime] = None,
    metadata: Optional[dict] = None,
) -> Interaction:
    row = Interaction(
        user_a_id=user_a_id,
        user_b_id=user_b_id,
        action=action,
        timestamp=timestamp or datetime.now(timezone.utc),
        source_function=source_function,
        metadata=metadata or {},
    )
    store.append(row)
    return row
