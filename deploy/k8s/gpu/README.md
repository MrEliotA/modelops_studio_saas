# NVIDIA GPU (production-only)

Recommended approach: install **NVIDIA GPU Operator** in production. The operator manages:
- NVIDIA driver (optional)
- NVIDIA Container Toolkit
- Kubernetes device plugin
- GPU Feature Discovery (node labels)
- DCGM exporter for Prometheus metrics

## GitOps (ArgoCD)
Use `deploy/argocd/app-of-apps-prod.yaml` (includes `gpu-operator.yaml`).

## Optional: standalone device plugin
If you do not use GPU Operator, you can deploy the standalone device plugin:
- `nvidia-device-plugin.yaml`

## Smoke tests
- `runtimeclass-nvidia.yaml` (optional)
- `smoke/full-gpu-smoke.yaml`
- `smoke/mig-smoke.yaml`
