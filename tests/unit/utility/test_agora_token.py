"""Decoding the non-secret claims of an Agora AccessToken2."""

from __future__ import annotations

import base64
import zlib

import pytest

from pymammotion.utility.agora_token import decode_agora_token, describe_agora_token
from tests.unit._helpers import agora_service, make_agora_token


def _truncated_token() -> str:
    """A validly compressed body that ends mid-field."""
    content = zlib.decompress(base64.b64decode(make_agora_token()[3:]))
    return "007" + base64.b64encode(zlib.compress(content[:20])).decode()


class TestDecodeAgoraToken:
    def test_reads_app_channel_uid_and_expiry(self) -> None:
        claims = decode_agora_token(make_agora_token(app_id="app-x", channel="4Dgdkg", uid="64077101"))

        assert (claims.app_id, claims.channel_name, claims.uid, claims.uid_int) == ("app-x", "4Dgdkg", "64077101", 64077101)
        assert (claims.issued_at, claims.expires_in) == (1_700_000_000, 3600)
        assert claims.privileges == {1: 3600, 2: 3600}

    def test_an_empty_uid_is_a_wildcard(self) -> None:
        claims = decode_agora_token(make_agora_token(uid=""))

        assert claims.uid == ""
        assert claims.uid_int is None

    @pytest.mark.parametrize(
        "leading",
        [
            agora_service(2, {}, "rtm-user"),
            agora_service(5, {1: 10}, "chat-user"),
            agora_service(7, {}, "room", "user") + b"\x01\x00",
            agora_service(4, {}),
        ],
        ids=["rtm", "chat", "apaas", "fpa"],
    )
    def test_skips_the_other_service_layouts_before_rtc(self, leading: bytes) -> None:
        assert decode_agora_token(make_agora_token(uid="7", leading_services=(leading,))).uid == "7"

    def test_an_unknown_service_before_rtc_yields_no_rtc_claims(self) -> None:
        claims = decode_agora_token(make_agora_token(uid="7", leading_services=(agora_service(99, {}, "x"),)))

        assert claims.uid is None
        assert claims.channel_name is None

    @pytest.mark.parametrize(
        "token",
        ["006abc", "", "007not-base64!!", "007" + base64.b64encode(b"nope").decode(), _truncated_token()],
        ids=["v006", "empty", "not-base64", "not-zlib", "truncated"],
    )
    def test_rejects_other_versions_and_garbage(self, token: str) -> None:
        with pytest.raises(ValueError, match="Agora token"):
            decode_agora_token(token)


class TestDescribeAgoraToken:
    def test_names_uid_and_channel_only(self) -> None:
        assert describe_agora_token(make_agora_token(channel="chan-1", uid="2")) == "uid=2 channel=chan-1 expires_in=3600s"

    def test_describes_a_bad_token_without_raising(self) -> None:
        assert describe_agora_token("garbage").startswith("<undecodable")
