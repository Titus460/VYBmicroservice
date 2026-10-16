"""Synthetic profiles and interactions for local testing."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Dict, List

from Model.recsys.checkin_features import ALL_TAGS, empty_tag_counts
from Model.recsys.compat import COMM_STYLE_MAP, INTENT_MAP
from Model.recsys.interactions import InMemoryInteractionStore, log_interaction
from Model.recsys.schema import InteractionAction, UserProfile

_COMM_KEYS = list(COMM_STYLE_MAP.keys())
_INTENT_KEYS = list(INTENT_MAP.keys())
_INTERESTS = ["coffee", "hiking", "music", "food", "travel", "fitness", "art", "movies"]


def generate_mock_profiles(n_users: int = 200) -> Dict[int, UserProfile]:
    profiles = {}
    for uid in range(1, n_users + 1):
        comm = random.choice(_COMM_KEYS)
        intent = random.choice(_INTENT_KEYS)
        tags = empty_tag_counts()
        for t in random.sample(ALL_TAGS, k=random.randint(2, 5)):
            tags[t] = random.randint(1, 8)
        profiles[uid] = UserProfile(
            user_id=uid,
            age=random.randint(21, 38),
            gender=random.choice(["Male", "Female"]),
            preference=random.choice(["Male", "Female", "Both"]),
            lat=12.97 + random.uniform(-0.15, 0.15),
            lng=77.59 + random.uniform(-0.15, 0.15),
            interests=random.sample(_INTERESTS, k=random.randint(2, 5)),
            comm_style=comm,
            intent=intent,
            comm_idx=COMM_STYLE_MAP[comm],
            intent_idx=INTENT_MAP[intent],
            prompt1=f"Mock prompt 1 for user {uid}",
            prompt2=f"Mock prompt 2 for user {uid}",
            tag_counts=tags,
            places=set(random.sample(["place_a", "place_b", "place_c", "place_d"], k=random.randint(0, 3))),
            last_active=datetime.now(timezone.utc) - timedelta(hours=random.randint(1, 72)),
            full_name=f"User {uid}",
        )
    return profiles


def generate_mock_interactions(
    profiles: Dict[int, UserProfile],
    n_pairs: int = 400,
    positive_rate: float = 0.15,
) -> InMemoryInteractionStore:
    store = InMemoryInteractionStore()
    ids = list(profiles.keys())
    now = datetime.now(timezone.utc)
    for _ in range(n_pairs):
        a, b = random.sample(ids, 2)
        ts = now - timedelta(hours=random.randint(1, 500))
        if random.random() < positive_rate:
            log_interaction(store, a, b, InteractionAction.LIKE, "mock:like", ts)
            log_interaction(store, b, a, InteractionAction.LIKE_BACK, "mock:like_back", ts + timedelta(minutes=5))
            if random.random() < 0.5:
                log_interaction(store, a, b, InteractionAction.ACCEPT_REQUEST, "mock:accept", ts + timedelta(hours=1))
        else:
            act = random.choice([
                InteractionAction.HIDE_1_DAY,
                InteractionAction.SKIP,
                InteractionAction.REJECT_REQUEST,
            ])
            log_interaction(store, a, b, act, f"mock:{act.value}", ts)
    return store
