"""Short-lived, single-use media credentials shared across API workers."""

import json
import secrets

from redis.asyncio import Redis

from api.constants import REDIS_URL

MEDIA_TOKEN_TTL = 600


async def issue_media_token(workflow_id: int, user_id: int, run_id: int) -> str:
    token = secrets.token_urlsafe(32)
    async with Redis.from_url(REDIS_URL, decode_responses=True) as redis:
        await redis.set(
            f"telephony:media-token:{token}",
            json.dumps([workflow_id, user_id, run_id]),
            ex=MEDIA_TOKEN_TTL,
        )
    return token


async def media_websocket_url(base: str, workflow_id: int, user_id: int, run_id: int) -> str:
    token = await issue_media_token(workflow_id, user_id, run_id)
    return f"{base}/api/v1/telephony/ws/{workflow_id}/{user_id}/{run_id}/{token}"


async def consume_media_token(token: str | None, workflow_id: int, user_id: int, run_id: int) -> bool:
    if not token or len(token) > 128:
        return False
    async with Redis.from_url(REDIS_URL, decode_responses=True) as redis:
        payload = await redis.getdel(f"telephony:media-token:{token}")
        if payload != json.dumps([workflow_id, user_id, run_id]):
            return False
        # Different valid tickets for one run must not start two pipelines.
        return bool(await redis.set(f"telephony:media-connected:{run_id}", "1", nx=True, ex=86400))
