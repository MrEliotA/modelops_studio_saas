# Feast multi-tenant demo

Demo tenants:
- tenant-a: 11111111-1111-1111-1111-111111111111
- tenant-b: 22222222-2222-2222-2222-222222222222

## Start (local)
```bash
docker compose up -d --build
docker compose -f docker-compose.feast-mt.yml up -d
```

## Push streaming features (tenant-a)
```bash
curl -X POST http://localhost:8013/api/v1/streams/features/events \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: 11111111-1111-1111-1111-111111111111" \
  -H "X-Project-Id: 00000000-0000-0000-0000-000000000001" \
  -H "X-User-Id: demo" \
  -d @push-driver-stats.json
```

## Read online features via platform facade (tenant-a)
```bash
curl -X POST http://localhost:8012/api/v1/feast/get-online-features \
  -H "Content-Type: application/json" \
  -H "X-Tenant-Id: 11111111-1111-1111-1111-111111111111" \
  -H "X-Project-Id: 00000000-0000-0000-0000-000000000001" \
  -H "X-User-Id: demo" \
  -d @get-online-features.json
```
