from __future__ import annotations

from fastapi import APIRouter, Request
import asyncpg
import os
import httpx

from mlops_common.app_factory import create_app
from mlops_common.errors import ApiError
from .rag_utils import normalize_text, sha256_text, fixed_chunk

app = create_app("llm-rag-service", enable_idempotency=True)
router = APIRouter(prefix="/api/v1")

# Default points to the in-cluster service name; docker-compose overrides this to a working URL.
EMBEDDINGS_URL = os.getenv("EMBEDDINGS_URL", "http://llm-embeddings-service:8000/api/v1/embeddings").rstrip("/")

# DB schema uses vector(1536) in migrations/0001_core.sql.
DIMS = int(os.getenv("RAG_DIMS", "1536"))
if DIMS != 1536:
    raise RuntimeError("RAG_DIMS must be 1536 to match DB schema (vector(1536))")


def to_pgvector(vec: list[float]) -> str:
    # pgvector text input format: '[1,2,3]'
    return "[" + ",".join(f"{float(x):.6f}" for x in vec) + "]"


async def embed_texts(texts: list[str], model: str) -> list[list[float]]:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(EMBEDDINGS_URL, json={"model": model, "inputs": texts, "dims": DIMS})
        r.raise_for_status()
        data = r.json()
        embs = data.get("embeddings")
        if not isinstance(embs, list):
            raise RuntimeError("Embeddings service did not return 'embeddings'")
        return embs


@router.get("/healthz", include_in_schema=False)
async def healthz():
    return {"ok": True, "service": "llm-rag-service"}


@router.post("/rag/indexes", status_code=201)
async def create_index(request: Request, payload: dict):
    t = request.state.tenancy
    name = payload.get("name")
    if not name:
        raise ApiError("BadRequest", "Missing name", 400)

    embedding_model = str(payload.get("embedding_model") or os.getenv("RAG_EMBEDDING_MODEL") or "local-hash-v1")

    chunking = payload.get("chunking") or {"chunk_size": 800, "overlap": 120}
    chunk_size = int(chunking.get("chunk_size", 800))
    overlap = int(chunking.get("overlap", 120))
    if overlap >= chunk_size:
        raise ApiError("BadRequest", "overlap must be < chunk_size", 400)

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                """INSERT INTO rag_indexes(tenant_id, project_id, name, embedding_model, dims, distance, chunking, metadata, created_by)
                   VALUES ($1,$2,$3,$4,$5,'cosine',$6,$7,$8)
                   RETURNING id, name, embedding_model, dims, distance, chunking, metadata, created_by, created_at, updated_at""",
                t.tenant_id,
                t.project_id,
                name,
                embedding_model,
                DIMS,
                {"strategy": "fixed", "chunk_size": chunk_size, "overlap": overlap},
                payload.get("metadata", {}),
                t.user_id,
            )
        except asyncpg.UniqueViolationError:
            raise ApiError("Conflict", "Index name already exists", 409)
    return dict(row)


@router.get("/rag/indexes")
async def list_indexes(request: Request):
    t = request.state.tenancy
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT id, name, embedding_model, dims, distance, chunking, metadata, created_by, created_at, updated_at
               FROM rag_indexes WHERE tenant_id=$1 AND project_id=$2 ORDER BY created_at DESC""",
            t.tenant_id,
            t.project_id,
        )
    return {"items": [dict(r) for r in rows]}


@router.post("/rag/indexes/{index_id}/documents")
async def ingest_documents(request: Request, index_id: str, payload: dict):
    t = request.state.tenancy
    docs = payload.get("documents")
    if not isinstance(docs, list) or not docs:
        raise ApiError("BadRequest", "documents must be a non-empty list", 400)

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        idx = await conn.fetchrow(
            """SELECT id, chunking, embedding_model FROM rag_indexes WHERE tenant_id=$1 AND project_id=$2 AND id=$3""",
            t.tenant_id,
            t.project_id,
            index_id,
        )
        if not idx:
            raise ApiError("NotFound", "Index not found", 404)

        chunking = idx["chunking"] or {"chunk_size": 800, "overlap": 120}
        chunk_size = int(chunking.get("chunk_size", 800))
        overlap = int(chunking.get("overlap", 120))
        embedding_model = str(idx["embedding_model"] or "local-hash-v1")

        ingested = []
        for d in docs:
            async with conn.transaction():
                content = d.get("content")
                if not content:
                    continue
                content_clean = normalize_text(str(content))
                chash = sha256_text(content_clean)
                external_id = d.get("external_id")

                doc_row = await conn.fetchrow(
                    """INSERT INTO rag_documents(tenant_id, project_id, index_id, external_id, title, source_uri, content, content_hash, doc_metadata, created_by)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)
                       ON CONFLICT (index_id, external_id)
                       DO UPDATE SET title=EXCLUDED.title, source_uri=EXCLUDED.source_uri,
                                     content=EXCLUDED.content, content_hash=EXCLUDED.content_hash,
                                     doc_metadata=EXCLUDED.doc_metadata, updated_at=now()
                       RETURNING id, external_id, title, source_uri, content_hash, created_at, updated_at""",
                    t.tenant_id,
                    t.project_id,
                    index_id,
                    external_id,
                    d.get("title"),
                    d.get("source_uri"),
                    content_clean,
                    chash,
                    d.get("metadata", {}),
                    t.user_id,
                )

                # Simple strategy: delete old chunks for this document.
                await conn.execute("""DELETE FROM rag_chunks WHERE document_id=$1""", doc_row["id"])

                chunks = fixed_chunk(content_clean, chunk_size, overlap)
                chunk_texts = [c.text for c in chunks]
                embeddings = await embed_texts(chunk_texts, model=embedding_model) if chunk_texts else []

                for c, e in zip(chunks, embeddings):
                    await conn.execute(
                        """INSERT INTO rag_chunks(tenant_id, project_id, index_id, document_id, chunk_no, start_char, end_char, text, chunk_metadata, embedding)
                           VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10)""",
                        t.tenant_id,
                        t.project_id,
                        index_id,
                        doc_row["id"],
                        c.chunk_no,
                        c.start,
                        c.end,
                        c.text,
                        {"external_id": external_id, "title": d.get("title"), **(d.get("metadata", {}) or {})},
                        to_pgvector(e),
                    )

                ingested.append({"document": dict(doc_row), "chunks": len(chunks)})

    return {"ingested": ingested}


@router.post("/rag/indexes/{index_id}/query")
async def query_index(request: Request, index_id: str, payload: dict):
    t = request.state.tenancy
    query = payload.get("query")
    if not query:
        raise ApiError("BadRequest", "Missing query", 400)
    top_k = int(payload.get("top_k", 5))
    top_k = max(1, min(top_k, 50))

    q = normalize_text(str(query))

    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        idx = await conn.fetchrow(
            """SELECT embedding_model FROM rag_indexes WHERE tenant_id=$1 AND project_id=$2 AND id=$3""",
            t.tenant_id,
            t.project_id,
            index_id,
        )
        if not idx:
            raise ApiError("NotFound", "Index not found", 404)
        embedding_model = str(idx["embedding_model"] or "local-hash-v1")

    q_emb = to_pgvector((await embed_texts([q], model=embedding_model))[0])

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """SELECT c.id, c.document_id, c.chunk_no, c.text, c.chunk_metadata,
                      (c.embedding <=> $4::vector) AS distance
               FROM rag_chunks c
               WHERE c.tenant_id=$1 AND c.project_id=$2 AND c.index_id=$3
               ORDER BY c.embedding <=> $4::vector
               LIMIT $5""",
            t.tenant_id,
            t.project_id,
            index_id,
            q_emb,
            top_k,
        )

    items = []
    for r in rows:
        dist = float(r["distance"]) if r["distance"] is not None else None
        sim = 1.0 - dist if dist is not None else None
        items.append(
            {
                "chunk_id": str(r["id"]),
                "document_id": str(r["document_id"]),
                "chunk_no": r["chunk_no"],
                "text": r["text"],
                "metadata": r["chunk_metadata"],
                "distance": dist,
                "similarity": sim,
            }
        )
    return {"index_id": index_id, "query": q, "top_k": top_k, "results": items}


# Convenience endpoint for the BFF: POST /llm/rag/query -> /api/v1/rag/query
@router.post("/rag/query")
async def query_index_bff(request: Request, payload: dict):
    index_id = payload.get("index_id")
    if not index_id:
        raise ApiError("BadRequest", "Missing index_id", 400)
    return await query_index(request, str(index_id), payload)


app.include_router(router)
