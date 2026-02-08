# control-plane-api

The **BFF (Backend For Frontend)**. It is the main entrypoint for the internal panel/UI.

## Responsibilities
- Validates tenancy headers (`X-Tenant-Id`, `X-Project-Id`, ...)
- Authenticates the caller (MVP)
- Aggregates and proxies requests to internal services
- Emits NATS events for workers

## Auth modes

### AUTH_MODE=passthrough (default)
Trust identity headers set by a *trusted edge*.

Accepted identity headers:
- `X-User-Id` (legacy)

Accepted roles headers (optional):
- `X-Roles` / `X-User-Roles`

> WARNING: `passthrough` is **not safe** if the service is directly reachable from untrusted clients.

### AUTH_MODE=dev-jwt
Local/demo mode. Accepts `Authorization: Bearer <HS256 JWT>`.

Env:
- `JWT_SECRET`

## Tenancy headers
Required for most endpoints:
- `X-Tenant-Id`
- `X-Project-Id`

### Tenant routing (subdomain / path)
When `TENANT_ROUTING_MODE=auto` (default), the control-plane can derive tenancy *without* the caller sending `X-Tenant-Id`.

Supported patterns:
- Subdomain: `https://<tenant>.<TENANT_BASE_DOMAIN>/api/v1/...`
- Path prefix: `https://<base-domain><TENANT_PATH_PREFIX>/<tenant>/api/v1/...` (default prefix is `/t`)

The slug -> UUID mapping is read from a JSON file:
- `TENANT_MAP_FILE=/etc/mlops/tenant-map/tenant-map.json`

If the request does not include `X-Project-Id`, and the mapping contains a `project_id`, the control-plane injects it as the default.

> NOTE: Internal service-to-service calls should keep using explicit `X-Tenant-Id` / `X-Project-Id`.

## Health checks
Tenancy is skipped for:
- `/api/v1/healthz`

Override via:
- `TENANCY_SKIP_PATHS`
