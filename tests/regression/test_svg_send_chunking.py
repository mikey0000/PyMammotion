"""``send_svg`` owns the chunking; a caller that pre-chunks crashes it.

Mammotion-HA#868: the integration called ``chunk_svg_messages`` itself and passed the
resulting *list* to :meth:`MammotionClient.send_svg`, which chunks again — so the
second call did ``list.svg_message`` and raised
``AttributeError: 'list' object has no attribute 'svg_message'``.  Nothing was ever
transferred.  The parameter was typed ``Any``, so no type checker caught it.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from pymammotion.client import MammotionClient
from pymammotion.data.model.hash_list import SvgMessage
from pymammotion.data.model.svg import build_svg_for_area, chunk_svg_messages
from pymammotion.proto import CommDataCouple
from tests._helpers import make_bare_client

AREA_HASH = 1234567890


def _svg_message(payload_chars: int) -> SvgMessage:
    boundary = [CommDataCouple(x=0.0, y=0.0), CommDataCouple(x=10.0, y=10.0)]
    return build_svg_for_area(
        area_hash=AREA_HASH,
        boundary=boundary,
        svg_file_data="a" * payload_chars,
        svg_file_name="pattern.svg",
    )


def _client_with_handle() -> tuple[MammotionClient, MagicMock]:
    client = make_bare_client()
    handle = MagicMock()
    handle.device_name = "Luba-TEST0001"
    handle.enqueue_saga = AsyncMock()
    client._device_registry.get_by_name = MagicMock(return_value=handle)  # noqa: SLF001
    return client, handle


@pytest.mark.regression
async def test_send_svg_chunks_the_message_itself() -> None:
    """It must be handed one message, and it does the splitting."""
    client, handle = _client_with_handle()
    message = _svg_message(1200)

    await client.send_svg("Luba-TEST0001", message)

    saga = handle.enqueue_saga.await_args.args[0]
    assert saga._chunks == chunk_svg_messages(message), "send_svg must chunk the message it was given"  # noqa: SLF001
    assert all(isinstance(chunk, SvgMessage) for chunk in saga._chunks)


@pytest.mark.regression
async def test_a_pre_chunked_list_is_rejected_rather_than_mangled() -> None:
    """The reported crash: a caller chunked first, and the AttributeError came from deep inside.

    A list is not an SvgMessage; the type annotation says so now, and at runtime the
    failure should name the argument rather than surfacing as a missing attribute on a
    list several frames down.
    """
    client, _ = _client_with_handle()
    already_chunked = chunk_svg_messages(_svg_message(1200))

    with pytest.raises(TypeError, match="single SvgMessage"):
        await client.send_svg("Luba-TEST0001", already_chunked)  # type: ignore[arg-type]


async def test_a_single_frame_message_still_produces_one_chunk() -> None:
    client, handle = _client_with_handle()

    await client.send_svg("Luba-TEST0001", _svg_message(10))

    saga = handle.enqueue_saga.await_args.args[0]
    assert len(saga._chunks) == 1
