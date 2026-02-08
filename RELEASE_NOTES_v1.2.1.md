# Release Notes - v1.2.1 (2026-02-02)

Focus: **KIND demo readiness** (CTO/CEO demo), without MetalLB complexity.

## Added
- `scripts/kind/up.sh`: one-command demo bring-up (cluster -> ingress -> deploy -> migrations -> smoke test)
- `scripts/kind/bootstrap-db.sh`: applies SQL migrations via a short-lived job
- `scripts/kind/smoke-test.sh`: validates core endpoints and flows end-to-end

## Changed
- `scripts/kind/install-networking.sh`: now installs only ingress-nginx + tenant hosts (no MetalLB)
- `deploy/kind/kind-config.yaml`: uses kind default CNI by default (optional Calico via `ENABLE_CALICO=1`)
- `deploy/k8s/mlops-saas/overlays/kind/kustomization.yaml`: sets namespace and overrides remote ghcr images to local `mlops/*:dev`
