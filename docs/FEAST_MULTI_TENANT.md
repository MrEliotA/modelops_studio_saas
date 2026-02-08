# Feast multi-tenant

Feast uses **projects** as the top-level namespace. In this platform we model each tenant as a distinct Feast project.
Because a Feature Server is configured with a single feature repository, we run one Feature Server per tenant.

## Demo tenants
This repo ships two fixed tenant IDs:

- tenant-a: `11111111-1111-1111-1111-111111111111`
- tenant-b: `22222222-2222-2222-2222-222222222222`

## Routing model
`feature-store-service` routes requests based on `X-Tenant-Id`:
- Tenant -> Feast base URL (Feature Server) + Feast project name

The mapping is stored in the platform database table `feature_store_tenants` and seeded on startup for the demo tenants.

## Stream ingestion
Streaming events are ingested via `stream-ingest-service` and published to JetStream:
- `mlops.stream.features`

`stream-feast-writer` consumes the stream and calls `feature-store-service` which forwards the request to the correct tenant Feature Server `/push`.

## Production deployment
Production uses ArgoCD apps in `deploy/argocd/apps-prod/`:
- `feast-redis` (online store)
- `feast-postgres` (registry + offline store)
- `feast-feature-server-tenant-a`
- `feast-feature-server-tenant-b`
- Optional: `feast-feature-repos` (runs `feast apply` as a Job)

