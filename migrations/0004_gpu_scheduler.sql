-- GPU scheduling: fairness, quotas, and priority
-- Adds DISPATCHED state and per-tenant GPU policies.

ALTER TABLE gpu_jobs RENAME COLUMN gpu_pool TO gpu_pool_requested;

ALTER TABLE gpu_jobs
  ADD COLUMN IF NOT EXISTS gpu_pool_assigned TEXT,
  ADD COLUMN IF NOT EXISTS isolation_level TEXT NOT NULL DEFAULT 'shared', -- shared|isolated
  ADD COLUMN IF NOT EXISTS priority INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS dispatch_token UUID,
  ADD COLUMN IF NOT EXISTS dispatch_attempts INT NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS dispatched_at TIMESTAMPTZ;

-- Expand status lifecycle: QUEUED|DISPATCHED|RUNNING|SUCCEEDED|FAILED
ALTER TABLE gpu_jobs
  ALTER COLUMN status SET DEFAULT 'QUEUED';

CREATE TABLE IF NOT EXISTS tenant_gpu_policies (
  tenant_id UUID PRIMARY KEY,
  plan TEXT NOT NULL DEFAULT 'free', -- free|pro|enterprise
  t4_max_concurrency INT NOT NULL DEFAULT 1,
  mig_max_concurrency INT NOT NULL DEFAULT 0,
  max_queued_jobs INT NOT NULL DEFAULT 50,
  priority_boost INT NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_gpu_jobs_sched_queue
  ON gpu_jobs(status, gpu_pool_requested, priority DESC, requested_at ASC);

CREATE INDEX IF NOT EXISTS idx_gpu_jobs_dispatched
  ON gpu_jobs(status, dispatched_at);

