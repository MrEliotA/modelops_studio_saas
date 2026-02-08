# MLOps-SaaS vs Amazon SageMaker (Studio + Pipelines + Registry + Hosting)

> Goal: help decide whether this platform can replace a SageMaker-centric stack
> (Studio, Pipelines, Model Registry, Hosting) and what is still missing.

## 1) Capability matrix (high-level)

| Capability | Amazon SageMaker | This project (current + planned) | What to implement / watch |
|---|---|---|---|
| Web IDE / Notebooks | SageMaker Studio | Not provided (out of scope) | If needed: JupyterHub on k8s, or VS Code Server, or keep internal company portal IDE |
| Training jobs | Managed Training Jobs (incl. distributed) | K8s Jobs + GPU pool + Kubeflow Pipelines | Add: distributed training operator (Kubeflow Training Operator / MPIJob / PyTorchJob) |
| Processing jobs | Processing jobs | K8s Jobs / KFP components | Add standard images + job templates |
| Batch inference | Batch Transform | KFP / Argo Workflows / K8s Jobs | Add a “BatchRun” API + queue + retries |
| Pipelines | SageMaker Pipelines | Kubeflow Pipelines | Now supported: template -> compiled YAML -> KFP run |
| Experiment tracking | SageMaker Experiments | MLflow Tracking (ArgoCD app) | Map tenant/project to MLflow experiment names |
| Model registry | SageMaker Model Registry | MLflow Model Registry (or custom) | Define stage transitions + approvals + RBAC |
| Online hosting | SageMaker Endpoints (real-time) | KServe (Kubeflow) + Ingress/Gateway | Add: canary/blue-green policies + autoscaling defaults |
| Monitoring (model/data) | Model Monitor, Clarify integrations | Prometheus/Grafana dashboards (MVP) | Add drift detection + data quality checks later |
| Explainability/Bias | SageMaker Clarify | Not provided | Optional: integrate Alibi / SHAP jobs in KFP |
| Profiler/Debugger | SageMaker Profiler/Debugger | OTEL + profiling per workload | Optional: PyTorch Profiler artifacts, Prometheus metrics |
| Feature Store | SageMaker Feature Store | Feast (multi-tenant) | Ensure offline store partitioning + online store quotas |
| Security & IAM | AWS IAM, VPC, KMS, private networking | API Gateway (Gateway API) + k8s RBAC + NetworkPolicy | Gateway API is the newer evolving standard for north-south routing; plan migration as needed |
| Multi-tenant isolation | Resource/Account isolation depends on design | Namespace per tenant + NetworkPolicy + (future) per-tenant quotas | Add ResourceQuota/LimitRange and PSA/OPA policies |
| Cost model | Pay-as-you-go managed services | Self-hosted infra + ops time | Cost shifts from AWS bills to hardware + SRE/ML ops workload |
| Lock-in | Higher (AWS APIs) | Lower (k8s/open-source) | Watch for hidden coupling (images, storage APIs) |

## 2) Recommended usage scenarios

### Prefer this project (k8s-native) when
- You must run on **bare-metal / on-prem** (data locality / compliance / GPU pool).
- You want **tooling portability** (Kubeflow, MLflow, KServe) and can invest in platform operations.
- You need **multi-tenant isolation** controlled by Kubernetes primitives (Namespaces/NetworkPolicies/Quotas).

### Prefer SageMaker when
- You want to minimize platform maintenance and use a managed ML suite.
- You need quick access to integrated managed features (Debugger/Profiler/Clarify/Model Monitor).
- Your org is already deeply standardized on AWS IAM/VPC/KMS.

## 3) Key risks (and mitigations)

- Ingress/Gateway strategy: treat Ingress as legacy for complex multi-tenant routing; plan a roadmap to adopt Gateway API if you need advanced routing and policy attachment.
- Template execution security: keep templates as compiled YAML (do not execute arbitrary Python from git) and add repo allowlists + signature verification later.
- Multi-tenancy blast radius: enforce namespace quotas, default-deny NetworkPolicies, and per-tenant service accounts.

## 4) Migration paths (two-way)

### SageMaker -> This project
1) Pipelines: export pipeline logic into KFP (or keep code as container steps) and store compiled YAML in git.
2) Registry: move models into MLflow Registry (same S3 artifact store) and map stages.
3) Hosting: deploy inference as KServe InferenceService; wire canary/blue-green using KServe traffic splitting.

### This project -> SageMaker
1) Pipelines: translate KFP components to SageMaker Pipelines steps.
2) Registry: publish models into SageMaker Model Registry (pipeline step).
3) Hosting: package inference into a SageMaker endpoint image or framework container.

