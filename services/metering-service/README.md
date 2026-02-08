# metering-service

Ingests usage records into `usage_ledger`.

Endpoints:
- `POST /api/v1/usage` ingest a usage record
- `GET /api/v1/usage` list records
- `POST /api/v1/invoices` generate a simple invoice for a time window

Events:
- On usage ingest, publishes `mlops.metering.usage_recorded` (optional)

