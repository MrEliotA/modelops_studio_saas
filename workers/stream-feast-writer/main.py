from __future__ import annotations

import os
import json
import httpx
from mlops_common.nats_client import connect as nats_connect, ensure_streams
from mlops_common.logging import get_logger

log = get_logger("stream-feast-writer")

async def run():
    nats_url = os.getenv("NATS_URL", "nats://nats:4222")
    fs_url = os.getenv("FEATURE_STORE_SERVICE_URL", "").strip().rstrip("/")
    push_source = os.getenv("PUSH_SOURCE_NAME", "driver_stats_push_source")
    push_to = os.getenv("PUSH_TO", "online")

    if not fs_url:
        raise RuntimeError("FEATURE_STORE_SERVICE_URL is required")

    nc = await nats_connect(nats_url)
    js = nc.jetstream()
    await ensure_streams(js)

    sub = await js.subscribe(
        "mlops.stream.features",
        durable="stream-feast-writer",
        manual_ack=True,
        ack_wait=30,
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        async for msg in sub.messages:
            try:
                evt = json.loads(msg.data.decode("utf-8"))
                payload = evt.get("payload") or {}
                tenant_id = evt.get("tenant_id")
                project_id = evt.get("project_id")
                user_id = evt.get("user_id", "stream")

                df = payload.get("df")
                if not df:
                    await msg.ack()
                    continue

                req = {
                    "push_source_name": payload.get("push_source_name", push_source),
                    "df": df,
                    "to": payload.get("to", push_to),
                }

                headers = {
                    "X-Tenant-Id": tenant_id,
                    "X-Project-Id": project_id,
                    "X-User-Id": user_id,
                }
                r = await client.post(f"{fs_url}/api/v1/feast/push", json=req, headers=headers)
                if r.status_code >= 500 or r.status_code == 429:
                    # Transient error: retry by not acking (or explicit NAK if supported).
                    try:
                        await msg.nak()
                    except Exception:
                        pass
                    continue
                if 400 <= r.status_code < 500:
                    # Permanent error (bad payload/tenant): drop.
                    log.warning("push_failed_permanent", status=r.status_code, body=r.text[:200])
                    await msg.ack()
                    continue
                await msg.ack()
            except Exception as e:
                log.exception("stream_event_error", error=str(e))

    await nc.drain()

if __name__ == "__main__":
    import asyncio
    asyncio.run(run())
