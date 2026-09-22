"""RTK base-station property pushes: the Mammotion flat path must mirror the Aliyun path."""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import pytest

from pymammotion.data.model.device import RTKBaseStationDevice
from pymammotion.data.mqtt.properties import Item, Items, MammotionPropertiesMessage
from pymammotion.device.state_reducer import RTKStateReducer


def _flat(params: dict) -> MammotionPropertiesMessage:
    return MammotionPropertiesMessage.from_json(
        json.dumps(
            {"id": "1", "version": "1.0", "sys": {"ack": 1}, "method": "thing.event.property.post", "params": params}
        )
    )


def _aliyun(**items: object) -> SimpleNamespace:
    """Aliyun ThingPropertiesMessage needs ~25 envelope fields; only ``params.items`` is read here."""
    return SimpleNamespace(
        params=SimpleNamespace(
            items=Items(**{k: Item(time=0, value=v) for k, v in items.items()}),
        )
    )


def _rtk(product_key: str = "") -> RTKBaseStationDevice:
    return RTKBaseStationDevice(name="RTK-Test", product_key=product_key)


def test_flat_coordinate_sets_position() -> None:
    updated = RTKStateReducer().apply_mammotion_properties(_rtk(), _flat({"coordinate": {"lat": 0.5, "lon": 0.2}}))

    assert (updated.lat, updated.lon) == (0.5, 0.2)


def test_flat_coordinate_zero_component_is_left_unset() -> None:
    device = _rtk()
    device.lat, device.lon = 0.5, 0.2

    updated = RTKStateReducer().apply_mammotion_properties(device, _flat({"coordinate": {"lat": 0.0, "lon": 0.3}}))

    assert (updated.lat, updated.lon) == (0.5, 0.3)


def test_flat_coordinate_applies_the_a1nc68bgzzx_shift_on_both_paths() -> None:
    reducer = RTKStateReducer()
    raw = -7.0  # out of range: the 436° low latitude that product reports

    flat = reducer.apply_mammotion_properties(_rtk("a1Nc68bGZzX"), _flat({"coordinate": {"lat": raw, "lon": raw}}))
    aliyun = reducer.apply_properties(_rtk("a1Nc68bGZzX"), _aliyun(coordinate=json.dumps({"lat": raw, "lon": raw})))

    assert flat.lat == aliyun.lat == raw + math.radians(436)
    assert flat.lon == aliyun.lon == raw + math.radians(436)


def test_a_valid_longitude_beyond_90_degrees_is_left_alone() -> None:
    """The #188 regression: New Zealand at ~174.5°E, reported correctly.

    A longitude that large is perfectly valid, but the guard was pi/2 -- the
    latitude limit -- so the quirk fired on a correct value and rendered it as
    610.5°.  Every base station east of 90°E or west of 90°W was affected.
    """
    reducer = RTKStateReducer()
    nz_lon = math.radians(174.5)

    flat = reducer.apply_mammotion_properties(_rtk("a1Nc68bGZzX"), _flat({"coordinate": {"lat": -0.7, "lon": nz_lon}}))
    aliyun = reducer.apply_properties(_rtk("a1Nc68bGZzX"), _aliyun(coordinate=json.dumps({"lat": -0.7, "lon": nz_lon})))

    assert flat.lon == aliyun.lon == nz_lon
    assert flat.lat == aliyun.lat == -0.7


@pytest.mark.parametrize("degrees", [-179.9, -174.5, -120.0, -90.1, 90.1, 120.0, 174.5, 179.9])
def test_no_in_range_longitude_is_shifted(degrees: float) -> None:
    """Anything inside ±180° is a real position and must survive untouched."""
    lon = math.radians(degrees)

    updated = RTKStateReducer().apply_mammotion_properties(
        _rtk("a1Nc68bGZzX"), _flat({"coordinate": {"lat": 0.5, "lon": lon}})
    )

    assert updated.lon == lon


@pytest.mark.parametrize("degrees", [-436.0, -400.0, -380.0, -361.0])
def test_a_shifted_longitude_is_still_corrected(degrees: float) -> None:
    """#563 must keep working: 436° low, so far out that it cannot be a real position."""
    raw = math.radians(degrees)

    updated = RTKStateReducer().apply_mammotion_properties(
        _rtk("a1Nc68bGZzX"), _flat({"coordinate": {"lat": 0.5, "lon": raw}})
    )

    assert updated.lon == raw + math.radians(436)
    assert abs(updated.lon) <= math.pi


def test_the_two_axes_keep_their_own_limits() -> None:
    """A latitude of 2.0 rad (115°) cannot be real, while that longitude can."""
    reducer = RTKStateReducer()

    updated = reducer.apply_mammotion_properties(_rtk("a1Nc68bGZzX"), _flat({"coordinate": {"lat": 2.0, "lon": 2.0}}))

    assert updated.lat == 2.0 + math.radians(436)
    assert updated.lon == 2.0


def test_another_product_key_is_never_shifted() -> None:
    """The quirk is one product key's firmware, not a general correction."""
    updated = RTKStateReducer().apply_mammotion_properties(
        _rtk("a1Another"), _flat({"coordinate": {"lat": -7.0, "lon": -7.0}})
    )

    assert (updated.lat, updated.lon) == (-7.0, -7.0)


def test_flat_network_info_matches_aliyun() -> None:
    reducer = RTKStateReducer()
    net = {"wifi_rssi": -61, "wifi_sta_mac": "aa:bb:cc:dd:ee:01", "bt_mac": "aa:bb:cc:dd:ee:02"}

    flat = reducer.apply_mammotion_properties(_rtk(), _flat({"networkInfo": net}))
    aliyun = reducer.apply_properties(_rtk(), _aliyun(networkInfo=json.dumps(net)))

    for device in (flat, aliyun):
        assert (device.wifi_rssi, device.wifi_mac, device.bt_mac) == (-61, net["wifi_sta_mac"], net["bt_mac"])


def test_flat_version_info_fills_module_firmwares_and_copies_before_writing() -> None:
    reducer = RTKStateReducer()
    current = _rtk()
    info = {
        "devVer": "2.1.0.9",
        "whole": 1,
        "fwInfo": [
            {"t": "101", "c": "mc", "v": "1.1"},
            {"t": "102", "c": "rtk", "v": "2.2"},
            {"t": "103", "c": "lora", "v": "3.3"},
            {"t": "999", "c": "x", "v": ""},
        ],
    }

    updated = reducer.apply_mammotion_properties(current, _flat({"deviceVersionInfo": info, "loraGeneralConfig": "L1"}))

    assert updated.device_version == "2.1.0.9"
    assert updated.device_firmwares.device_version == "2.1.0.9"
    assert (
        updated.device_firmwares.main_controller,
        updated.device_firmwares.rtk_version,
        updated.device_firmwares.lora_version,
    ) == ("1.1", "2.2", "3.3")
    assert updated.lora_version == "L1"
    # The previous snapshot's nested model must be untouched (identity-based diff).
    assert current.device_firmwares.main_controller == ""


def test_aliyun_version_info_still_fills_module_firmwares() -> None:
    info = {"devVer": "2.1.0.9", "fwInfo": [{"t": "102", "v": "2.2"}]}

    updated = RTKStateReducer().apply_properties(_rtk(), _aliyun(deviceVersionInfo=json.dumps(info)))

    assert updated.device_version == "2.1.0.9"
    assert updated.device_firmwares.rtk_version == "2.2"


def test_flat_ota_progress_drives_update_check_and_installs_version() -> None:
    reducer = RTKStateReducer()

    running = reducer.apply_mammotion_properties(_rtk(), _flat({"otaProgress": {"progress": 40, "result": 2}}))
    assert running.update_check.isupgrading is True
    assert running.update_check.progress == 40
    assert running.has_live_ota_push()

    done = reducer.apply_mammotion_properties(
        running, _flat({"otaProgress": {"progress": 99, "result": 0, "version": "2.2.0.1"}})
    )
    assert done.update_check.isupgrading is False
    assert done.update_check.progress == 100
    assert done.device_version == "2.2.0.1"


def test_aliyun_ota_progress_uses_the_same_result_codes() -> None:
    ota = {"result": 1, "otaId": "o1", "progress": 55, "message": "", "version": "2.2.0.1", "properties": ""}

    failed = RTKStateReducer().apply_properties(_rtk(), _aliyun(otaProgress=ota))

    assert failed.update_check.isupgrading is False
    assert failed.update_check.progress == 55
    assert failed.device_version == ""


async def test_the_http_property_poll_applies_the_quirk_too() -> None:
    """The second way a coordinate reaches an RTK skipped the correction entirely.

    ``MammotionClient.fetch_rtk_properties`` wrote lat/lon straight onto the
    device, so a1Nc68bGZzX stations polled over HTTP reported a latitude 436°
    out — the reporter's -474.669° (Mammotion-HA / PyMammotion #188) — while
    the MQTT push path corrected the same payload.
    """
    from unittest.mock import AsyncMock, MagicMock

    from pymammotion.client import MammotionClient

    device = RTKBaseStationDevice(name="RTKBAU242721575", product_key="a1Nc68bGZzX")
    device.iot_id = "iot-1"
    handle = MagicMock()
    handle.snapshot.raw = device
    handle.state_machine.apply.return_value = (MagicMock(), None)
    handle.emit_state_changed = AsyncMock()

    client = MammotionClient.__new__(MammotionClient)
    client._device_registry = MagicMock()  # noqa: SLF001
    client._device_registry.get_by_name.return_value = handle  # noqa: SLF001

    gateway = MagicMock()
    gateway.get_device_properties = AsyncMock(
        return_value=MagicMock(
            code=200,
            data=MagicMock(
                otaProgress=None,
                networkInfo=None,
                deviceVersion=None,
                coordinate=MagicMock(value=json.dumps({"lat": -8.28453707294943, "lon": 3.059871264118208})),
            ),
        )
    )
    type(client).cloud_gateway = property(lambda _self: gateway)
    try:
        await client.fetch_rtk_properties("RTKBAU242721575")
    finally:
        del type(client).cloud_gateway

    applied = handle.state_machine.apply.call_args.args[0]
    assert applied.lat == pytest.approx(math.radians(-38.669))
    assert applied.lon == pytest.approx(3.059871264118208)
