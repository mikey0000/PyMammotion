"""``MammotionClient``'s Aliyun auth-failure hook when the credential refresh is throttled.

The hook answers False to give the Aliyun transport up, so a ``RateLimitedError`` must
propagate instead and leave the transport to back off.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from pymammotion.http.model.http import RateLimitedError
from tests.unit._helpers import make_aliyun_session


@pytest.mark.regression
async def test_on_aliyun_auth_failure_raises_a_rate_limit_instead_of_giving_up() -> None:
    """A throttled refresh answered False, which the transport reads as "give this transport up"."""
    _client, session, transport = make_aliyun_session("old-tok")
    session.token_manager.refresh_aliyun_credentials = AsyncMock(
        side_effect=RateLimitedError("authorization/code", 3600.0)
    )

    with pytest.raises(RateLimitedError):
        await transport.on_auth_failure()
