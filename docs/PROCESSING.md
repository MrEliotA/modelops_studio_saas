# Processing: Batch and Stream

This platform supports two processing styles.

## Batch processing
Finite workloads:
- Pipelines (KFP template -> run)
- Training jobs
- Batch inference (async GPU jobs)
- Feature materialization jobs (Feast materialize)

Pattern:
- Persist job intent in Postgres
- Publish an event to NATS JetStream
- Workers pull events, execute, and update job status
- KEDA scales workers based on queue lag (optional)

## Stream processing
Continuous workloads:
- Realtime feature updates (Feast push sources)
- Event-driven enrichment (e.g., embeddings)
- Online inference (sync) and async fallback

Pattern:
- Ingest events via a gateway service
- Publish events to JetStream subjects
- Stream processors consume and write outputs (Feast / Postgres / Vector DB)

See:
- `services/gpu-jobs-service` + `services/gpu-scheduler-service` (batch GPU queue)
- `services/stream-ingest-service` + `workers/stream-feast-writer` (stream -> Feast)
- `docs/FEAST_MULTI_TENANT.md` (Feast multi-tenant)
