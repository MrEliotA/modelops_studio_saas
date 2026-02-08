# training-worker (demo)

In production this worker would:
- schedule a K8s Job / Kubeflow Training / Ray job
- log metrics + artifacts to MLflow
- emit events for model registration

This dev worker currently listens to `mlops.training.requested` (not emitted in the demo flow yet).
