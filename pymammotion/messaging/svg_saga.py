"""SvgSendSaga — sends a multi-frame SVG tile to the device with per-frame ACK."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import betterproto2

from pymammotion.messaging.saga import Saga
from pymammotion.transport import TransportError

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from pymammotion.data.model.hash_list import SvgMessage
    from pymammotion.messaging.broker import DeviceMessageBroker

_logger = logging.getLogger(__name__)


class SvgSendSaga(Saga):
    """Send a (possibly multi-frame) SVG tile to the device.

    The APK (``sendSvgDataBean``) sends each frame individually and waits for
    a ``toapp_svg_msg`` ACK before sending the next.  The device echoes
    ``current_frame`` and ``sub_cmd`` in its response; the final frame's
    response carries the device-assigned ``data_hash``.

    Usage::

        from pymammotion.utility.svg import build_svg_for_area, chunk_svg_messages

        msg    = build_svg_for_area(area_hash, boundary, svg_data)
        chunks = chunk_svg_messages(msg)
        saga   = SvgSendSaga(chunks, handle.commands, handle.send_raw)
        await handle.enqueue_saga(saga)
        device_hash = saga.result_hash  # device-assigned hash for future UPDATE/DELETE

    Prefer :meth:`~pymammotion.client.MammotionClient.send_svg` for the
    common case — it handles chunking and enqueuing in one call.

    Attributes:
        result_hash: Device-assigned ``data_hash`` from the final frame ACK.
                     ``None`` until the saga completes successfully.

    """

    name = "svg_send"
    max_attempts = 3
    step_timeout = 15.0

    def __init__(
        self,
        chunks: list[SvgMessage],
        command_builder: Any,
        send_command: Callable[[bytes], Awaitable[None]],
    ) -> None:
        """Initialise the saga.

        Args:
            chunks:          Per-frame messages from :func:`~pymammotion.utility.svg.chunk_svg_messages`.
            command_builder: Navigation command builder exposing ``send_svg_data(svg_message)``.
            send_command:    Async callable that transmits raw bytes to the device.

        """
        if not chunks:
            msg = "SvgSendSaga requires at least one frame"
            raise ValueError(msg)
        self._chunks = chunks
        self._command_builder = command_builder
        self._send_command = send_command
        self.result_hash: int | None = None

    async def _run(self, broker: DeviceMessageBroker) -> None:
        """Send all frames sequentially, waiting for a device ACK after each."""
        self.result_hash = None
        expected_sub_cmd = self._chunks[0].sub_cmd

        with self._collect_frames(broker, "toapp_svg_msg", lambda v: v.sub_cmd == expected_sub_cmd) as frame_queue:
            for i, chunk in enumerate(self._chunks):
                cmd = self._command_builder.send_svg_data(chunk)
                await self._send_command(cmd)

                msg = await self._next_frame(frame_queue, "toapp_svg_msg", chunk.current_frame)

                _, nav_val = betterproto2.which_one_of(msg, "LubaSubMsg")
                if nav_val is None:
                    raise ValueError(f"Unexpected message type in SVG response: {msg}")

                ack = nav_val.toapp_svg_msg

                _logger.debug(
                    "SvgSendSaga[%s]: frame %d/%d ack result=%d hash=%d",
                    self.device_name,
                    ack.current_frame,
                    ack.total_frame,
                    ack.result,
                    ack.data_hash,
                )

                if ack.result != 0:
                    # Device rejected the frame — abort instead of streaming the
                    # remaining chunks and reporting success with a bogus data_hash.
                    msg = f"SvgSendSaga: device rejected frame {ack.current_frame}/{ack.total_frame} (result={ack.result})"
                    raise TransportError(msg)

                if i == len(self._chunks) - 1:
                    self.result_hash = ack.data_hash
