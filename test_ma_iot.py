"""End-to-end smoke test for the MA-IoT proxy client.

Reads credentials from ``../ha-automations/.env`` (falls back to a sibling
``.env``), logs in via the encrypted OAuth flow, then exercises the new
MA-IoT endpoints: region resolution, device list, MQTT JWT, and properties
get.  Does NOT hit service_invoke or set_properties to avoid accidentally
moving the real mower.

Run from the PyMammotion repo root:
    python test_ma_iot.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("pymammotion.http.ma_iot").setLevel(logging.DEBUG)

from pymammotion.http.http import MammotionHTTP
from pymammotion.http.ma_iot import MammotionMaIoT


def _load_env() -> tuple[str, str]:
    for candidate in (
        Path(__file__).parent / ".env",
        Path(__file__).parent.parent / "ha-automations" / ".env",
    ):
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())

    account = os.environ.get("MAMMOTION_EMAIL")
    password = os.environ.get("MAMMOTION_PASSWORD")
    if not account or not password:
        sys.exit("Set MAMMOTION_EMAIL / MAMMOTION_PASSWORD in an .env file or the environment")
    return account, password


async def main() -> None:
    account, password = _load_env()

    http = MammotionHTTP()
    login_response = await http.login_v2(account, password)
    if login_response.code != 0 or http.login_info is None:
        sys.exit(f"login_v2 failed: code={login_response.code} msg={login_response.msg}")

    user_info = http.login_info.userInformation
    print(f"✓ logged in as {user_info.userAccount} (userId={user_info.userId})")
    print(f"  JWT iot claim  : {http.jwt_info.iot or '(missing)'}")
    print(f"  JWT robot claim: {http.jwt_info.robot or '(missing)'}")

    ma_iot = MammotionMaIoT(http)
    base = await ma_iot.resolve_base_url()
    print(f"✓ MA-IoT base URL from JWT: {base}")

    # Also try the explicit region lookup endpoint to compare
    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api-iot-region.mammotion.com/v1/ma-user/region",
            json={"accessToken": http.login_info.access_token},
            headers={
                "User-Agent": "okhttp/4.9.3",
                "App-Version": "2.2.4.13",
                "Authorization": f"Bearer {http.login_info.access_token}",
            },
        ) as resp:
            print(f"  explicit region lookup: status={resp.status} body={await resp.text()}")

    devices = await ma_iot.list_devices()
    print(
        f"✓ devices: total={devices.total} pages={devices.pages} "
        f"size={devices.size} current={devices.current}"
    )
    for record in devices.records:
        print(
            f"    • {record.nick_name or record.device_name} "
            f"iotId={record.iot_id} productKey={record.product_key} "
            f"status={record.status} owned={record.owned}"
        )

    if not devices.records:
        print("no devices bound to this account; skipping MQTT + properties checks")
        return

    first = devices.records[0]

    client_id = f"pymammotion-{user_info.userId}-smoketest"
    jwt = await ma_iot.get_mqtt_credentials(
        client_id=client_id, username=user_info.email or user_info.userAccount
    )
    print(
        "✓ MQTT creds fetched: host=%s clientId=%s username=%s jwt_len=%d"
        % (jwt.host, jwt.client_id, jwt.username, len(jwt.jwt))
    )

    try:
        props = await ma_iot.get_properties(
            iot_id=first.iot_id, product_key=first.product_key, device_name=first.device_name
        )
        print(f"✓ properties.get returned {len(props)} entries for {first.device_name}")
        for prop in props[:5]:
            print(f"    - {prop.identifier} = {prop.value!r}")
    except Exception as err:  # noqa: BLE001
        print(f"✗ properties.get failed (may be expected if device offline): {err}")


if __name__ == "__main__":
    asyncio.run(main())
