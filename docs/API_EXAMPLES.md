# API examples

Auth in this repo is intentionally minimal for a demo. We use an `X-Actor` header:

- Admin actor:
  - `X-Actor: admin|tenant=platform|role=admin`
- Tenant user actor:
  - `X-Actor: user|tenant=<TENANT_ID>|role=user`

> Replace `<TENANT_ID>` with the tenant id returned from `/v1/admin/tenants`.

## List built-in dashboards (Admin)
```bash
curl -sS -H 'X-Actor: admin|tenant=platform|role=admin'   'http://localhost:8000/v1/observability/dashboards?scope=admin'
```

## List dashboards for a tenant (User)
```bash
curl -sS -H 'X-Actor: user|tenant=<TENANT_ID>|role=user'   'http://localhost:8000/v1/observability/dashboards?scope=user&tenant_id=<TENANT_ID>'
```

## Create a custom user dashboard (stored in DB)
```bash
curl -sS -X POST -H 'Content-Type: application/json'   -H 'X-Actor: admin|tenant=platform|role=admin'   http://localhost:8000/v1/observability/dashboards   -d @./deploy/addons/observability/grafana/dashboards/modelops_user_runtime_resources.json
```
NOTE: For a real UI you would wrap the JSON payload with:
- scope, name, dashboard_json

## Export a dashboard as Grafana ConfigMap YAML
```bash
curl -sS -H 'X-Actor: admin|tenant=platform|role=admin'   'http://localhost:8000/v1/observability/dashboards/<DASH_ID>/export_configmap?namespace=monitoring' | jq -r .configmap_yaml
```

## Prometheus scrape endpoint
```bash
curl -sS http://localhost:8000/metrics | head
```

## Inference (predict)
```bash
curl -sS -X POST   -H 'Content-Type: application/json'   -H 'X-Actor: user|tenant=<TENANT_ID>|role=user'   http://localhost:8000/v1/deployments/<DEPLOYMENT_ID>/predict   -d '{"instances":[[0.1,0.2,0.3,0.4]]}'
```
