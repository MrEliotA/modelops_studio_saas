# stream-feast-writer

Consumes `mlops.stream.features` and writes to Feast via `feature-store-service`.

Env:
- `NATS_URL` (required)
- `FEATURE_STORE_SERVICE_URL` (required)
- `PUSH_SOURCE_NAME` (default: driver_stats_push_source)
- `PUSH_TO` (default: online)
