from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from typing import Iterable, Protocol


class EmbeddingModel(Protocol):
    """Protocol for embedding providers."""

    def embed_texts(self, texts: Iterable[str]) -> list[list[float]]:  # pragma: no cover - protocol
        ...


@dataclass(slots=True)
class HashingEmbedding:
    """Deterministic, dependency-free embedding for local demos.

    This is not meant to be a semantic embedding. It provides a stable
    numerical representation so pipelines can be wired without an external
    model dependency.
    """

    dim: int = 384
    salt: str = "modelops-llm"

    def embed_texts(self, texts: Iterable[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_text(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dim
        tokens = [tok for tok in text.lower().split() if tok.strip()]
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(f"{self.salt}:{token}".encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            sign = -1.0 if digest[4] % 2 else 1.0
            vector[index] += sign

        norm = math.sqrt(sum(val * val for val in vector))
        if norm == 0:
            return vector
        return [val / norm for val in vector]
