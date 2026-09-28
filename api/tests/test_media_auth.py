"""Media credentials must bind one connection to one call across workers."""
import asyncio
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from redis.asyncio import Redis

from api.services.telephony import media_auth
from api.routes.telephony import websocket_endpoint, _handle_telephony_websocket
from api.enums import WorkflowRunState


@pytest.mark.asyncio
async def test_media_ticket_is_single_use_and_bound_to_call():
    run_id = uuid.uuid4().int
    token = await media_auth.issue_media_token(10, 20, run_id)
    assert not await media_auth.consume_media_token(token, 11, 20, run_id)
    token = await media_auth.issue_media_token(10, 20, run_id)
    assert await media_auth.consume_media_token(token, 10, 20, run_id)
    assert not await media_auth.consume_media_token(token, 10, 20, run_id)
    async with Redis.from_url(media_auth.REDIS_URL) as redis:
        await redis.delete(f"telephony:media-connected:{run_id}")


@pytest.mark.asyncio
async def test_two_valid_tickets_cannot_start_same_run_twice():
    run_id = uuid.uuid4().int
    tokens = [await media_auth.issue_media_token(10, 20, run_id) for _ in range(2)]
    results = await asyncio.gather(*(media_auth.consume_media_token(t, 10, 20, run_id) for t in tokens))
    assert sorted(results) == [False, True]
    async with Redis.from_url(media_auth.REDIS_URL) as redis:
        await redis.delete(f"telephony:media-connected:{run_id}")


@pytest.mark.asyncio
async def test_expired_ticket_is_rejected():
    token = await media_auth.issue_media_token(10, 20, uuid.uuid4().int)
    async with Redis.from_url(media_auth.REDIS_URL) as redis:
        assert 0 < await redis.ttl(f"telephony:media-token:{token}") <= media_auth.MEDIA_TOKEN_TTL
        await redis.pexpire(f"telephony:media-token:{token}", 1)
        await asyncio.sleep(0.02)
    assert not await media_auth.consume_media_token(token, 10, 20, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("token", [None, "forged"])
async def test_unauthenticated_media_does_not_accept_or_mutate(token):
    ws = AsyncMock()
    with patch('api.routes.telephony._handle_telephony_websocket', new_callable=AsyncMock) as handler:
        await websocket_endpoint(ws, 10, 20, 30, token)
    ws.accept.assert_not_awaited()
    ws.close.assert_awaited_once_with(code=4403, reason="Invalid media credential")
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_valid_ticket_reaches_handler_once():
    run_id = uuid.uuid4().int
    token = await media_auth.issue_media_token(10, 20, run_id)
    ws = AsyncMock()
    with patch('api.routes.telephony._handle_telephony_websocket', new_callable=AsyncMock) as handler:
        await websocket_endpoint(ws, 10, 20, run_id, token)
    ws.accept.assert_awaited_once()
    handler.assert_awaited_once_with(ws, 10, 20, run_id)
    async with Redis.from_url(media_auth.REDIS_URL) as redis:
        await redis.delete(f"telephony:media-connected:{run_id}")


@pytest.mark.asyncio
@pytest.mark.parametrize("run_workflow,owner", [(999,20), (10,999)])
async def test_media_rejects_mismatched_workflow_or_owner(run_workflow, owner):
    ws = AsyncMock()
    with patch('api.routes.telephony.db_client') as db:
        db.get_workflow_run = AsyncMock(return_value=SimpleNamespace(workflow_id=run_workflow, state=WorkflowRunState.INITIALIZED.value))
        db.get_workflow_by_id = AsyncMock(return_value=SimpleNamespace(id=10, user_id=owner))
        db.update_workflow_run = AsyncMock()
        await _handle_telephony_websocket(ws,10,20,30)
    db.update_workflow_run.assert_not_awaited()
    ws.close.assert_awaited_once_with(code=4403, reason="Call context mismatch")
