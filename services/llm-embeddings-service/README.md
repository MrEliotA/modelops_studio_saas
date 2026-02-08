# llm-embeddings-service

An **embeddings façade** with a pluggable provider interface.

It is intentionally lightweight so you can swap the backend without changing the rest of the platform.

## Providers

Configured via `EMBEDDINGS_PROVIDER`:

- `hash` (default): deterministic pseudo-embeddings for dev/testing (no external dependencies).
- `http`: forwards to another embeddings endpoint with a compatible API.
- `st`: SentenceTransformers (optional dependency; install `sentence-transformers`).

### Provider: hash (default)

- Produces vectors of dimension `EMBEDDINGS_DIM` (default `1536`).
- Good for validating the end-to-end flow (RAG indexing/query), not for quality.

### Provider: http

Env:
- `EMBEDDINGS_PROVIDER=http`
- `EMBEDDINGS_HTTP_URL=<url>`
- optional `EMBEDDINGS_HTTP_API_KEY=<token>`

### Provider: st (SentenceTransformers)

Env:
- `EMBEDDINGS_PROVIDER=st`
- `EMBEDDINGS_ST_MODEL=sentence-transformers/all-MiniLM-L6-v2`

> Note: this provider requires `sentence-transformers` installed in the image.

## API

`POST /api/v1/embeddings`

Request (backward compatible keys):
- `inputs: string[]` (or `texts: string[]`)
- optional `model: string`
- optional `dims: int` (ignored by SentenceTransformers provider)

Response:
- `provider`
- `model`
- `dims`
- `count`
- `embeddings: number[][]`
