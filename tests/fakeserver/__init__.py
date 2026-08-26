"""Fake Mammotion cloud for integration testing.

Emulates the three services the library talks to, with runtime fault injection:

- ``http_api``  — the Mammotion HTTP API (oauth2/token, device list, MQTT
  credentials, mqtt_invoke, …) as an aiohttp app, plus a ``/control`` API to
  flip failure states (expired tokens, 40102 refresh rejection, deactivated
  account, invoke 401/460, …).
- ``broker``    — a minimal MQTT 3.1.1 broker that aiomqtt clients accept,
  with hooks for CONNACK auth rejection and message injection.
- ``scenario``  — the shared mutable state both servers consult, so a test
  (or a human driving Home Assistant) can trigger any auth state and watch
  the client react.

Run standalone with ``uv run python -m tests.fakeserver`` or use the pytest
fixtures in ``tests/integration/fake_cloud/conftest.py``.
"""
