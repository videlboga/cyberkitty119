"""Simple file-backed vector store for demo/testing.

This is intentionally minimal: stores a list of entries as JSON with
fields {id, text, embedding} and supports cosine-similarity queries.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
import math


def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _norm(a: List[float]) -> float:
    return math.sqrt(sum(x * x for x in a)) or 1.0


class SimpleVectorStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.entries: List[Dict[str, Any]] = []
        if self.path.exists():
            self.load()

    def add(self, id: str, text: str, embedding: List[float]) -> None:
        self.entries.append({"id": id, "text": text, "embedding": embedding})

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("w", encoding="utf-8") as fh:
            json.dump(self.entries, fh, ensure_ascii=False, indent=2)

    def load(self) -> None:
        with self.path.open("r", encoding="utf-8") as fh:
            self.entries = json.load(fh)

    def query(self, embedding: List[float], top_k: int = 3):
        scores = []
        emb_norm = _norm(embedding)
        for e in self.entries:
            v = e.get("embedding") or []
            if not v:
                continue
            score = _dot(embedding, v) / (emb_norm * _norm(v))
            scores.append((score, e))
        scores.sort(key=lambda x: x[0], reverse=True)
        return scores[:top_k]


__all__ = ["SimpleVectorStore"]
