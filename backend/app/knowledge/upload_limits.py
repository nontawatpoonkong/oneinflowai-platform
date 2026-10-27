"""Fail-closed knowledge upload limits shared by every application instance.

Two Redis-backed controls run after authentication and the knowledge.manage
check, before the file is read or parsed:

- fixed-window counters per user and per Workspace, so switching the
  Workspace header does not reset a user's allowance;
- per-Workspace parse leases, so one Workspace cannot occupy every worker.
  Each lease is a sorted-set member that expires on its own, so a crashed
  worker cannot hold capacity forever.

When Redis is unavailable the upload is refused (503) instead of running
without limits.
"""

import math
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress

from fastapi import Depends, Request
from redis.exceptions import RedisError

from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.core.exceptions import (
    KnowledgeUploadLimitUnavailableError,
    KnowledgeUploadRateLimitedError,
)
from app.core.logging import get_logger
from app.models.user import User
from app.models.workspace import Workspace
from app.services.public_rate_limit import PublicRateLimitService
from app.services.workspace_capability import WorkspaceCapability
from app.workspace.dependencies import require_workspace_capability

logger = get_logger(__name__)

_knowledge_manage = require_workspace_capability(WorkspaceCapability.KNOWLEDGE_MANAGE)
# A lease outlives the parse deadline by this much to cover storage and
# chunking around it.
_LEASE_MARGIN_SECONDS = 60

_ACQUIRE_LEASE_SCRIPT = """
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', ARGV[1])
if redis.call('ZCARD', KEYS[1]) >= tonumber(ARGV[4]) then
  return 0
end
redis.call('ZADD', KEYS[1], ARGV[2], ARGV[3])
redis.call('EXPIRE', KEYS[1], ARGV[5])
return 1
"""
_RELEASE_LEASE_SCRIPT = "return redis.call('ZREM', KEYS[1], ARGV[1])"
_REDIS_ERRORS = (RedisError, OSError, TimeoutError)


async def enforce_knowledge_upload_limits(
    request: Request,
    user: User = Depends(get_current_user),
    workspace: Workspace = Depends(_knowledge_manage),
) -> AsyncIterator[None]:
    settings = get_settings()
    redis = request.app.state.redis
    window = settings.KNOWLEDGE_UPLOAD_RATE_LIMIT_WINDOW_SECONDS
    lease_key = f"knowledge-parse-leases:{workspace.id}"
    lease_id = uuid.uuid4().hex
    lease_seconds = settings.KNOWLEDGE_PARSE_TIMEOUT_SECONDS + _LEASE_MARGIN_SECONDS
    try:
        for namespace, identity, allowance in (
            (
                "knowledge-upload:user",
                str(user.id),
                settings.KNOWLEDGE_UPLOAD_RATE_LIMIT_PER_USER,
            ),
            (
                "knowledge-upload:workspace",
                str(workspace.id),
                settings.KNOWLEDGE_UPLOAD_RATE_LIMIT_PER_WORKSPACE,
            ),
        ):
            result = await PublicRateLimitService(
                redis, requests=allowance, window_seconds=window
            ).check(namespace, identity)
            if not result.allowed:
                raise KnowledgeUploadRateLimitedError(result.retry_after_seconds)
        now = time.time()
        acquired = await redis.eval(
            _ACQUIRE_LEASE_SCRIPT,
            1,
            lease_key,
            now,
            now + lease_seconds,
            lease_id,
            settings.KNOWLEDGE_MAX_CONCURRENT_PARSES_PER_WORKSPACE,
            math.ceil(lease_seconds),
        )
    except _REDIS_ERRORS:
        logger.warning("knowledge.upload_limit.unavailable")
        raise KnowledgeUploadLimitUnavailableError() from None
    if not int(acquired):
        raise KnowledgeUploadRateLimitedError(5)
    try:
        yield
    finally:
        # The lease also expires by itself, so a failed release only delays
        # the next upload instead of blocking the Workspace.
        with suppress(*_REDIS_ERRORS):
            await redis.eval(_RELEASE_LEASE_SCRIPT, 1, lease_key, lease_id)
