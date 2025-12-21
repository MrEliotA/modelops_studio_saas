from __future__ import annotations

import boto3
from botocore.client import Config

from modelops.core.config import settings


def client():
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def ensure_bucket() -> None:
    c = client()
    try:
        c.head_bucket(Bucket=settings.s3_bucket)
    except Exception:
        c.create_bucket(Bucket=settings.s3_bucket)


def s3_uri(key: str) -> str:
    return f"s3://{settings.s3_bucket}/{key}"
