# Kubeflow Pipelines (KFP) Integration

This project can submit pipeline runs to Kubeflow Pipelines (KFP) when the
`pipeline_backend` is set to `kfp`.

## 1) Configure API settings

Set environment variables for the API service:

```bash
export MODELOPS_PIPELINE_BACKEND=kfp
export MODELOPS_KFP_API_ENDPOINT=http://kubeflow-pipelines.kubeflow.svc.cluster.local:8888
# Optional auth for protected KFP deployments
export MODELOPS_KFP_API_TOKEN=<bearer-token>
# Optional default experiment (used when template does not provide experiment_id)
export MODELOPS_KFP_DEFAULT_EXPERIMENT_ID=<experiment-id>
```

## 2) Template format (KfpPipelineTemplate)

`PipelineTemplate.template_yaml` should use the following structure:

```yaml
kind: KfpPipelineTemplate
apiVersion: modelops.studio/v1alpha1
metadata:
  name: kfp-xgboost-iris
spec:
  description: Classic Iris classifier pipeline using XGBoost on Kubeflow Pipelines.
  kfp:
    pipeline_id: "<KFP_PIPELINE_ID>"
    pipeline_version_id: "<OPTIONAL_PIPELINE_VERSION_ID>"
    experiment_id: "<OPTIONAL_EXPERIMENT_ID>"
  parameters:
    - name: n_estimators
      type: int
      default: 200
```

> Note: the `pipeline_id` is required. Use the KFP UI or API to upload a pipeline
> package and obtain its `pipeline_id`.

## 3) Create a run

With the backend set to `kfp`, calling `POST /v1/pipelines/runs` will submit a KFP
run. The created `PipelineRun` will include a `kfp_run_id` in its `parameters` field.

## 4) Included KFP template stubs

The repo ships with popular pipeline templates for fast bootstrapping:

- `deploy/templates/kfp_xgboost_iris.yaml`
- `deploy/templates/kfp_pytorch_mnist.yaml`
- `deploy/templates/kfp_tfx_taxi.yaml`

Replace the placeholder IDs with the pipeline IDs from your KFP installation.
