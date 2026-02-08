# KServe examples

- `inferenceservice-canary.yaml`: Canary rollout example.
- `inferenceservice-batcher.yaml`: Request batching via KServe model agent sidecar.

Notes:
- Batching improves GPU utilization when requests are small.
- Batcher is only supported on KServe v1 HTTP protocol (not gRPC).



## KEDA autoscaling

KServe can autoscale `InferenceService` using KEDA when running in **RawDeployment** mode.
Use the examples:
- `inferenceservice-keda-cpu.yaml` (scale on CPU utilization)
- `inferenceservice-keda-prometheus.yaml` (placeholder for scaling on Prometheus/LLM metrics)

