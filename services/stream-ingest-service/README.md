# stream-ingest-service

Ingress for stream events. Publishes to JetStream subjects under `mlops.stream.*`.

Endpoint:
- `POST /api/v1/streams/{stream_name}/events`

Env:
- `NATS_URL` (required)
