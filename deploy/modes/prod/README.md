# Production mode (real cluster)

This mode is intended for a real Kubernetes cluster.

## What you get
- Same platform components as kind mode (API, Controller, Agent, Postgres, MinIO)
- Persistent volumes for stateful dependencies
- Optional KEDA autoscaling
- Optional Prometheus/Grafana stack

## 1) Deploy core platform
```bash
make prod-deploy NAMESPACE=modelops-system
```

## 2) Install KEDA (optional)
```bash
make keda-install
make keda-apply NAMESPACE=modelops-system
```

## 3) Observability (optional)
```bash
make obs-install
```

## GPU notes (T4 + A30)
- T4 time-slice: request `nvidia.com/gpu: 1` (time-slicing configured in NVIDIA device plugin)
- A30 MIG: request the MIG resource name exposed by the device plugin (example: `nvidia.com/mig-1g.6gb`)

This repo stores GPU resource naming per pool, so the same code can:
- run in kind (no GPU request)
- run in prod (real GPU request) by enabling the env var `MODELOPS_ENABLE_REAL_GPU_REQUESTS=true`.
