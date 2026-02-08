from __future__ import annotations

import os
import hashlib
from dataclasses import dataclass
from typing import Protocol, Any, Optional

import httpx


class EmbeddingsProvider(Protocol):
    name: str

    async def embed(self, texts: list[str], dims: int, model: str | None = None) -> list[list[float]]:
        ...


def _hash_embedding(text: str, dims: int) -> list[float]:
    # Deterministic pseudo-embedding for dev/testing.
    out: list[float] = []
    base = hashlib.sha256(text.encode("utf-8")).digest()
    for i in range(dims):
        h = hashlib.sha256(base + i.to_bytes(4, "little")).digest()
        v = int.from_bytes(h[:4], "little", signed=False)
        out.append(((v % 2000000) / 1000000.0) - 1.0)  # [-1, 1)
    return out


@dataclass
class HashProvider:
    name: str = "hash"

    async def embed(self, texts: list[str], dims: int, model: str | None = None) -> list[list[float]]:
        return [_hash_embedding(t, dims) for t in texts]


@dataclass
class HttpProvider:
    # Calls another embeddings service with a compatible API (inputs -> embeddings).
    url: str
    api_key: Optional[str] = None
    name: str = "http"

    async def embed(self, texts: list[str], dims: int, model: str | None = None) -> list[list[float]]:
        headers = {}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        payload = {"inputs": texts, "dims": dims}
        if model:
            payload["model"] = model

        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(self.url, json=payload, headers=headers)
            r.raise_for_status()
            data = r.json()
            embs = data.get("embeddings")
            if not isinstance(embs, list):
                raise RuntimeError("Upstream embeddings response missing 'embeddings'")
            return embs


@dataclass
class SentenceTransformersProvider:
    model_name: str
    name: str = "sentence-transformers"
    _model: Any = None

    def _load(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore
        except Exception as e:
            raise RuntimeError(
                "sentence-transformers is not installed. Add it to requirements or use EMBEDDINGS_PROVIDER=hash/http."
            ) from e
        self._model = SentenceTransformer(self.model_name)

    async def embed(self, texts: list[str], dims: int, model: str | None = None) -> list[list[float]]:
        # dims is ignored for this provider; returned dimension depends on the model.
        self._load()
        vecs = self._model.encode(texts, convert_to_numpy=True, normalize_embeddings=True)
        return [v.tolist() for v in vecs]


def get_provider() -> EmbeddingsProvider:
    provider = (os.getenv("EMBEDDINGS_PROVIDER") or "hash").strip().lower()
    if provider == "hash":
        return HashProvider()
    if provider == "http":
        url = os.getenv("EMBEDDINGS_HTTP_URL")
        if not url:
            raise RuntimeError("EMBEDDINGS_HTTP_URL is required for EMBEDDINGS_PROVIDER=http")
        api_key = os.getenv("EMBEDDINGS_HTTP_API_KEY")
        return HttpProvider(url=url, api_key=api_key)
    if provider in ("st", "sentence-transformers", "sentence_transformers"):
        model_name = os.getenv("EMBEDDINGS_ST_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        return SentenceTransformersProvider(model_name=model_name)
    raise RuntimeError(f"Unknown EMBEDDINGS_PROVIDER: {provider}")
