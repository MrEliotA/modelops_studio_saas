# gpu-scheduler-service

A scheduler loop that dispatches queued GPU jobs fairly across tenants.

## What it does
- Reads `gpu_jobs` from Postgres
- Enforces:
  - per-tenant concurrency (`tenant_gpu_policies`)
  - global slot limits (T4 time-slicing replicas / MIG partitions)
  - priority ordering
- Transitions jobs:
  - `QUEUED` -> `DISPATCHED` (sets `gpu_pool_assigned` + `dispatch_token`)
- Publishes dispatch events:
  - `mlops.gpu.jobs.dispatched.t4.shared`
  - `mlops.gpu.jobs.dispatched.t4.exclusive`
  - `mlops.gpu.jobs.dispatched.mig`

## Slot configuration (env)
- `T4_SHARED_SLOTS` (default 8)
- `T4_EXCLUSIVE_SLOTS` (default 1)
- `MIG_TOTAL_SLOTS` (default 0)

## Related docs
- `docs/GPU_QUEUE.md`
