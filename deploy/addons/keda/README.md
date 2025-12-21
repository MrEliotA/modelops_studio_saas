# KEDA addon

This folder provides:
- an install script (Helm-based, recommended)
- optional metrics-server install for kind
- ScaledObject manifests for platform components
- optional HTTP add-on notes (advanced)

## Install KEDA
```bash
./deploy/addons/keda/install_keda.sh
```

## Kind: install metrics-server (required for CPU scaler)
```bash
./deploy/addons/keda/install_metrics_server_kind.sh
```

## Apply ScaledObjects (CPU scaler)
```bash
kubectl -n modelops-system apply -f deploy/addons/keda/scaledobjects/api-cpu.yaml
kubectl -n modelops-system apply -f deploy/addons/keda/scaledobjects/controller-cpu.yaml
kubectl -n modelops-system apply -f deploy/addons/keda/scaledobjects/agent-cpu.yaml
```

Serving deployments created by the platform will also receive an optional ScaledObject if
`MODELOPS_KEDA_ENABLED=true` is set on the controller (see `deploy/k8s/controller.yaml`).

## Prometheus scaler (production)
KEDA can scale on Prometheus queries when you have a Prometheus server.
See `scaledobjects/serving-prometheus-example.yaml` for a template.
