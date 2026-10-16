"""Two-tower embedding model + FAISS retrieval."""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Set, Tuple

import numpy as np

from Model.recsys.config import (
    TOWER_EMBED_DIM,
    TOWER_FAISS_INDEX_PATH,
    TOWER_HIDDEN_DIM,
    TOWER_ID_MAP_PATH,
    TOWER_MODEL_PATH,
)
from Model.recsys.features import profile_input_vector
from Model.recsys.schema import UserProfile


class _TowerNet:
    def __init__(self, in_dim: int, hidden: int, out_dim: int):
        import torch
        import torch.nn as nn

        self.net = nn.Sequential(
            nn.Linear(in_dim, hidden),
            nn.ReLU(),
            nn.Linear(hidden, out_dim),
        )

    def encode(self, x):
        import torch
        with torch.no_grad():
            t = torch.tensor(x, dtype=torch.float32).unsqueeze(0)
            out = self.net(t)
            out = out / (out.norm(dim=-1, keepdim=True) + 1e-8)
            return out.squeeze(0).numpy()


class TwoTowerModel:
    def __init__(self):
        self._tower: Optional[_TowerNet] = None
        self._index = None
        self._id_map: List[int] = []
        self._profiles: Dict[int, UserProfile] = {}
        self.load()

    def load(self) -> None:
        if os.path.exists(TOWER_MODEL_PATH):
            try:
                import torch
                payload = torch.load(TOWER_MODEL_PATH, map_location="cpu", weights_only=False)
                in_dim = payload.get("in_dim", 21)
                self._tower = _TowerNet(in_dim, TOWER_HIDDEN_DIM, TOWER_EMBED_DIM)
                self._tower.net.load_state_dict(payload["state_dict"])
            except Exception:
                self._tower = None
        if os.path.exists(TOWER_FAISS_INDEX_PATH) and os.path.exists(TOWER_ID_MAP_PATH):
            try:
                import faiss
                self._index = faiss.read_index(TOWER_FAISS_INDEX_PATH)
                with open(TOWER_ID_MAP_PATH, encoding="utf-8") as f:
                    self._id_map = json.load(f)
            except Exception:
                self._index = None

    def set_profiles(self, profiles: Dict[int, UserProfile]) -> None:
        self._profiles = profiles

    def embed_user(self, profile: UserProfile) -> np.ndarray:
        vec = profile_input_vector(profile)
        if self._tower is not None:
            return self._tower.encode(vec)
        norm = np.linalg.norm(vec)
        if norm <= 0:
            return np.zeros(TOWER_EMBED_DIM, dtype=np.float32)
        out = np.zeros(TOWER_EMBED_DIM, dtype=np.float32)
        out[: min(len(vec), TOWER_EMBED_DIM)] = vec[:TOWER_EMBED_DIM] / norm
        return out

    def query_nearest(
        self,
        viewer: UserProfile,
        top_k: int = 500,
        exclude_ids: Optional[Set[int]] = None,
    ) -> List[Tuple[int, float]]:
        exclude = exclude_ids or set()
        q = self.embed_user(viewer).astype(np.float32).reshape(1, -1)

        if self._index is not None and self._id_map:
            import faiss
            faiss.normalize_L2(q)
            k = min(top_k + len(exclude) + 10, max(1, self._index.ntotal))
            scores, idxs = self._index.search(q, k)
            hits = []
            for score, idx in zip(scores[0], idxs[0]):
                if idx < 0 or idx >= len(self._id_map):
                    continue
                uid = self._id_map[idx]
                if uid in exclude or uid == viewer.user_id:
                    continue
                hits.append((uid, float(score)))
                if len(hits) >= top_k:
                    break
            if hits:
                return hits

        # Fallback: brute-force cosine over provided profiles
        scored = []
        for uid, prof in self._profiles.items():
            if uid in exclude or uid == viewer.user_id:
                continue
            emb = self.embed_user(prof)
            sim = float(np.dot(q.flatten(), emb))
            scored.append((uid, sim))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    def save(self, path: Optional[str] = None) -> None:
        if self._tower is None:
            return
        import torch
        out = path or TOWER_MODEL_PATH
        os.makedirs(os.path.dirname(out), exist_ok=True)
        torch.save({"in_dim": 21, "state_dict": self._tower.net.state_dict()}, out)

    def rebuild_faiss(self, profiles: Dict[int, UserProfile]) -> int:
        import faiss
        ids = []
        vecs = []
        for uid, prof in profiles.items():
            emb = self.embed_user(prof)
            if np.linalg.norm(emb) <= 0:
                continue
            ids.append(uid)
            vecs.append(emb)
        if not vecs:
            return 0
        matrix = np.array(vecs, dtype=np.float32)
        faiss.normalize_L2(matrix)
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)
        os.makedirs(os.path.dirname(TOWER_FAISS_INDEX_PATH), exist_ok=True)
        faiss.write_index(index, TOWER_FAISS_INDEX_PATH)
        with open(TOWER_ID_MAP_PATH, "w", encoding="utf-8") as f:
            json.dump(ids, f)
        self._index = index
        self._id_map = ids
        return len(ids)
