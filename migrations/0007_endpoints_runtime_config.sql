-- 0007_endpoints_runtime_config.sql
-- Add runtime_config to endpoints for extensible serving configs (e.g., KServe/Triton/canary).
BEGIN;

ALTER TABLE endpoints
  ADD COLUMN IF NOT EXISTS runtime_config JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMIT;
