# Release Notes - v1.2.2 (2026-02-03)

Focus: **KIND demo polish** + remove legacy routing demo complexity.

## Changes
- Removed legacy routing demo assets (router container script, MetalLB manifests, old networking docs).
- Tenant routers now inject `X-Roles: admin` by default, so key demo endpoints work in a browser with **no custom headers**.
- KIND smoke test output is now demo-friendly and prints ready-to-share URLs (use `VERBOSE=1` for detailed logs).

## How to demo
```bash
./scripts/kind/up.sh
```

Then open:
- `http://tenant-a.127.0.0.1.nip.io:8080/api/v1/overview`
- `http://tenant-a.127.0.0.1.nip.io:8080/docs`
