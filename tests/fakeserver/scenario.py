"""Mutable scenario state shared by the fake HTTP API and MQTT brokers.

Everything a test (or the /control API) can flip lives here, together with
counters so tests can assert *exactly* how many oauth2/token, invoke, or MQTT
CONNECT attempts the library made — the whole point of the auth work is that
those counts stay bounded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import secrets
import time

import jwt

#: Signing key for every JWT the fake mints.  Signatures are never verified by
#: the client (it decodes with verify_signature=False), so any key works.
JWT_KEY = "x" * 32

DEACTIVATED_MSG = "Your account activity is abnormal and has been deactivated"
BAD_CREDENTIALS_MSG = "The user name or password is incorrect"


@dataclass
class FakeDevice:
    """The one mower the fake account owns (post-2025, Mammotion-direct)."""

    product_key: str = "FAKEPK9QS"
    device_name: str = "Luba-FAKE01"
    iot_id: str = "iot-fake-luba-000001"
    identity_id: str = "819000000000000001"


@dataclass
class Scenario:
    """All injectable state, with sane 'everything healthy' defaults."""

    account: str = "test@example.com"
    password: str = "test-password"
    user_account: str = "8190001"
    device: FakeDevice = field(default_factory=FakeDevice)

    # --- HTTP OAuth ---------------------------------------------------
    #: (code, msg) returned by the password grant instead of a login, or None.
    login_reject: tuple[int, str] | None = None
    #: True → every refresh grant answers 40102 "Refresh token has expired".
    refresh_rejected: bool = False
    #: Force this HTTP status on /oauth2/token (e.g. 429, 500) — transient path.
    oauth_http_status: int | None = None
    #: Lifetime of minted access tokens (exp claim). Short values force the
    #: client's proactive refresh; default keeps it quiet.
    access_token_ttl: float = 7200.0

    # --- Bearer-token registry ----------------------------------------
    valid_access_tokens: set[str] = field(default_factory=set)
    current_refresh_token: str | None = None

    # --- Mammotion MQTT ------------------------------------------------
    #: Lifetime of the broker JWT (exp claim); < 1800 forces refetch every call.
    mqtt_jwt_ttl: float = 86400.0
    #: When True the JWT endpoint answers 200 with no ``data``, which is how the
    #: Mammotion broker credential fetch fails *without* the HTTP login being bad —
    #: the transport-scoped case (``TokenManager.mqtt_unavailable``).
    mqtt_jwt_returns_no_data: bool = False
    #: CONNACK return code for the Mammotion broker (0 accept, 4/5 auth reject).
    mammotion_connack_rc: int = 0

    # --- mqtt_invoke ----------------------------------------------------
    #: ok | http_401 | body_401 | body_460 | offline | gateway_timeout | error
    invoke_mode: str = "ok"

    # --- Aliyun MQTT -----------------------------------------------------
    bind_reply_code: int = 200
    aliyun_connack_rc: int = 0

    # --- Counters ---------------------------------------------------------
    counters: dict[str, int] = field(default_factory=dict)

    def count(self, name: str) -> None:
        self.counters[name] = self.counters.get(name, 0) + 1

    # Token minting / validation

    def age_cached_access_token(self, cache: dict, remaining: float = 60.0) -> None:
        """Rewrite *cache*'s access token so it expires in *remaining* seconds.

        Use this instead of minting the original token near-expiry.  A short
        ``access_token_ttl`` at login time leaves the client's refresh scheduler
        permanently inside its 300 s HTTP lead window, so it refreshes as fast as the
        loop allows for the whole of setup — which both floods the counters a test is
        about to assert on and races anything the test does next.

        The token's other claims are preserved, and it replaces the old one in
        ``valid_access_tokens`` so the server still accepts it.
        """
        login = cache["mammotion_data"].data
        claims = jwt.decode(login.access_token, options={"verify_signature": False})
        claims["exp"] = int(time.time()) + int(remaining)
        aged = jwt.encode(claims, JWT_KEY, algorithm="HS256")
        self.valid_access_tokens.discard(login.access_token)
        self.valid_access_tokens.add(aged)
        login.access_token = aged
        login.expires_in = int(remaining)

    def mint_login_data(self, base_url: str) -> dict:
        """Issue a fresh access/refresh token pair as an oauth2/token `data` blob."""
        now = int(time.time())
        access_token = jwt.encode(
            {
                "iot": base_url,
                "robot": base_url,
                "exp": now + int(self.access_token_ttl),
                "iat": now,
                "jti": secrets.token_hex(8),
            },
            JWT_KEY,
            algorithm="HS256",
        )
        self.valid_access_tokens.add(access_token)
        self.current_refresh_token = f"rt-{secrets.token_hex(8)}"
        return {
            "access_token": access_token,
            "token_type": "bearer",
            "refresh_token": self.current_refresh_token,
            "expires_in": int(self.access_token_ttl),
            "authorization_code": f"authcode-{secrets.token_hex(6)}",
            "userInformation": {
                "areaCode": "44",
                "domainAbbreviation": "EU",
                "userId": "fake-user-1",
                "userAccount": self.user_account,
                "authType": "0",
                "email": self.account,
            },
        }

    def mint_broker_jwt(self) -> str:
        now = int(time.time())
        return jwt.encode(
            {
                "clientId": "fake-mqtt-client-1",
                "username": self.device.identity_id,
                "location": "eu",
                "client_attrs": {"identityId": self.device.identity_id, "connectType": "app"},
                "iat": now,
                "exp": now + int(self.mqtt_jwt_ttl),
            },
            JWT_KEY,
            algorithm="HS256",
        )

    def bearer_ok(self, authorization: str | None) -> bool:
        """Is the Authorization header a live, unexpired access token?"""
        if not authorization or not authorization.startswith("Bearer "):
            return False
        token = authorization.removeprefix("Bearer ")
        if token not in self.valid_access_tokens:
            return False
        try:
            claims = jwt.decode(token, options={"verify_signature": False})
        except Exception:  # noqa: BLE001
            return False
        return float(claims.get("exp", 0)) > time.time()

    # Control actions

    def revoke_access_tokens(self) -> None:
        """Server-side revocation: every bearer becomes invalid (401s) while its
        local exp still looks fine — the 'signed in elsewhere' case."""
        self.valid_access_tokens.clear()

    def revoke_refresh_token(self) -> None:
        """The 40102 case: the refresh token no longer works, ever."""
        self.refresh_rejected = True

    def deactivate_account(self) -> None:
        """The case from the field: password logins rejected as abnormal activity."""
        self.login_reject = (20105, DEACTIVATED_MSG)
        self.refresh_rejected = True
        self.valid_access_tokens.clear()

    def expire_session(self) -> None:
        """Full server-side session death: bearers dead AND refresh dead."""
        self.revoke_access_tokens()
        self.revoke_refresh_token()

    def reset(self) -> None:
        """Back to a healthy cloud (keeps the account/device identity)."""
        self.login_reject = None
        self.refresh_rejected = False
        self.oauth_http_status = None
        self.access_token_ttl = 7200.0
        self.mqtt_jwt_ttl = 86400.0
        self.mqtt_jwt_returns_no_data = False
        self.mammotion_connack_rc = 0
        self.aliyun_connack_rc = 0
        self.invoke_mode = "ok"
        self.bind_reply_code = 200
        self.valid_access_tokens.clear()
        self.current_refresh_token = None
        self.counters.clear()
