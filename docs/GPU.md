# GPU in production (NVIDIA GPU Operator + T4 time-slicing + MIG)

This repo supports two GPU modes in production:

1) **T4 time-slicing** (shared GPU on a single physical card)  
2) **MIG** on A100/A30-class GPUs (hard partitioning)

> GPU add-ons are production-only in this repo.

---

## What the platform does (and does not do)

- The platform **requests** GPU resources in Kubernetes (e.g. `nvidia.com/gpu`, `nvidia.com/mig-1g.5gb`).
- The platform **does not** implement CUDA kernels. Your training/inference image (PyTorch/TensorRT/etc) contains CUDA code.

---

## NVIDIA GPU Operator (production)

The production ArgoCD app installs the NVIDIA GPU Operator:
- driver + container toolkit
- device plugin
- DCGM exporter (Prometheus GPU metrics)
- optional MIG manager

Files:
- `deploy/argocd/apps-prod/gpu-operator.yaml`

---

## T4 time-slicing (shared GPU)

### Device plugin config

The operator configures time-slicing via a device-plugin ConfigMap (Helm values), for example:

- `tesla-t4` profile advertises **8 replicas** of `nvidia.com/gpu` per physical T4.

Node labeling (recommended if you have multiple GPU types):
```bash
kubectl label node <t4-node> nvidia.com/device-plugin.config=tesla-t4 --overwrite
```

### Scheduler settings

The GPU scheduler uses these env vars (production overlay sets defaults):
- `T4_SHARED_SLOTS=8` (matches time-slicing replicas)
- `T4_EXCLUSIVE_SLOTS=1`

### Shared vs exclusive jobs

When a user submits a GPU job:
- `isolation_level=shared` → may run concurrently (best throughput)
- `isolation_level=exclusive` → runs alone (soft exclusivity for better isolation)

Soft exclusivity means:
- while an exclusive job is running, shared jobs are not dispatched
- while shared jobs are running, exclusive jobs wait until idle

---

## MIG (hard partitioning)

With MIG enabled, the node advertises resources like:
- `nvidia.com/mig-1g.5gb`
- `nvidia.com/mig-2g.10gb`
- ...

This repo keeps MIG flexible by letting ops configure:
- `GPU_RESOURCE_NAME` on `gpu-dispatcher-mig` (e.g. `nvidia.com/mig-1g.5gb`)

Later you can extend job requests to include a preferred MIG profile/size and let the scheduler select it.

---

## Production execution model (ephemeral K8s Job)

For better GPU memory cleanup and simpler operations:

- `gpu-dispatcher-*` is CPU-only and consumes dispatch events
- it creates an **ephemeral Kubernetes Job** per dispatched GPU job
- the Job runs `workers/gpu-runner/executor.py` and requests GPU resources
- the Job is auto-cleaned via `ttlSecondsAfterFinished`

RBAC:
- `deploy/k8s/mlops-saas/base/rbac/gpu-job-launcher-rbac.yaml`

Docs:
- `docs/GPU_QUEUE.md`
