"""pymammotion — Python library for Mammotion robot mowers (Luba, Yuka, RTK).

The public API entry point is ``MammotionClient``; import it directly:

    from pymammotion.client import MammotionClient

Lower-level transports live under ``pymammotion.transport``.
"""

import contextlib
import logging

# betterproto2's first SerializeToString() probes pydantic via
# pydantic.dataclasses.is_pydantic_dataclass; pydantic resolves .dataclasses through a
# lazy module __getattr__ -> import_module, which Home Assistant flags as a blocking
# call inside the event loop (Mammotion-HA #779).  Import it eagerly at package import
# time (already off the loop) so the first serialization is import-free.
with contextlib.suppress(ImportError):
    import pydantic.dataclasses  # noqa: F401

from pymammotion.bluetooth.ble import MammotionBLE
from pymammotion.http.http import MammotionHTTP

__version__ = "0.0.5"

logger = logging.getLogger(__name__)

__all__ = ["MammotionBLE", "MammotionHTTP", "logger"]
