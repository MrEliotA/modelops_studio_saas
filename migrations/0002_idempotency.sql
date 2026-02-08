-- 0002_idempotency.sql
BEGIN;
CREATE TABLE IF NOT EXISTS idempotency_keys (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  idem_key text NOT NULL,
  method text NOT NULL,
  path text NOT NULL,
  request_hash text NOT NULL,
  status_code integer,
  response_headers jsonb NOT NULL DEFAULT '{}'::jsonb,
  response_body bytea,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_idem_expires ON idempotency_keys(expires_at);
CREATE UNIQUE INDEX IF NOT EXISTS uniq_idem ON idempotency_keys(tenant_id, project_id, idem_key, method, path);
COMMIT;
