# Kubeflow components

This directory contains GitOps-friendly installs for:
- **Kubeflow Pipelines (KFP)**
- **Kubeflow Trainer** (Training Operator v2)

## Kubeflow Pipelines

Path: `deploy/k8s/kubeflow/pipelines`

Installs:
- Cluster-scoped resources (CRDs + cluster roles)
- Platform-agnostic KFP manifests

> Reference: https://www.kubeflow.org/docs/components/pipelines/operator-guides/installation/

### Object store (S3)

KFP uses object storage for:
- Pipeline IR (API server)
- Input/Output artifacts (launcher / executor)

See:
- https://www.kubeflow.org/docs/components/pipelines/operator-guides/configure-object-store/

We provide an **example patch**:
- `deploy/k8s/kubeflow/pipelines/patches/ml-pipeline-object-store.patch.yaml`

You must also create a secret:

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: kfp-s3-creds
  namespace: kubeflow
type: Opaque
stringData:
  accessKey: "REPLACE_ME"
  secretKey: "REPLACE_ME"
```

## Kubeflow Trainer

Path: `deploy/k8s/kubeflow/trainer`

Installs:
- Trainer controller manager
- Training runtimes

Reference:
- https://www.kubeflow.org/docs/components/trainer/operator-guides/installation/
