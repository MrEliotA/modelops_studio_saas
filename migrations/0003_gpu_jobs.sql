-- GPU jobs: async inference / GPU queue
CREATE TABLE IF NOT EXISTS gpu_jobs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id UUID NOT NULL,
  project_id UUID NOT NULL,
  status TEXT NOT NULL DEFAULT 'QUEUED', -- QUEUED|RUNNING|SUCCEEDED|FAILED
  gpu_pool TEXT NOT NULL DEFAULT 't4', -- t4|mig|custom
  target_url TEXT NOT NULL,
  request_json JSONB NOT NULL,
  response_json JSONB,
  error TEXT,
  created_by TEXT,
  requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  started_at TIMESTAMPTZ,
  finished_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_gpu_jobs_tenant_project_time
  ON gpu_jobs(tenant_id, project_id, requested_at DESC);

CREATE INDEX IF NOT EXISTS idx_gpu_jobs_status_time
  ON gpu_jobs(status, requested_at DESC);
