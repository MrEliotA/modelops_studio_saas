# Observability (Prometheus + Grafana)

This repo is designed to work with **kube-prometheus-stack** (Prometheus Operator + Grafana + kube-state-metrics + node-exporter).

## Install stack
```bash
./deploy/addons/observability/install_kube_prometheus_stack.sh
```

## Install ModelOps dashboards (ConfigMaps)
```bash
./deploy/addons/observability/apply_dashboards.sh monitoring
```

## Install ServiceMonitor (scrape ModelOps services)
```bash
kubectl apply -f deploy/addons/observability/k8s/servicemonitors/modelops-services.yaml
```

## Grafana access
```bash
kubectl -n monitoring port-forward svc/kps-grafana 3000:80
# then open http://localhost:3000
```

## Where dashboards live
- JSON source of truth:
  - `deploy/addons/observability/grafana/dashboards/`
- ConfigMaps for Grafana sidecar import:
  - `deploy/addons/observability/k8s/dashboards/`

NOTE: kube-prometheus-stack enables the Grafana dashboards sidecar by default in many setups.
If your chart differs, enable the sidecar or use manual import.
