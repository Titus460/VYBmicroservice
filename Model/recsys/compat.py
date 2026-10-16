"""Communication style and dating intent compatibility maps."""

COMM_STYLE_MAP = {
    "direct and to the point": 0,
    "thoughtful and reflective": 1,
    "playful and witty": 2,
    "warm and expressive": 3,
}

INTENT_MAP = {
    "something casual": 0,
    "long-term relationship": 1,
    "friendship first": 2,
    "not sure yet": 3,
}

_COMM_COMPAT = {
    (0, 0): 1.0, (0, 1): 0.6, (0, 2): 0.7, (0, 3): 0.5,
    (1, 0): 0.6, (1, 1): 1.0, (1, 2): 0.5, (1, 3): 0.8,
    (2, 0): 0.7, (2, 1): 0.5, (2, 2): 1.0, (2, 3): 0.7,
    (3, 0): 0.5, (3, 1): 0.8, (3, 2): 0.7, (3, 3): 1.0,
}

_INTENT_COMPAT = {
    (0, 0): 1.0, (0, 1): 0.3, (0, 2): 0.6, (0, 3): 0.7,
    (1, 0): 0.3, (1, 1): 1.0, (1, 2): 0.5, (1, 3): 0.6,
    (2, 0): 0.6, (2, 1): 0.5, (2, 2): 1.0, (2, 3): 0.7,
    (3, 0): 0.7, (3, 1): 0.6, (3, 2): 0.7, (3, 3): 1.0,
}


def comm_style_compat(a_idx, b_idx) -> float:
    if a_idx is None or b_idx is None:
        return 0.5
    return _COMM_COMPAT.get((a_idx, b_idx), 0.5)


def intent_compat(a_idx, b_idx) -> float:
    if a_idx is None or b_idx is None:
        return 0.5
    return _INTENT_COMPAT.get((a_idx, b_idx), 0.5)
