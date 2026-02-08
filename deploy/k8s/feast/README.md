# Feast on Kubernetes (multi-tenant)

This deployment uses:
- One shared Redis (online store)
- One shared Postgres (registry + offline store), separated by schema per tenant
- One Feature Server per tenant (project)

Demo tenant IDs:
- tenant-a: 11111111-1111-1111-1111-111111111111
- tenant-b: 22222222-2222-2222-2222-222222222222

We recommend running `feast apply` via CI/CD. This repo includes an optional Job per tenant.

## Secrets

`deploy/k8s/feast/kustomization.yaml` no longer applies secrets by default.
Create `feast-postgres` and `feast-redis` via your secret manager.
For local demos you can apply `deploy/k8s/feast/secrets.example.yaml` after replacing values.
