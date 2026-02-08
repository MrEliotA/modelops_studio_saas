-- 0006_llm_modules.sql
BEGIN;

-- LLM evaluation runs (task -> metrics)
CREATE TABLE IF NOT EXISTS llm_eval_runs (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  task text NOT NULL,
  model_version_id uuid REFERENCES model_versions(id) ON DELETE SET NULL,
  input_count int NOT NULL,
  metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_llm_eval_tenant_project ON llm_eval_runs(tenant_id, project_id);

-- Labeling rules (keyword-based weak labeling)
CREATE TABLE IF NOT EXISTS labeling_rules (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL,
  project_id uuid NOT NULL,
  name citext NOT NULL,
  label text NOT NULL,
  keywords jsonb NOT NULL DEFAULT '[]'::jsonb,
  is_active boolean NOT NULL DEFAULT true,
  created_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, project_id, name)
);
CREATE INDEX IF NOT EXISTS idx_labeling_rules_tenant_project ON labeling_rules(tenant_id, project_id);
CREATE TRIGGER trg_labeling_rules_updated_at BEFORE UPDATE ON labeling_rules FOR EACH ROW EXECUTE FUNCTION set_updated_at();

COMMIT;
