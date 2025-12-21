# ModelOps Studio — Project Overview

ModelOps Studio is a Kubernetes-native ModelOps platform that provides:
- **Pipelines** (template -> run)
- **Training** (jobs with GPU pool selection)
- **Artifacts** (MinIO/S3)
- **Model registry** (models + versions)
- **Deployment/Serving** (runtime deployments)
- **Explain** (simple baseline endpoint)
- **Monitoring/Observability** (Prometheus/Grafana dashboards + metrics)
- **Metering/Billing** (usage ledger + invoices)

The repo includes two modes:
- `kind` (demo): single-machine, no real GPUs, fast demo
- `prod` (real cluster): persistent storage, real GPUs, autoscaling, full observability
