# Architecture overview

This system follows a controller-style pattern:
- The API writes desired state into the database.
- The Controller reconciles pipelines/jobs/deployments to actual Kubernetes resources.
- The Agent meters completed jobs and releases pool allocations.

Backends are pluggable:
- Pipeline backend: `mini` (default demo), `kfp` (Kubeflow Pipelines scaffold)
- Serving backend: `deployment` (default demo), `kserve` (KServe scaffold)
- HPO backend: `none` (default), `katib` (Katib scaffold)

The demo uses a Kind-friendly approach:
- Pools are enforced via node labels/taints and an allocation service in the control plane.
- Jobs do not request real `nvidia.com/gpu` resources on kind.
- In a real GPU cluster, you can switch to Kueue + GPU Operator and request actual GPU resources.
