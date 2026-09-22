"""Mock factories used only by the unit tier.

Plain functions, not fixtures — matching tests/unit/transport/_fakes.py and
tests/unit/messaging/_helpers.py.  Builders the integration tier also needs live
in tests/_helpers.py; keep one superset builder per concept, so the per-file
variants can't drift apart (the exact failure mode _fakes.py's docstring warns
about).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
import time
from unittest.mock import AsyncMock, MagicMock

from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import JWTTokenInfo


def make_http_posting(
    status: int,
    body: dict,
    content_type: str = "application/json",
) -> tuple[MammotionHTTP, MagicMock]:
    """A MammotionHTTP whose ``_client_session`` requests return a canned response.

    Returns the session too, so callers can assert on url/json/headers.  The
    far-future ``expires_in`` keeps ``refresh_token_decorator`` from rotating.
    """
    http = MammotionHTTP()
    http.login_info = MagicMock(access_token="tok")  # type: ignore[assignment]
    http.expires_in = time.time() + 3600
    http.jwt_info = JWTTokenInfo(iot="https://iot.example", robot="https://robot.example")
    resp = MagicMock(status=status, headers={"Content-Type": content_type})
    resp.json = AsyncMock(return_value=body)
    session = MagicMock()
    # Both verbs: device-server mixes them (the product list is a GET, the error-code
    # endpoints are POSTs), and an unmocked one returns a non-awaitable MagicMock.
    session.post = AsyncMock(return_value=resp)
    session.get = AsyncMock(return_value=resp)

    @asynccontextmanager
    async def _fake_session() -> object:  # type: ignore[misc]
        yield session

    http._client_session = _fake_session  # type: ignore[method-assign]
    return http, session
