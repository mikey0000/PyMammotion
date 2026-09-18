"""Every product key the cloud publishes must belong to a device family.

``tests/fixtures/product_list.json`` is a capture of
``/device-server/v1/product/product/list`` (fetch a fresh one with ``products()`` in
``examples/dev_console.py``).  An unclassified key is not a loud failure at runtime —
it falls through to defaults, which means the wrong broker for an Aliyun device and
guessed capabilities for the rest — so it is pinned here instead.

The cloud publishes most families twice: an ``a1…`` key from the Aliyun era and a
newer key with an identical model set.  Holding only one half is how a device bound
under the newer key ends up unclassified.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from pymammotion.utility import device_type as device_type_module

PRODUCTS = json.loads((pathlib.Path(__file__).parents[2] / "fixtures" / "product_list.json").read_text())

#: Product keys grouped by list, excluding the Aliyun *routing* list — membership there
#: says which broker to use, not what the device is.
TYPE_LISTS = {
    name: value
    for name, value in vars(device_type_module).items()
    if name.endswith("ProductKey") and isinstance(value, list) and name != "AliyunProductKey"
}


def _families(product_key: str) -> list[str]:
    return [name for name, keys in TYPE_LISTS.items() if product_key in keys]


@pytest.mark.parametrize(
    "product_key",
    [pytest.param(entry["product_key"], id=entry["product_key"]) for entry in PRODUCTS],
)
def test_every_published_product_key_has_a_family(product_key: str) -> None:
    models = next(e["models"] for e in PRODUCTS if e["product_key"] == product_key)
    names = sorted({model["ext_mod"] for model in models}) or ["(no models published)"]
    assert _families(product_key), (
        f"{product_key} ({', '.join(names)}) is in no product-key list, so it falls "
        f"through to defaults — add it to the list its twin uses"
    )


def test_no_product_key_claims_two_families() -> None:
    """Two families for one key makes classification order-dependent."""
    conflicts = {
        entry["product_key"]: families
        for entry in PRODUCTS
        if len(families := _families(entry["product_key"])) > 1
    }
    assert not conflicts, f"product keys claimed by more than one family: {conflicts}"


def test_keys_sharing_a_model_set_share_a_family() -> None:
    """The a1-and-newer pairs are the same product; they must classify identically."""
    by_models: dict[tuple[str, ...], list[str]] = {}
    for entry in PRODUCTS:
        if not entry["models"]:
            continue
        signature = tuple(sorted({model["int_id"] for model in entry["models"]}))
        by_models.setdefault(signature, []).append(entry["product_key"])

    split = {
        keys[0]: {key: _families(key) for key in keys}
        for keys in by_models.values()
        if len(keys) > 1 and len({tuple(_families(key)) for key in keys}) > 1
    }
    assert not split, f"keys with identical models classified differently: {split}"
