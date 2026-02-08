# Monitoring

This repo uses:
- kube-prometheus-stack (Prometheus Operator + Grafana)
- DCGM exporter (usually enabled via NVIDIA GPU Operator)

Dashboards:
- `deploy/k8s/monitoring-dashboards/` contains Grafana dashboard ConfigMaps.
