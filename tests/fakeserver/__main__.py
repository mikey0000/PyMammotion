"""Standalone fake Mammotion cloud.

Run with::

    uv run python -m tests.fakeserver [--http-port 8787] [--account EMAIL] [--password PW]

Then point pymammotion (e.g. inside a Home Assistant dev install) at it via
environment variables — pymammotion.const reads these at import time::

    MAMMOTION_DOMAIN=http://<host>:8787
    MAMMOTION_API_DOMAIN=http://<host>:8787

and log the integration in with the printed account/password.  Drive failure
states at runtime with the /control API, e.g.::

    curl -X POST http://127.0.0.1:8787/control/revoke-access-tokens     # invoke 401s → reactive refresh
    curl -X POST http://127.0.0.1:8787/control/revoke-refresh-token     # 40102 → account terminal, kill switch
    curl -X POST http://127.0.0.1:8787/control/deactivate-account       # "activity abnormal ... deactivated"
    curl -X POST http://127.0.0.1:8787/control/expire-session           # bearers AND refresh dead at once
    curl -X POST -d '{"mode":"body_460"}' http://127.0.0.1:8787/control/set-invoke-mode
    curl -X POST -d '{"rc":5}'            http://127.0.0.1:8787/control/set-connack-rc
    curl -X POST -d '{"code":2043}'       http://127.0.0.1:8787/control/set-bind-reply
    curl -X POST http://127.0.0.1:8787/control/restore-login            # heal auth rejections
    curl -X POST http://127.0.0.1:8787/control/reset                    # everything healthy again
    curl http://127.0.0.1:8787/control/state                            # counters + current faults
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from .cloud import FakeMammotionCloud
from .scenario import Scenario


async def main() -> None:
    parser = argparse.ArgumentParser(description="Fake Mammotion cloud")
    parser.add_argument("--http-port", type=int, default=8787)
    parser.add_argument("--account", default="test@example.com")
    parser.add_argument("--password", default="test-password")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    scenario = Scenario(account=args.account, password=args.password)
    cloud = FakeMammotionCloud(scenario, http_port=args.http_port)
    await cloud.start()

    print()
    print("Fake Mammotion cloud running")
    print(f"  HTTP API + control:  {cloud.base_url}")
    print(f"  Mammotion MQTT:      127.0.0.1:{cloud.mammotion_broker.port} (plaintext)")
    print(f"  Aliyun MQTT:         127.0.0.1:{cloud.aliyun_broker.port} (plaintext — patch get_ssl_context)")
    print(f"  Account:             {scenario.account} / {scenario.password}")
    print(f"  Mower:               {scenario.device.device_name} (iotId {scenario.device.iot_id})")
    print()
    print("Point pymammotion at it with:")
    print(f"  MAMMOTION_DOMAIN={cloud.base_url}")
    print(f"  MAMMOTION_API_DOMAIN={cloud.base_url}")
    print()
    print(f"Fault injection: see `curl {cloud.base_url}/control/state` and module docstring.")
    print("Ctrl+C to stop.")
    try:
        await asyncio.Event().wait()
    finally:
        await cloud.stop()


if __name__ == "__main__":
    with __import__("contextlib").suppress(KeyboardInterrupt):
        asyncio.run(main())
