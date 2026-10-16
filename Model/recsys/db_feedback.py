"""MySQL persistence for rec_interactions and rec_impressions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import List, Optional

from Model.recsys.schema import Interaction, InteractionAction, coerce_timestamp


def ensure_rec_interactions_table(cursor) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS icebreaker.rec_interactions (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_a_id INT NOT NULL,
            user_b_id INT NOT NULL,
            action VARCHAR(64) NOT NULL,
            source_function VARCHAR(128) DEFAULT NULL,
            metadata JSON DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_user_a (user_a_id),
            INDEX idx_user_b (user_b_id),
            INDEX idx_created (created_at)
        )
    """)


def ensure_rec_impressions_table(cursor) -> None:
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS icebreaker.rec_impressions (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            viewer_id INT NOT NULL,
            candidate_id INT NOT NULL,
            rank_position INT NOT NULL,
            score FLOAT DEFAULT NULL,
            pipeline_version VARCHAR(64) DEFAULT NULL,
            feature_breakdown JSON DEFAULT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_viewer (viewer_id),
            INDEX idx_candidate (candidate_id)
        )
    """)


def insert_interaction_row(
    cursor,
    user_a_id: int,
    user_b_id: int,
    action: str,
    source_function: str = "",
    metadata: Optional[dict] = None,
    created_at: Optional[datetime] = None,
) -> None:
    ensure_rec_interactions_table(cursor)
    cursor.execute("""
        INSERT INTO icebreaker.rec_interactions
            (user_a_id, user_b_id, action, source_function, metadata, created_at)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        user_a_id,
        user_b_id,
        action,
        source_function,
        json.dumps(metadata or {}),
        created_at or datetime.now(timezone.utc),
    ))


def insert_impression_row(
    cursor,
    viewer_id: int,
    candidate_id: int,
    rank_position: int,
    score: float,
    pipeline_version: str,
    feature_breakdown: dict,
) -> None:
    ensure_rec_impressions_table(cursor)
    cursor.execute("""
        INSERT INTO icebreaker.rec_impressions
            (viewer_id, candidate_id, rank_position, score, pipeline_version, feature_breakdown)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (
        viewer_id,
        candidate_id,
        rank_position,
        score,
        pipeline_version,
        json.dumps(feature_breakdown),
    ))


def _row_to_interaction(row) -> Interaction:
    meta = row[5] if len(row) > 5 else {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}
    return Interaction(
        user_a_id=row[1],
        user_b_id=row[2],
        action=InteractionAction(row[3]),
        source_function=row[4] or "",
        timestamp=coerce_timestamp(row[6] if len(row) > 6 else row[5]),
        metadata=meta if isinstance(meta, dict) else {},
    )


def load_interactions_from_cursor(cursor, since: Optional[datetime] = None) -> List[Interaction]:
    ensure_rec_interactions_table(cursor)
    if since:
        cursor.execute("""
            SELECT id, user_a_id, user_b_id, action, source_function, metadata, created_at
            FROM icebreaker.rec_interactions
            WHERE created_at >= %s
            ORDER BY created_at ASC
        """, (since,))
    else:
        cursor.execute("""
            SELECT id, user_a_id, user_b_id, action, source_function, metadata, created_at
            FROM icebreaker.rec_interactions
            ORDER BY created_at ASC
        """)
    return [_row_to_interaction(r) for r in cursor.fetchall()]


def backfill_rec_interactions_from_legacy(cursor) -> int:
    ensure_rec_interactions_table(cursor)
    inserted = 0

    cursor.execute("""
        SELECT sender_id, receiver_id, created_at
        FROM icebreaker.user_likes
        ORDER BY created_at ASC
    """)
    for sender_id, receiver_id, created_at in cursor.fetchall():
        cursor.execute("""
            SELECT id FROM icebreaker.rec_interactions
            WHERE user_a_id=%s AND user_b_id=%s AND action='like'
            LIMIT 1
        """, (sender_id, receiver_id))
        if cursor.fetchone():
            continue
        insert_interaction_row(
            cursor, sender_id, receiver_id, "like",
            "user_likes:backfill", {}, created_at,
        )
        inserted += 1

    cursor.execute("""
        SELECT sender_id, receiver_id, created_at
        FROM icebreaker.user_likes_near
        ORDER BY created_at ASC
    """)
    for sender_id, receiver_id, created_at in cursor.fetchall():
        cursor.execute("""
            SELECT id FROM icebreaker.rec_interactions
            WHERE user_a_id=%s AND user_b_id=%s AND action='like'
            LIMIT 1
        """, (sender_id, receiver_id))
        if cursor.fetchone():
            continue
        insert_interaction_row(
            cursor, sender_id, receiver_id, "like",
            "user_likes_near:backfill", {}, created_at,
        )
        inserted += 1

    for table, action in (
        ("hidden_users_1day", "hide_1_day"),
        ("hidden_users_1month", "hide_1_month"),
    ):
        cursor.execute(f"""
            SELECT userId, hiddenUserId, hiddenAt
            FROM icebreaker.{table}
            ORDER BY hiddenAt ASC
        """)
        for user_id, hidden_id, hidden_at in cursor.fetchall():
            insert_interaction_row(
                cursor, user_id, hidden_id, action,
                f"{table}:backfill", {}, hidden_at,
            )
            inserted += 1

    cursor.execute("""
        SELECT userId, requestedUserId, requestTime
        FROM icebreaker.netwirkRequestsPending
        WHERE status = 'Pending'
        ORDER BY requestTime ASC
    """)
    for user_id, requested_id, request_time in cursor.fetchall():
        cursor.execute("""
            SELECT id FROM icebreaker.rec_interactions
            WHERE user_a_id=%s AND user_b_id=%s AND action='send_request'
            LIMIT 1
        """, (user_id, requested_id))
        if cursor.fetchone():
            continue
        insert_interaction_row(
            cursor, user_id, requested_id, "send_request",
            "netwirkRequestsPending:backfill", {}, request_time,
        )
        inserted += 1

    cursor.execute("""
        SELECT userId, requestedUserId, requestTime
        FROM icebreaker.netwirkRequestsAccepted
        WHERE status = 'Accepted'
        ORDER BY requestTime ASC
    """)
    for user_id, requested_id, request_time in cursor.fetchall():
        cursor.execute("""
            SELECT id FROM icebreaker.rec_interactions
            WHERE user_a_id=%s AND user_b_id=%s AND action='accept_request'
            LIMIT 1
        """, (user_id, requested_id))
        if cursor.fetchone():
            continue
        insert_interaction_row(
            cursor, user_id, requested_id, "accept_request",
            "netwirkRequestsAccepted:backfill", {}, request_time,
        )
        inserted += 1

    return inserted


def log_impressions(
    cursor,
    viewer_id: int,
    ranked: list,
    pipeline_version: str,
    max_rows: int = 25,
) -> None:
    for pos, (uid, score, breakdown) in enumerate(ranked[:max_rows], start=1):
        insert_impression_row(
            cursor, viewer_id, uid, pos, float(score),
            pipeline_version, breakdown if isinstance(breakdown, dict) else {},
        )
