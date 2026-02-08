# llm-rag-service

A **RAG index** service backed by Postgres + pgvector.

Features:
- Create an index (chunking + embedding model)
- Ingest documents (upsert by `external_id`)
- Chunk + embed + store chunks (`vector(1536)`)
- Query with cosine similarity (HNSW index)

## Endpoints

- `POST /api/v1/rag/indexes`
- `GET /api/v1/rag/indexes`
- `POST /api/v1/rag/indexes/{id}/documents`
- `POST /api/v1/rag/indexes/{id}/query`
- `POST /api/v1/rag/query` (convenience for the BFF; expects `index_id` in body)

## Env

- `DATABASE_URL`
- `EMBEDDINGS_URL` (defaults to `http://llm-embeddings-service:8000/api/v1/embeddings`)
- `RAG_EMBEDDING_MODEL` (default model when creating indexes)
- `RAG_DIMS` must remain `1536` (matches DB schema)

## Best-practice notes

- Retrieval quality is mostly about **chunking + metadata**. Treat this as an iterative loop:
  - choose a chunk strategy (size/overlap)
  - run evaluation (llm-eval-service)
  - adjust and re-ingest
- For large corpora, move ingestion to an async worker and store raw documents in object storage.
