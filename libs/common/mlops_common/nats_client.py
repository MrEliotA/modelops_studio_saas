from __future__ import annotations
import os
import json
import asyncio
from typing import Any, Optional

import nats
from nats.aio.client import Client as NATS
from nats.js.api import StreamConfig, RetentionPolicy, StorageType

DEFAULT_STREAMS = [
    ("MLOPS_RUNS", ["mlops.runs.*"]),
    ("MLOPS_TRAINING", ["mlops.training.*"]),
    ("MLOPS_SERVING", ["mlops.serving.*"]),
    ("MLOPS_METERING", ["mlops.metering.*"]),
    ("MLOPS_GPU", ["mlops.gpu.*"]),
    ("MLOPS_STREAM", ["mlops.stream.*"]),
]


async def connect() -> NATS:
    url = os.getenv("NATS_URL", "nats://localhost:4222")
    return await nats.connect(url)

async def ensure_streams(js):
    # Create streams if not exist (workqueue retention for task semantics).
    # NOTE: multiple services may race on startup; swallow 'already exists' errors.
    for name, subjects in DEFAULT_STREAMS:
        try:
            await js.stream_info(name)
            continue
        except Exception:
            pass

        cfg = StreamConfig(
            name=name,
            subjects=subjects,
            retention=RetentionPolicy.WORK_QUEUE,
            storage=StorageType.FILE,
            max_age=7 * 24 * 3600,
        )
        try:
            await js.add_stream(cfg)
        except Exception:
            # likely created by another service concurrently
            pass

async def publish(js, subject: str, payload: dict[str, Any]):
    data = json.dumps(payload).encode("utf-8")
    await js.publish(subject, data)
