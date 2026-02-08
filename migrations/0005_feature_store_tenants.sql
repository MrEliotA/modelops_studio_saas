-- Feature store tenant routing (Feast multi-tenant).
CREATE TABLE IF NOT EXISTS feature_store_tenants (
  tenant_id UUID PRIMARY KEY,
  feast_base_url TEXT NOT NULL,
  feast_project TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Demo tenants (safe upsert).
INSERT INTO feature_store_tenants (tenant_id, feast_base_url, feast_project)
VALUES
  ('11111111-1111-1111-1111-111111111111', 'http://feast-feature-server-tenant-a.feast.svc.cluster.local:6566', 'tenant_a'),
  ('22222222-2222-2222-2222-222222222222', 'http://feast-feature-server-tenant-b.feast.svc.cluster.local:6566', 'tenant_b')
ON CONFLICT (tenant_id) DO UPDATE SET
  feast_base_url = EXCLUDED.feast_base_url,
  feast_project = EXCLUDED.feast_project,
  updated_at = now();
