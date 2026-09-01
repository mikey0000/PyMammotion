"""SVG map-tile utilities — building and positioning SVG shapes within mowing areas.

Protocol notes (from APK MACommandHelper / SvgDataBean analysis)
-----------------------------------------------------------------
SVG tiles use the ``todev_svg_msg`` (``svg_message_ack_t``) nav proto field.

Sub-command values
~~~~~~~~~~~~~~~~~~
- ``1`` — **ADD**: send a new SVG tile to the device.  ``data_hash`` must be
  ``0``; the device assigns the real hash and returns it in its response.
- ``2`` — **ACK**: app acknowledges receipt of SVG data the device pushed.
  No ``svg_message`` body is included.  Use :func:`build_svg_ack`.
- ``3`` — **UPDATE**: replace an existing tile.  Use the device-assigned hash
  from the ADD response.
- ``6`` — **DELETE**: remove a tile by its device-assigned hash.

Frame counting
~~~~~~~~~~~~~~
Single-frame SVG messages use ``total_frame=0, current_frame=0`` (APK convention).
For multi-frame large payloads, use 1-based counting with the total number of
frames.

Pixel dimensions
~~~~~~~~~~~~~~~~
``base_width_pix`` and ``base_height_pix`` are sent as ``0`` by the APK — the
device derives rendering size from the metre dimensions and the screen DPI.

Name count
~~~~~~~~~~
``name_count`` must equal ``len(svg_file_name)`` so the device knows how many
bytes to read for the filename string.
"""

from __future__ import annotations

import dataclasses

from pymammotion.data.model.hash_list import CommDataCouple, SvgMessage, SvgMessageData

#: Default SVG base dimensions in metres.  Luba 1 / Yuka use 2.5 m; Luba 2 uses 4.0 m.
_BASE_M_DEFAULT: float = 2.5
_BASE_M_LUBA2: float = 4.0


def area_centroid(boundary: list[CommDataCouple]) -> tuple[float, float]:
    """Return the centroid (cx, cy) of a closed polygon in device-local ENU metres.

    Uses the standard shoelace / surveyor's formula for polygon centroids,
    which weights each vertex by the area of the triangle it forms with the
    origin.  Falls back to the arithmetic mean when the polygon is degenerate
    (collinear points or a single point).

    Args:
        boundary: Ordered boundary vertices in device-local ENU coordinates.

    Returns:
        ``(cx, cy)`` centroid in metres.

    """
    n = len(boundary)
    if n == 0:
        return 0.0, 0.0
    if n == 1:
        return boundary[0].x, boundary[0].y

    signed_area = 0.0
    cx = 0.0
    cy = 0.0
    for i in range(n):
        j = (i + 1) % n
        cross = boundary[i].x * boundary[j].y - boundary[j].x * boundary[i].y
        signed_area += cross
        cx += (boundary[i].x + boundary[j].x) * cross
        cy += (boundary[i].y + boundary[j].y) * cross

    signed_area *= 0.5
    if abs(signed_area) < 1e-10:
        # Degenerate polygon — fall back to simple mean
        return (
            sum(p.x for p in boundary) / n,
            sum(p.y for p in boundary) / n,
        )

    cx /= 6.0 * signed_area
    cy /= 6.0 * signed_area
    return cx, cy


def build_svg_for_area(
    area_hash: int,
    boundary: list[CommDataCouple],
    svg_file_data: str,
    *,
    svg_file_name: str = "pattern.svg",
    scale: float = 1.0,
    rotate: float = 0.0,
    base_width_m: float = _BASE_M_DEFAULT,
    base_height_m: float = _BASE_M_DEFAULT,
) -> SvgMessage:
    """Build an ADD :class:`SvgMessage` centred within a mowing area.

    The position (``x_move``, ``y_move``) is the polygon centroid of *boundary*,
    rounded to 3 decimal places to match the APK's ``BaseUtil.keepf(value, 3)``.

    ``data_hash`` is left as ``0`` — the device assigns the real hash on
    receipt and returns it in its acknowledgement.  Store the device-assigned
    hash if you later need to UPDATE or DELETE this tile.

    ``name_count`` is set to ``len(svg_file_name)`` as required by the device.

    Args:
        area_hash:     Hash of the parent mowing area; becomes ``paternal_hash_a``.
        boundary:      Ordered boundary vertices in device-local ENU metres
                       (from ``HashList.area[area_hash]``).
        svg_file_data: Raw SVG markup to embed, or the filename of a built-in
                       device pattern (in which case pass ``""`` here and set
                       ``svg_file_name`` to the pattern name, e.g. ``"circle.svg"``).
        svg_file_name: Filename stored alongside the data (default ``"pattern.svg"``).
        scale:         Uniform scale factor (default 1.0 = no scaling).
        rotate:        Rotation in radians in the device frame.  Pass
                       ``-(map_bearing_rad) - rtk_yaw`` to match the APK's
                       combined transform for live devices.
        base_width_m:  Physical width of one SVG tile unit in metres
                       (2.5 m for Yuka/Luba 1; 4.0 m for Luba 2).
        base_height_m: Physical height of one SVG tile unit in metres.

    Returns:
        A fully populated :class:`SvgMessage` with ``sub_cmd=1`` (ADD) ready
        for :meth:`~pymammotion.mammotion.commands.messages.navigation.MessageNavigation.send_svg_data`.

    """
    cx, cy = area_centroid(boundary)
    return SvgMessage(
        pver=1,
        sub_cmd=1,
        total_frame=0,
        current_frame=0,
        data_hash=0,  # device assigns the real hash
        paternal_hash_a=area_hash,
        type=13,
        result=0,
        svg_message=SvgMessageData(
            x_move=round(cx, 3),
            y_move=round(cy, 3),
            scale=scale,
            rotate=rotate,
            base_width_m=base_width_m,
            base_height_m=base_height_m,
            base_width_pix=0,  # device derives from metre dimensions
            base_height_pix=0,
            name_count=len(svg_file_name),
            data_count=0,
            svg_file_name=svg_file_name,
            svg_file_data=svg_file_data,
        ),
    )


def build_svg_update(
    device_hash: int,
    area_hash: int,
    boundary: list[CommDataCouple],
    svg_file_data: str,
    *,
    svg_file_name: str = "pattern.svg",
    scale: float = 1.0,
    rotate: float = 0.0,
    base_width_m: float = _BASE_M_DEFAULT,
    base_height_m: float = _BASE_M_DEFAULT,
) -> SvgMessage:
    """Build an UPDATE :class:`SvgMessage` for an existing SVG tile.

    Use the hash the device returned in its ADD acknowledgement as
    ``device_hash``.  All other parameters follow the same conventions as
    :func:`build_svg_for_area`.

    Args:
        device_hash:   Hash assigned by the device when the tile was first added.
        area_hash:     Parent mowing area hash (``paternal_hash_a``).
        boundary:      Ordered boundary vertices used to recompute the centroid.
        svg_file_data: Updated SVG content.
        svg_file_name: Filename of the SVG pattern.
        scale:         Scale factor.
        rotate:        Rotation in radians.
        base_width_m:  Tile width in metres.
        base_height_m: Tile height in metres.

    """
    cx, cy = area_centroid(boundary)
    return SvgMessage(
        pver=1,
        sub_cmd=3,
        total_frame=0,
        current_frame=0,
        data_hash=device_hash,
        paternal_hash_a=area_hash,
        type=13,
        result=0,
        svg_message=SvgMessageData(
            x_move=round(cx, 3),
            y_move=round(cy, 3),
            scale=scale,
            rotate=rotate,
            base_width_m=base_width_m,
            base_height_m=base_height_m,
            base_width_pix=0,
            base_height_pix=0,
            name_count=len(svg_file_name),
            data_count=0,
            svg_file_name=svg_file_name,
            svg_file_data=svg_file_data,
        ),
    )


def build_svg_delete(device_hash: int, area_hash: int) -> SvgMessage:
    """Build a DELETE :class:`SvgMessage` to remove an SVG tile from the map.

    Args:
        device_hash: Hash assigned by the device when the tile was added.
        area_hash:   Parent mowing area hash (``paternal_hash_a``).

    """
    return SvgMessage(
        pver=1,
        sub_cmd=6,
        total_frame=0,
        current_frame=0,
        data_hash=device_hash,
        paternal_hash_a=area_hash,
        type=13,
        result=0,
        svg_message=SvgMessageData(),
    )


def build_svg_ack(incoming: SvgMessage) -> SvgMessage:
    """Build an ACK response for an SVG message received from the device.

    The device pushes ``toapp_svg_msg`` frames; the app must acknowledge each
    frame with ``sub_cmd=2``, echoing back ``data_hash``, ``paternal_hash_a``,
    ``total_frame``, and ``current_frame``.  No ``svg_message`` body is sent.

    Args:
        incoming: The :class:`SvgMessage` received from the device.

    """
    return SvgMessage(
        pver=1,
        sub_cmd=2,
        total_frame=incoming.total_frame,
        current_frame=incoming.current_frame,
        data_hash=incoming.data_hash,
        paternal_hash_a=incoming.paternal_hash_a,
        type=13,
        result=0,
        svg_message=SvgMessageData(),
    )


#: Maximum SVG payload bytes per frame (matches APK ``data_count`` constant).
_SVG_CHUNK_SIZE: int = 500


def chunk_svg_messages(msg: SvgMessage, chunk_size: int = _SVG_CHUNK_SIZE) -> list[SvgMessage]:
    """Split an :class:`SvgMessage` into transport-sized frames.

    The APK (``PlanMapLandFragment.sendSvgDataBean``) slices ``svg_file_data``
    into *chunk_size*-character windows and assigns ``data_count = chunk_size``
    on every frame.

    Frame-counting conventions (from the device protocol):

    - **Single frame** (``len(svg_file_data) <= chunk_size``):
      ``total_frame=0, current_frame=0`` — the APK singles-frame convention.
    - **Multi-frame**: 1-based ``current_frame`` from 1 to *N*,
      ``total_frame=N``.

    The input *msg* is never mutated.

    Args:
        msg:        The :class:`SvgMessage` to split.  Its ``svg_file_data``
                    field supplies the payload to chunk.  All other fields are
                    copied to every output frame unchanged, except for
                    ``total_frame``, ``current_frame``, ``svg_file_data``, and
                    ``data_count``.
        chunk_size: Maximum number of characters per frame (default 500).

    Returns:
        A list of one or more :class:`SvgMessage` frames ready to pass to
        :class:`~pymammotion.messaging.svg_saga.SvgSendSaga`.

    """
    data = msg.svg_message.svg_file_data

    if len(data) <= chunk_size:
        return [
            dataclasses.replace(
                msg,
                svg_message=dataclasses.replace(msg.svg_message, data_count=chunk_size),
            )
        ]

    raw_chunks = [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]
    total = len(raw_chunks)
    return [
        dataclasses.replace(
            msg,
            total_frame=total,
            current_frame=i + 1,
            svg_message=dataclasses.replace(
                msg.svg_message,
                svg_file_data=raw_chunks[i],
                data_count=chunk_size,
            ),
        )
        for i in range(total)
    ]
