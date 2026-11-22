"""CloudIOTGateway.get_region: the first step of the Aliyun chain."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from aiohttp import ConnectionTimeoutError
import orjson
import pytest

from pymammotion.aliyun import cloud_gateway
from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.aliyun.exceptions import CloudSetupError
from pymammotion.aliyun.model.regions_response import RegionResponse
from pymammotion.aliyun.regions import region_mappings
from pymammotion.http.http import MammotionHTTP
from tests.unit.aliyun._helpers import make_region


def _gateway(region: RegionResponse | None = None) -> CloudIOTGateway:
    http = MagicMock(spec=MammotionHTTP, account="user@example.com")
    return CloudIOTGateway(mammotion_http=http, region_response=region)


async def test_a_region_lookup_timeout_falls_back_to_the_country_region() -> None:
    """The fallback is stored, so the next chain step reads a region rather than None."""
    gateway = _gateway()
    client = MagicMock()
    client.async_do_request = AsyncMock(side_effect=ConnectionTimeoutError())

    with patch.object(cloud_gateway, "Client", return_value=client):
        region = await gateway.get_region("GB")

    assert gateway.region_response is region
    assert region.data.regionId == region_mappings["GB"]
    assert region.data.apiGatewayEndpoint == f"{region_mappings['GB']}.api-iot.aliyuncs.com"


async def test_a_known_region_is_not_looked_up_again() -> None:
    gateway = _gateway(make_region())
    client = MagicMock()
    client.async_do_request = AsyncMock()

    with patch.object(cloud_gateway, "Client", return_value=client):
        assert await gateway.get_region("GB") is gateway.region_response

    client.async_do_request.assert_not_awaited()


async def test_a_refused_region_lookup_is_a_setup_error() -> None:
    gateway = _gateway()
    response = MagicMock(body=orjson.dumps({"code": 2064, "message": "refused"}))
    client = MagicMock()
    client.async_do_request = AsyncMock(return_value=response)

    with patch.object(cloud_gateway, "Client", return_value=client), pytest.raises(CloudSetupError):
        await gateway.get_region("GB")

    assert gateway.region_response is None
