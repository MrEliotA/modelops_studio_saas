from __future__ import annotations

import json
import os
from dataclasses import dataclass

import boto3
import joblib
import numpy as np
from botocore.client import Config
from sklearn.datasets import load_digits
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split


@dataclass(frozen=True)
class S3Config:
    endpoint: str
    access_key: str
    secret_key: str
    bucket: str
    model_key: str
    metrics_key: str


def s3_client(cfg: S3Config):
    return boto3.client(
        "s3",
        endpoint_url=cfg.endpoint,
        aws_access_key_id=cfg.access_key,
        aws_secret_access_key=cfg.secret_key,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )


def ensure_bucket(s3, bucket: str) -> None:
    try:
        s3.head_bucket(Bucket=bucket)
    except Exception:
        s3.create_bucket(Bucket=bucket)


def main() -> None:
    cfg = S3Config(
        endpoint=os.environ["S3_ENDPOINT"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
        bucket=os.environ["S3_BUCKET"],
        model_key=os.environ["S3_MODEL_KEY"],
        metrics_key=os.environ["S3_METRICS_KEY"],
    )

    s3 = s3_client(cfg)
    ensure_bucket(s3, cfg.bucket)

    digits = load_digits()
    features = digits.data.astype(np.float32)
    y = digits.target.astype(np.int64)

    features_train, features_test, y_train, y_test = train_test_split(
        features, y, test_size=0.2, random_state=42, stratify=y
    )

    model = LogisticRegression(max_iter=500, n_jobs=1)
    model.fit(features_train, y_train)

    y_pred = model.predict(features_test)
    acc = float(accuracy_score(y_test, y_pred))

    model_path = "/tmp/model.pkl"
    joblib.dump(model, model_path)

    metrics = {
        "accuracy": acc,
        "n_train": int(features_train.shape[0]),
        "n_test": int(features_test.shape[0]),
    }
    metrics_path = "/tmp/metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f)

    s3.upload_file(model_path, cfg.bucket, cfg.model_key)
    s3.upload_file(metrics_path, cfg.bucket, cfg.metrics_key)

    print(json.dumps({"status": "ok", "model_key": cfg.model_key, "metrics": metrics}))


if __name__ == "__main__":
    main()
