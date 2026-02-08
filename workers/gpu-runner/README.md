# gpu-dispatcher + executor (workers/gpu-runner)

This worker package provides **production-grade GPU job execution** using ephemeral Kubernetes Jobs.

## Components

### 1) Dispatcher (`main.py`)
Consumes dispatch subjects from NATS JetStream:

- `mlops.gpu.jobs.dispatched.t4.shared`
- `mlops.gpu.jobs.dispatched.t4.exclusive`
- `mlops.gpu.jobs.dispatched.mig`

Execution modes:
- `GPU_EXECUTION_MODE=direct` (dev): runs the job in-process (no Kubernetes API)
- `GPU_EXECUTION_MODE=k8s_job` (prod): creates a **Kubernetes Job** per GPU job

### 2) Executor (`executor.py`)
Runs inside the ephemeral Kubernetes Job:

- updates status `DISPATCHED -> RUNNING -> (SUCCEEDED|FAILED)`
- stores `response_json` / `error`
- writes a metering record in `usage_ledger` (`meter=gpu_seconds`)

## Required env

Common:
- `DATABASE_URL`
- `NATS_URL`

Dispatcher (k8s_job mode):
- `GPU_EXECUTOR_IMAGE` (container image that contains this worker)
- `GPU_JOB_NAMESPACE` (default: mlops-system)
- `GPU_RESOURCE_NAME` (default: nvidia.com/gpu; for MIG use nvidia.com/mig-*)
- `GPU_NODE_SELECTOR_KEY` / `GPU_NODE_SELECTOR_VALUE`

Executor:
- `JOB_ID`
- `DISPATCH_TOKEN`
- `GPU_EXECUTOR` (simulate|http)
- `HTTP_TIMEOUT_SECONDS`

## Related docs
- `docs/GPU_QUEUE.md`
- `docs/GPU.md`
