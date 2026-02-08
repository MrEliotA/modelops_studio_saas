from __future__ import annotations
import os
import asyncpg

async def create_pool():
    dsn = os.getenv("DATABASE_URL")
    if not dsn:
        raise RuntimeError("DATABASE_URL is required")
    return await asyncpg.create_pool(dsn)
