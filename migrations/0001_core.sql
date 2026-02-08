-- 0001_core.sql
BEGIN;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Templates
CREATE TABLE IF NOT EXISTS templates (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  name citext NOT NULL,
  description text,
  git_repo text NOT NULL,
  git_ref text NOT NULL,
  entrypoint text NOT NULL,
  compiler text NOT NULL,
  default_parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, name)
);
CREATE TRIGGER trg_templates_updated_at BEFORE UPDATE ON templates FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Runs
CREATE TABLE IF NOT EXISTS runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  template_id uuid REFERENCES templates(id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'QUEUED',
  parameters jsonb NOT NULL DEFAULT '{}'::jsonb,
  compute_profile text,
  kfp_run_id text,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_runs_tenant_project ON runs(tenant_id, project_id);
CREATE TRIGGER trg_runs_updated_at BEFORE UPDATE ON runs FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Training jobs
CREATE TABLE IF NOT EXISTS training_jobs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  run_id uuid REFERENCES runs(id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'QUEUED',
  compute_profile text,
  image text,
  command jsonb NOT NULL DEFAULT '[]'::jsonb,
  dataset_uri text,
  output_uri text,
  mlflow_run_id text,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_training_tenant_project ON training_jobs(tenant_id, project_id);
CREATE TRIGGER trg_training_updated_at BEFORE UPDATE ON training_jobs FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Model registry (internal façade)
CREATE TABLE IF NOT EXISTS models (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  name citext NOT NULL,
  description text,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id, project_id, name)
);
CREATE TRIGGER trg_models_updated_at BEFORE UPDATE ON models FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS model_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  model_id uuid NOT NULL REFERENCES models(id) ON DELETE CASCADE,
  version int NOT NULL,
  artifact_uri text,
  source_run_id uuid REFERENCES runs(id) ON DELETE SET NULL,
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  stage text,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(model_id, version)
);
CREATE INDEX IF NOT EXISTS idx_model_versions_model ON model_versions(model_id);
CREATE TRIGGER trg_model_versions_updated_at BEFORE UPDATE ON model_versions FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Endpoints / serving
CREATE TABLE IF NOT EXISTS endpoints (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  name citext NOT NULL,
  status text NOT NULL DEFAULT 'CREATING',
  url text,
  runtime text NOT NULL DEFAULT 'kserve',
  model_id uuid REFERENCES models(id) ON DELETE SET NULL,
  model_version_id uuid REFERENCES model_versions(id) ON DELETE SET NULL,
  traffic jsonb NOT NULL DEFAULT '{}'::jsonb,
  autoscaling jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id, project_id, name)
);
CREATE TRIGGER trg_endpoints_updated_at BEFORE UPDATE ON endpoints FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Artifacts (metadata)
CREATE TABLE IF NOT EXISTS artifacts (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  kind text NOT NULL,
  uri text NOT NULL,
  content_type text,
  size_bytes bigint,
  checksum text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_artifacts_tenant_project ON artifacts(tenant_id, project_id);
CREATE TRIGGER trg_artifacts_updated_at BEFORE UPDATE ON artifacts FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- Metering
CREATE TABLE IF NOT EXISTS usage_ledger (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  subject_type text NOT NULL,
  subject_id uuid,
  meter text NOT NULL,
  quantity numeric NOT NULL,
  labels jsonb NOT NULL DEFAULT '{}'::jsonb,
  window_start timestamptz,
  window_end timestamptz,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_usage_tenant_project ON usage_ledger(tenant_id, project_id);

CREATE TABLE IF NOT EXISTS invoices (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  period_start date NOT NULL,
  period_end date NOT NULL,
  currency text NOT NULL DEFAULT 'USD',
  total_amount numeric NOT NULL DEFAULT 0,
  lines jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL DEFAULT 'DRAFT',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_invoices_tenant_project ON invoices(tenant_id, project_id);

-- LLM: RAG indexes/docs/chunks (pgvector)
-- We fix embedding dimension to 1536 for simplicity.
CREATE TABLE IF NOT EXISTS rag_indexes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  name citext NOT NULL,
  embedding_model text NOT NULL DEFAULT 'local-hash-v1',
  dims int NOT NULL DEFAULT 1536,
  distance text NOT NULL DEFAULT 'cosine',
  chunking jsonb NOT NULL DEFAULT '{"strategy":"fixed","chunk_size":800,"overlap":120}'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(tenant_id, project_id, name)
);
CREATE TRIGGER trg_rag_indexes_updated_at BEFORE UPDATE ON rag_indexes FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS rag_documents (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  index_id uuid NOT NULL REFERENCES rag_indexes(id) ON DELETE CASCADE,
  external_id text,
  title text,
  source_uri text,
  content text NOT NULL,
  content_hash text NOT NULL,
  doc_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(index_id, external_id)
);
CREATE INDEX IF NOT EXISTS idx_rag_docs_index ON rag_documents(index_id);
CREATE TRIGGER trg_rag_docs_updated_at BEFORE UPDATE ON rag_documents FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TABLE IF NOT EXISTS rag_chunks (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  index_id uuid NOT NULL REFERENCES rag_indexes(id) ON DELETE CASCADE,
  document_id uuid NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
  chunk_no int NOT NULL,
  start_char int NOT NULL,
  end_char int NOT NULL,
  text text NOT NULL,
  chunk_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  embedding vector(1536),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_doc ON rag_chunks(document_id);
-- Vector index (HNSW with cosine operator class). If the extension build lacks HNSW, comment this out.
CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding_hnsw
  ON rag_chunks USING hnsw (embedding vector_cosine_ops);

COMMIT;
