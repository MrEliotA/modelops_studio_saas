# MLOps SaaS (MVP)

A minimal, GitOps-friendly **multi-tenant MLOps control-plane** that runs on a shared Kubernetes cluster.

This repo is a clean starting point for:
- Multi-tenant MLOps APIs
- Async workers with NATS JetStream
- Kubeflow Pipelines backend
- KServe model serving

> MVP version.

---

## High-level architecture


graph TD
  UI[UI] -->|HTTPS| EDGE[API Gateway]
  EDGE --> BFF[Control Plane API]

  BFF --> DB[(Postgres)]
  BFF --> NATS[(NATS)]

  subgraph Workers
    RO[Run Orchestrator]
    TW[Training Worker]
    DW[Deployment Worker]
  end

  NATS --> RO
  NATS --> TW
  NATS --> DW

  RO --> KFP[Kubeflow Pipelines]
  DW --> KS[KServe]
  KS --> IS[Inference Service]
  IS --> GPU[GPU Nodes]

  BFF --> REG[Registry]
  REG --> OBJ[(Object Store)]

  BFF --> TPL[Template Service]



### Edge / Auth options

- **Demo / kind**: either
  - Direct NodePort (30080) to control-plane-api + Host header (tenant-a.mlops.local)
  - Or via Envoy Gateway (port-forward to :30081) + Host header
- **Production**: Envoy Gateway is the default edge entrypoint in this repo. main panel can still handle AuthN/AuthZ and forward identity headers to the BFF.

---

## Documentation

- Architecture: `docs/ARCHITECTURE.md`
- Environments: `docs/ENVIRONMENTS.md`
- Serving (KServe/Triton/Rollout): `docs/SERVING.md`
- SageMaker comparison: `docs/SAGEMAKER_COMPARISON.md`

## Multi-tenancy headers

All APIs expect these headers:

- `X-Tenant-Id`
- `X-Project-Id`
- `X-User-Id`
- `X-Roles` (optional, comma or whitespace separated)

### Demo vs production

- `AUTH_MODE=passthrough` is intended for **demo**: it trusts `X-User-Id`/`X-Roles`.
- In production, only use passthrough if the control-plane is reachable **only** through a trusted edge.
- Planned upgrades:
  - JWT verification mode (`AUTH_MODE=jwt`)
  - Policy-based authorization (OPA/Kyverno integration)

---

## Templates (YAML-only, allowlisted)

Templates are stored as **catalog entries** and executed as **pipeline YAML packages**.

Key properties:
- No `git clone` for user-provided repos in the cluster
- No pipeline compilation step during execution
- `run-orchestrator` fetches the pipeline YAML from template-service:
  - `GET /api/v1/templates/{template_id}/package`

See:
- `services/template-service/catalog/`
- `workers/run-orchestrator/`

---

## Local dev (docker compose)

```bash
make up
```

Endpoints:
- Control plane: http://localhost:8000
- NATS: http://localhost:8222
- Postgres: localhost:5432

---

## Kind demo

```bash
./scripts/kind/up.sh
```

Demo (direct NodePort):
```bash
curl -H "Host: tenant-a.mlops.local" http://localhost:30080/api/v1/overview
```

Demo (via API gateway):
```bash
# terminal 1
./scripts/kind/port-forward-gateway.sh

# terminal 2
curl -H "Host: tenant-a.mlops.local" http://localhost:30081/api/v1/overview
```

---

## Production GitOps (ArgoCD)

1) Apply:
- `deploy/argocd/app-of-apps-prod.yaml`

2) ArgoCD syncs everything under:
- `deploy/argocd/apps-prod/`

Included apps (baseline):
- `mlops-saas` (platform)
- `monitoring` + dashboards
- `kubeflow-pipelines`
- `kserve`
- `gpu-operator`
- `networking` (tenant namespaces + NetworkPolicy)
- `envoy-gateway-crds` + `envoy-gateway` (Gateway API controller)
- `api-gateway` (tenant-aware HTTPRoutes)

---

## Health endpoints

To keep Kubernetes liveness/readiness probes working without tenancy headers, tenancy is skipped for:
- `/api/v1/healthz`
- `/healthz`
- `/metrics`

Override via:
- `TENANCY_SKIP_PATHS` (comma separated, supports `*` suffix for prefixes)

---

## License

Internal / private.
