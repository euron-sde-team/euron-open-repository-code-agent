"""Short-lived distributed locks in Valkey, for writers of a repository's mirror.

SET NX with a random token and a TTL; release deletes the key only if it still holds our
token (a Lua compare-and-delete), so a lock that expired and was taken by another worker
is never released by the first one.
"""

from __future__ import annotations

import asyncio
import secrets
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from redis.asyncio import Redis

from codeagent.core.errors import ServiceUnavailableError

_RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


@asynccontextmanager
async def repository_lock(
    redis: Redis, repository_id: uuid.UUID, *, ttl_s: int = 600, wait_s: float = 300
) -> AsyncIterator[None]:
    key = f"lock:repo:{repository_id}"
    token = secrets.token_hex(16).encode()
    deadline = time.monotonic() + wait_s
    while not await redis.set(key, token, nx=True, ex=ttl_s):
        if time.monotonic() > deadline:
            raise ServiceUnavailableError("The repository is busy with another change. Try again.")
        await asyncio.sleep(0.5)
    try:
        yield
    finally:
        await redis.eval(_RELEASE, 1, key, token)
