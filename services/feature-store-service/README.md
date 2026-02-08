# feature-store-service

Platform facade for Feast.

- Routes by `X-Tenant-Id` to the correct tenant Feature Server
- Preserves tenancy and tracing headers
- Provides admin APIs to update tenant routing (optional)

Env:
- `DATABASE_URL` (required)
