import os, asyncio, json
import nats
from nats.errors import TimeoutError
from nats.js.api import ConsumerConfig, AckPolicy, DeliverPolicy
import structlog

log = structlog.get_logger("metering-worker")

async def main():
    nc = await nats.connect(os.getenv("NATS_URL","nats://nats:4222"))
    js = nc.jetstream()

    stream = "MLOPS_METERING"
    subject = "mlops.metering.usage_recorded"
    durable = "metering-worker"

    try:
        await js.add_consumer(stream, ConsumerConfig(
            durable_name=durable,
            ack_policy=AckPolicy.EXPLICIT,
            deliver_policy=DeliverPolicy.ALL,
            filter_subject=subject,
        ))
    except Exception:
        pass

    sub = await js.pull_subscribe(subject, durable=durable, stream=stream)
    log.info("worker_started", stream=stream, subject=subject)

    while True:
        try:
            msgs = await sub.fetch(20, timeout=1)
        except TimeoutError:
            msgs = []

        for msg in msgs:
            try:
                evt = json.loads(msg.data.decode("utf-8"))
                log.info("usage_event", usage_id=evt.get("usage_id"), meter=evt.get("meter"), quantity=evt.get("quantity"))
                await msg.ack()
            except Exception as e:
                log.exception("failed_processing", error=str(e))

        await asyncio.sleep(0.2)

if __name__ == "__main__":
    asyncio.run(main())
