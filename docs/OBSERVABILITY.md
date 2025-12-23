# Observability (best-practice notes)

This repo intentionally separates observability into:
- **Admin view**: platform reliability + capacity + cost
- **User view**: per project/deployment health + saturation

Key design decisions:
- Latency uses **histograms** (server-side quantiles in Prometheus).
- Route labels use **templates** (bounded cardinality).
- Runtime exposes saturation metrics (inflight, queue depth, queue wait).
- GPU pools expose allocator metrics (capacity, utilization, jobs pending/running).
- GPU node metrics come from **DCGM Exporter** (utilization, memory, power, temperature).

Operational add-ons you may add later:
- OpenTelemetry traces for end-to-end correlation.
- Centralized logging (Loki/ELK).
- Alerting rules and runbooks.
