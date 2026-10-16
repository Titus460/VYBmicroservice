"""Label engineering from interaction trails."""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Dict, Iterable, List, Tuple

from Model.recsys.schema import Interaction, InteractionAction, coerce_timestamp

POSITIVE_ACTIONS = {InteractionAction.ACCEPT_REQUEST, InteractionAction.LIKE_BACK}
NEGATIVE_ACTIONS = {
    InteractionAction.HIDE_1_DAY,
    InteractionAction.HIDE_1_MONTH,
    InteractionAction.REJECT_REQUEST,
    InteractionAction.WITHDRAW_REQUEST,
    InteractionAction.UNLIKE,
    InteractionAction.SKIP,
}


def _pair_key(a: int, b: int) -> Tuple[int, int]:
    return (min(a, b), max(a, b))


def label_from_interactions(interactions: Iterable[Interaction]) -> Dict[Tuple[int, int], int]:
    trails: Dict[Tuple[int, int], List[InteractionAction]] = defaultdict(list)
    for row in interactions:
        key = _pair_key(row.user_a_id, row.user_b_id)
        trails[key].append(row.action)

    labels = {}
    for key, actions in trails.items():
        if InteractionAction.ACCEPT_REQUEST in actions:
            labels[key] = 1
        elif any(a in NEGATIVE_ACTIONS for a in actions):
            labels[key] = 0
        elif InteractionAction.LIKE in actions and InteractionAction.LIKE_BACK in actions:
            labels[key] = 1
        else:
            labels[key] = 0
    return labels


def label_from_interactions_weighted(interactions: Iterable[Interaction]) -> Dict[Tuple[int, int], float]:
    base = label_from_interactions(interactions)
    return {k: float(v) for k, v in base.items()}


def funnel_summary(labeled: Dict[Tuple[int, int], int]) -> dict:
    pairs = len(labeled)
    positives = sum(1 for v in labeled.values() if v == 1)
    return {
        "pairs": pairs,
        "positives": positives,
        "positive_rate": positives / pairs if pairs else 0.0,
    }


def weighted_funnel_summary(labeled: Dict[Tuple[int, int], float]) -> dict:
    pairs = len(labeled)
    positives = sum(1 for v in labeled.values() if v >= 0.5)
    return {
        "pairs": pairs,
        "positives": positives,
        "positive_rate": positives / pairs if pairs else 0.0,
    }
