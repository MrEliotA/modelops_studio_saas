import os, asyncio, json
import asyncpg
import nats
from nats.errors import TimeoutError
from nats.js.api import ConsumerConfig, AckPolicy, DeliverPolicy
import structlog
import mlflow
from contextlib import contextmanager

log = structlog.get_logger("training-worker")

@contextmanager
def nullcontext():
    yield

async def main():
    db = await asyncpg.create_pool(os.getenv("DATABASE_URL"))
    nc = await nats.connect(os.getenv("NATS_URL","nats://nats:4222"))
    js = nc.jetstream()

    tracking = os.getenv("MLFLOW_TRACKING_URI")
    if tracking:
        mlflow.set_tracking_uri(tracking)

    stream = "MLOPS_TRAINING"
    subject = "mlops.training.requested"
    durable = "training-worker"

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
            msgs = await sub.fetch(10, timeout=1)
        except TimeoutError:
            msgs = []

        for msg in msgs:
            try:
                evt = json.loads(msg.data.decode("utf-8"))
                job_id = evt["training_job_id"]

                async with db.acquire() as conn:
                    await conn.execute("UPDATE training_jobs SET status='RUNNING', updated_at=now() WHERE id=$1", job_id)

                ctx = mlflow.start_run(run_name=f"training-{job_id}") if tracking else nullcontext()
                with ctx:
                    if tracking:
                        # Persist MLflow run id for traceability.
                        try:
                            run_id_mlflow = mlflow.active_run().info.run_id
                            async with db.acquire() as conn:
                                await conn.execute("UPDATE training_jobs SET mlflow_run_id=$2, updated_at=now() WHERE id=$1", job_id, run_id_mlflow)
                        except Exception:
                            pass
                    if tracking:
                        mlflow.log_metric("loss", 0.1)

                await asyncio.sleep(2)

                async with db.acquire() as conn:
                    await conn.execute("UPDATE training_jobs SET status='SUCCEEDED', updated_at=now() WHERE id=$1", job_id)

                await msg.ack()
            except Exception as e:
                log.exception("failed_processing", error=str(e))

        await asyncio.sleep(0.2)

if __name__ == "__main__":
    asyncio.run(main())