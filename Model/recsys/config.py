"""Recsys pipeline configuration and artifact paths."""

import os

ARTIFACTS_DIR = os.getenv(
    "VYB_RECSYS_ARTIFACTS",
    os.path.join(os.path.dirname(__file__), "..", "..", "artifacts", "recsys"),
)

RETRIEVAL_TOP_K = int(os.getenv("VYB_RETRIEVAL_TOP_K", "500"))
RANKING_TOP_K = int(os.getenv("VYB_RANKING_TOP_K", "50"))

TOWER_EMBED_DIM = int(os.getenv("VYB_TOWER_EMBED_DIM", "64"))
TOWER_HIDDEN_DIM = int(os.getenv("VYB_TOWER_HIDDEN_DIM", "128"))
TOWER_MODEL_PATH = os.path.join(ARTIFACTS_DIR, "two_tower.pt")
TOWER_FAISS_INDEX_PATH = os.path.join(ARTIFACTS_DIR, "two_tower.index")
TOWER_ID_MAP_PATH = os.path.join(ARTIFACTS_DIR, "two_tower_id_map.json")

RANKER_MODEL_PATH = os.path.join(ARTIFACTS_DIR, "connection_ranker.xgb")
RANKER_META_PATH = os.path.join(ARTIFACTS_DIR, "connection_ranker_meta.json")
LEGACY_RANKER_PATH = os.path.join(ARTIFACTS_DIR, "ranker.xgb")

FEATURE_NAMES = [
    "proximity_score",
    "shared_interest_count",
    "comm_style_compat",
    "intent_compat",
    "prompt1_sim",
    "prompt2_sim",
    "age_gap",
    "lifestyle_similarity",
    "checkin_overlap",
]

DIVERSITY_LAMBDA = float(os.getenv("VYB_DIVERSITY_LAMBDA", "0.35"))
EXPLORATION_EPSILON = float(os.getenv("VYB_EXPLORATION_EPSILON", "0.12"))
BANDIT_STATE_PATH = os.path.join(ARTIFACTS_DIR, "bandit_state.json")

PROXIMITY_PRIORITY = float(os.getenv("VYB_PROXIMITY_PRIORITY", "2.0"))
RETRIEVAL_PROXIMITY_BLEND = float(os.getenv("VYB_RETRIEVAL_PROXIMITY_BLEND", "0.45"))

HEURISTIC_FALLBACK_WEIGHTS = {
    "proximity_score": 0.28,
    "shared_interest_count": 0.13,
    "comm_style_compat": 0.10,
    "intent_compat": 0.12,
    "prompt1_sim": 0.06,
    "prompt2_sim": 0.06,
    "age_gap": 0.08,
    "lifestyle_similarity": 0.08,
    "checkin_overlap": 0.07,
}

ST_MODEL_NAME = os.getenv("VYB_ST_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
