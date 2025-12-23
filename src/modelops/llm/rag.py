from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

from modelops.llm.embeddings import EmbeddingModel


@dataclass(slots=True)
class Document:
    doc_id: str
    text: str
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class RetrievalResult:
    document: Document
    score: float


class InMemoryVectorIndex:
    """Simple in-memory vector index for demos."""

    def __init__(self, embedder: EmbeddingModel) -> None:
        self._embedder = embedder
        self._docs: list[Document] = []
        self._vectors: list[list[float]] = []

    def add_documents(self, documents: Iterable[Document]) -> None:
        docs = list(documents)
        if not docs:
            return
        vectors = self._embedder.embed_texts([doc.text for doc in docs])
        self._docs.extend(docs)
        self._vectors.extend(vectors)

    def search(self, query: str, top_k: int = 5) -> list[RetrievalResult]:
        if not self._docs:
            return []
        query_vector = self._embedder.embed_texts([query])[0]
        scored = []
        for doc, vector in zip(self._docs, self._vectors, strict=True):
            scored.append((doc, _cosine_similarity(query_vector, vector)))
        scored.sort(key=lambda item: item[1], reverse=True)
        return [RetrievalResult(document=doc, score=score) for doc, score in scored[:top_k]]


class RAGPipeline:
    """Builds retrieval context for LLM prompting."""

    def __init__(self, index: InMemoryVectorIndex) -> None:
        self._index = index

    def retrieve(self, query: str, top_k: int = 4) -> list[RetrievalResult]:
        return self._index.search(query, top_k=top_k)

    def build_context(self, query: str, top_k: int = 4) -> str:
        results = self.retrieve(query, top_k=top_k)
        sections = []
        for result in results:
            sections.append(f"[doc:{result.document.doc_id}] {result.document.text}")
        return "\n\n".join(sections)


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    dot = sum(l * r for l, r in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(l * l for l in left))
    right_norm = math.sqrt(sum(r * r for r in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)
