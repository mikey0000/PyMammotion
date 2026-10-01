"""Read the non-secret claims out of an Agora AccessToken2 (``007…``) without validating it.

The cloud mints one token per camera slot; which viewer uid each is bound to decides whether
two camera entities can join a channel side by side. Only the claims are exposed, never the
signature or the token text.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
import struct
import zlib

TOKEN_VERSION = "007"  # noqa: S105 — the AccessToken2 format prefix, not a credential
SERVICE_RTC = 1
SERVICE_RTM = 2
SERVICE_FPA = 4
SERVICE_CHAT = 5
SERVICE_APAAS = 7
_ONE_STRING_SERVICES = frozenset({SERVICE_RTM, SERVICE_CHAT})  # privileges, then one user-id string


@dataclass(frozen=True)
class AgoraTokenClaims:
    """The claims of an AccessToken2: the app it was issued for and, per RTC service, channel and uid."""

    app_id: str
    issued_at: int
    expires_in: int
    channel_name: str | None = None
    uid: str | None = None
    privileges: dict[int, int] = field(default_factory=dict)

    @property
    def uid_int(self) -> int | None:
        """The uid as an integer, or ``None`` when the token is a wildcard (empty uid) or non-numeric."""
        return int(self.uid) if self.uid and self.uid.isdigit() else None


class _Reader:
    def __init__(self, data: bytes) -> None:
        self._data = data
        self._pos = 0

    def uint16(self) -> int:
        (value,) = struct.unpack_from("<H", self._data, self._pos)
        self._pos += 2
        return value

    def uint32(self) -> int:
        (value,) = struct.unpack_from("<I", self._data, self._pos)
        self._pos += 4
        return value

    def string(self) -> str:
        length = self.uint16()
        value = self._data[self._pos : self._pos + length]
        self._pos += length
        return value.decode("utf-8", errors="replace")

    def int_map(self) -> dict[int, int]:
        return {self.uint16(): self.uint32() for _ in range(self.uint16())}


def decode_agora_token(token: str) -> AgoraTokenClaims:
    """Decode the claims of a ``007`` token.

    Raises:
        ValueError: The token is not a version-007 AccessToken2 or is malformed.

    """
    if not token.startswith(TOKEN_VERSION):
        raise ValueError("not a version-007 Agora token")
    try:
        content = zlib.decompress(base64.b64decode(token[len(TOKEN_VERSION) :]))
        reader = _Reader(content)
        reader.string()  # signature, not needed
        app_id = reader.string()
        issued_at = reader.uint32()
        expires_in = reader.uint32()
        reader.uint32()  # salt
        claims = AgoraTokenClaims(app_id=app_id, issued_at=issued_at, expires_in=expires_in)
        for _ in range(reader.uint16()):
            service_type = reader.uint16()
            privileges = reader.int_map()
            if service_type == SERVICE_RTC:
                channel_name = reader.string()
                uid = reader.string()
                claims = AgoraTokenClaims(
                    app_id=app_id,
                    issued_at=issued_at,
                    expires_in=expires_in,
                    channel_name=channel_name,
                    uid=uid,
                    privileges=privileges,
                )
            elif service_type in _ONE_STRING_SERVICES:
                reader.string()  # user id
            elif service_type == SERVICE_APAAS:
                reader.string()
                reader.string()
                reader.uint16()
            elif service_type != SERVICE_FPA:
                break  # unknown layout; the RTC service was not among the ones read
    except (ValueError, struct.error, zlib.error) as exc:
        raise ValueError("malformed Agora token") from exc
    return claims


def describe_agora_token(token: str) -> str:
    """Describe a token for a log line: its uid, channel and expiry, never the token itself."""
    try:
        claims = decode_agora_token(token)
    except ValueError as exc:
        return f"<undecodable: {exc}>"
    return f"uid={claims.uid or '<wildcard>'} channel={claims.channel_name} expires_in={claims.expires_in}s"
