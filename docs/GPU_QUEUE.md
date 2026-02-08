# GPU queue + shared GPU best practices (T4 time-slicing + MIG)

This platform provides a **SageMaker-like async GPU job queue** that works well on bare-metal Kubernetes
where GPUs are scarce and must be shared across tenants.

## Why a queue?

- You can accept user requests immediately and run GPU work asynchronously.
- You can enforce **fairness** (per-tenant quotas) and **priority** (billing tiers / SLA).
- You can get better GPU utilization by controlling concurrency when using **T4 time-slicing** or **MIG**.

## Components

### 1) `gpu-jobs-service` (API)
- Stores jobs in Postgres (`gpu_jobs`)
- Publishes `mlops.gpu.jobs.enqueued` to JetStream

Key job fields:
- `gpu_pool_requested`: `t4 | mig | auto`
- `isolation_level`: `shared | exclusive`
  - `shared`: can run concurrently on T4 time-slicing
  - `exclusive`: scheduled alone (soft exclusivity) for stronger isolation

### 2) `gpu-scheduler-service` (control loop)
- Consumes jobs from Postgres and dispatches them fairly:
  - per-tenant concurrency limits (`tenant_gpu_policies`)
  - global slots (cluster capacity)
  - priority ordering
- Emits dispatch events:
  - `mlops.gpu.jobs.dispatched.t4.shared`
  - `mlops.gpu.jobs.dispatched.t4.exclusive`
  - `mlops.gpu.jobs.dispatched.mig`

Slots configuration (env):
- `T4_SHARED_SLOTS` (default 8) — matches the NVIDIA device-plugin time-slicing replicas
- `T4_EXCLUSIVE_SLOTS` (default 1)
- `MIG_TOTAL_SLOTS` (default 0)

### 3) GPU dispatcher + executor (production best practice)

**Production mode (`k8s_job`)**
- `gpu-dispatcher-*` is CPU-only and consumes dispatch events.
- For every dispatched job, it creates an **ephemeral Kubernetes Job** that requests GPU resources.
- The Job runs `workers/gpu-runner/executor.py`.

Why this is better:
- Each job runs in a fresh container => GPU memory is released on exit (cleaner than a long-running process).
- You can set `ttlSecondsAfterFinished` to auto-delete Pods/Jobs.
- You can keep the dispatcher simple and scalable.

**Dev mode (`direct`)**
- The dispatcher executes the job in-process (no Kubernetes API).
- Useful for local development on Docker Compose without GPUs.

## T4 time-slicing and isolation

With a single physical T4, time-slicing advertises multiple logical `nvidia.com/gpu` resources.
That means several Pods can request `nvidia.com/gpu: 1` concurrently.

**Isolation trade-off:**
- Time-slicing does **not** isolate GPU memory or faults between Pods.
- Use `isolation_level=exclusive` for sensitive workloads (soft exclusivity) — the scheduler avoids mixing
  shared and exclusive jobs concurrently.

## MIG notes

For MIG, Kubernetes resources are typically `nvidia.com/mig-<profile>` (not `nvidia.com/gpu`).
This repo keeps MIG configuration flexible:

- `gpu-dispatcher-mig` has `GPU_RESOURCE_NAME` as an env var (e.g. `nvidia.com/mig-1g.5gb`).
- You can later extend the job schema to include requested MIG profile/size and let the scheduler decide.

## API examples

Create a shared T4 job:
```bash
curl -X POST http://localhost:8021/api/v1/gpu-jobs \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: 11111111-1111-1111-1111-111111111111" \
  -H "X-Project-Id: 00000000-0000-0000-0000-000000000001" \
  -H "X-User-Id: demo" \
  -d '{"gpu_pool_requested":"t4","isolation_level":"shared","target_url":"http://example","request_json":{"x":1}}'
```

Create an exclusive T4 job:
```bash
curl -X POST http://localhost:8021/api/v1/gpu-jobs \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: 11111111-1111-1111-1111-111111111111" \
  -H "X-Project-Id: 00000000-0000-0000-0000-000000000001" \
  -H "X-User-Id: demo" \
  -d '{"gpu_pool_requested":"t4","isolation_level":"exclusive","target_url":"http://example","request_json":{"x":1}}'
```
