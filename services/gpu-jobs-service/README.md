# gpu-jobs-service

API service for submitting **async GPU jobs**.

## What it does
- Validates tenancy headers and request payload
- Persists the job in Postgres (`gpu_jobs`) with status `QUEUED`
- Publishes `mlops.gpu.jobs.enqueued` to NATS JetStream (informational)

## Request fields
- `gpu_pool_requested`: `t4 | mig | auto`
- `isolation_level`: `shared | exclusive` (alias: `isolated` -> `exclusive`)
- `priority`: integer (higher runs first within a tenant)
- `target_url`: HTTP endpoint to call
- `request_json`: payload for the HTTP call

## Related docs
- `docs/GPU_QUEUE.md`
