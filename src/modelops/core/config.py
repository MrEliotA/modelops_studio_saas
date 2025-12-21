from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MODELOPS_", extra="ignore")

    database_url: str = "postgresql+psycopg://modelops:modelops@localhost:5432/modelops"

    jwt_secret: str = "dev-secret"
    jwt_issuer: str = "modelops-studio"
    jwt_audience: str = "modelops-studio"
    jwt_ttl_seconds: int = 3600

    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "minio"
    s3_secret_key: str = "minio12345"
    s3_bucket: str = "artifacts"

    controller_tick_seconds: int = 2
    agent_tick_seconds: int = 2

    # Enable KEDA resources creation for serving workloads.
    keda_enabled: bool = False
    keda_min_replicas: int = 1
    keda_max_replicas: int = 5
    keda_cpu_utilization: int = 60

    # When true, workloads request real GPU resources.
    enable_real_gpu_requests: bool = False
    gpu_resource_fallback: str = "nvidia.com/gpu"

    # How pools are enforced:
    # - allocator: DB-backed allocator enforces capacity and tenant quotas (default for kind)
    # - kueue: rely on Kueue admission (production path)
    pool_enforcement: str = "allocator"  # allocator | kueue

    serving_backend: str = "deployment"  # deployment | kserve (scaffold)
    pipeline_backend: str = "mini"       # mini | kfp (scaffold)

    system_namespace: str = "modelops-system"


settings = Settings()
