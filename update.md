# Updates

- v1.2 (2026-02-01)
  - Fixed BFF training route to use `/api/v1/training-jobs`
  - Completed template CRUD (`PUT`/`DELETE`) in template-service
  - Added artifacts `GET /api/v1/artifacts` in artifact-service (BFF already exposed it)
  - Implemented deployment-service CRUD + async deploy/delete events
  - Fixed GPU jobs INSERT SQL placeholder mismatch
  - Fixed feature-store-service DB access bug (removed non-existent `get_db`)
  - Removed unsafe prod secret placeholders; moved secrets to `.example` manifests and KIND overlay secret
  - docker-compose: stream-ingest-service now depends on postgres
  - NATS bootstrap script now uses shared stream definitions

- v1.2.1 (2026-02-02)
  - Simplified KIND environment for CTO/CEO demos (no MetalLB)
  - KIND overlay now applies namespace to infra resources (postgres/minio/nats)
  - Added image overrides for KIND so everything runs with local `mlops/*:dev` images
  - Added one-command demo script: `./scripts/kind/up.sh`
  - Added KIND DB bootstrap: `./scripts/kind/bootstrap-db.sh`
  - Added KIND smoke test: `./scripts/kind/smoke-test.sh`

- v1.2.2 (2026-02-03)
  - Removed legacy routing demo assets (router container + MetalLB manifests + old docs)
  - Tenant routers now inject `X-Roles: admin` by default, so demo endpoints work in a browser without custom headers
  - KIND smoke test output is now demo-friendly and prints ready-to-share URLs
  - NOTE: AUTH_MODE=passthrough trusts X-User-Id/X-Roles for demo only; in production add an API Gateway/Ingress to do AuthN/AuthZ (OIDC/JWT) and overwrite identity headers before forwarding.

## v2 - Stage 5C (Kyverno + image allowlist policy)
- Added Kyverno as a pinned Helm chart via ArgoCD (kyverno chart v3.7.0)
- Added ClusterPolicy to enforce image allowlist in tenant namespaces only

## v2 - Stage 5D (CNI standardization: Cilium)
- Standardized on Cilium as the single CNI option (removed Calico artifacts)
- KIND cluster now disables default CNI and installs Cilium automatically (NetworkPolicy enforcement)
- Added ArgoCD Applications to install Cilium via OCI Helm chart (pinned to 1.19.0)

## v2 - Stage 6 (KServe rollout templates + guardrails)
- Added YAML-only KFP templates for Canary, A/B (50/50), and Blue/Green (stage+promote) rollouts
- Updated KServe Triton deploy template to set protocolVersion=v2 by default
- Added Kyverno ClusterPolicy to validate rollout fields for tenant namespaces (canaryTrafficPercent range, Knative requirement, Triton protocol v2)
