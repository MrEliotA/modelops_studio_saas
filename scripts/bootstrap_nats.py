import os, asyncio

from mlops_common.nats_client import connect, ensure_streams

async def main():
    nc = await connect()
    js = nc.jetstream()
    # Uses the shared DEFAULT_STREAMS list from mlops_common
    await ensure_streams(js)
    await nc.drain()

if __name__ == "__main__":
    asyncio.run(main())
