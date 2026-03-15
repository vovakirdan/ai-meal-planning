from __future__ import annotations

import inspect

from redis.asyncio import Redis


def build_redis(redis_url: str) -> Redis:
    return Redis.from_url(redis_url, decode_responses=True)


async def verify_redis(redis_client: Redis) -> None:
    ping_result = redis_client.ping()
    if inspect.isawaitable(ping_result):
        ping_result = await ping_result

    if not ping_result:
        raise RuntimeError("Redis ping failed")
