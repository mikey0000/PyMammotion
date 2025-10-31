import asyncio
import json
import logging
import os
import random
import time
from typing import Optional

from pymammotion.data.model.device import MowingDevice
from pymammotion.data.mower_state_manager import MowerStateManager
from pymammotion.mammotion.devices.mammotion_cloud import MammotionCloud
from pymammotion.aliyun.cloud_gateway import CloudIOTGateway
from pymammotion.http.http import MammotionHTTP
from pymammotion.mqtt.aliyun_mqtt import AliyunMQTT, logger
from pymammotion.mammotion.devices import MammotionBaseCloudDevice, Mammotion

_LOGGER = logging.getLogger(__name__)

async def exponential_backoff(
    func,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 10.0,
    jitter: bool = True
) -> Optional[any]:
    """Execute function with exponential backoff retry logic."""
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            return await func()
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            if "429" in str(e) or "Too Many Requests" in str(e):
                sleep_time = min(delay * (2 ** attempt), max_delay)
                if jitter:
                    sleep_time = random.uniform(0.5 * sleep_time, sleep_time)
                _LOGGER.warning(f"Rate limited, retrying in {sleep_time:.1f}s (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(sleep_time)
            else:
                raise


async def run() -> CloudIOTGateway:
    EMAIL = os.environ.get('EMAIL')
    PASSWORD = os.environ.get('PASSWORD')
    mammotion_http = MammotionHTTP()
    cloud_client = CloudIOTGateway(mammotion_http)
    try:
        # Add initial delay to avoid immediate rate limiting
        await asyncio.sleep(1.0)
        
        # Wrap login with retry logic
        await exponential_backoff(
            lambda: mammotion_http.login(EMAIL, PASSWORD),
            max_retries=3,
            initial_delay=5.0
        )
        
        country_code = mammotion_http.login_info.userInformation.domainAbbreviation
        _LOGGER.debug("CountryCode: " + country_code)
        _LOGGER.debug("AuthCode: " + mammotion_http.login_info.authorization_code)
        
        # Execute API calls sequentially with delays and retries
        await exponential_backoff(
            lambda: cloud_client.get_region(country_code),
            max_retries=3,
            initial_delay=5.0
        )
        await asyncio.sleep(0.5)  # Add delay between calls
        
        await exponential_backoff(
            lambda: cloud_client.connect(),
            max_retries=3,
            initial_delay=5.0
        )
        await asyncio.sleep(0.5)
        
        await exponential_backoff(
            lambda: cloud_client.login_by_oauth(country_code),
            max_retries=3,
            initial_delay=5.0
        )
        
        # Remove unused responses check since we're now doing sequential calls

        # Execute remaining calls with retry logic and delays
        await exponential_backoff(
            lambda: cloud_client.aep_handle(),
            max_retries=3,
            initial_delay=5.0
        )
        await asyncio.sleep(0.5)
        
        await exponential_backoff(
            lambda: cloud_client.session_by_auth_code(),
            max_retries=3,
            initial_delay=5.0
        )
        await asyncio.sleep(0.5)
        
        await exponential_backoff(
            lambda: mammotion_http.get_all_error_codes(),
            max_retries=3,
            initial_delay=5.0
        )

        # Log API responses for debugging
        _LOGGER.debug(f"region_response: {cloud_client.region_response}")
        _LOGGER.debug(f"aep_response: {cloud_client.aep_response}")
        _LOGGER.debug(f"session_by_authcode_response: {cloud_client.session_by_authcode_response}")

        binding_result = await cloud_client.list_binding_by_account()
        _LOGGER.debug(f"list_binding_by_account result: {binding_result}")

        # Verify required responses
        if not all([
            hasattr(cloud_client, 'region_response') and cloud_client.region_response,
            hasattr(cloud_client, 'aep_response') and cloud_client.aep_response,
            hasattr(cloud_client, 'session_by_authcode_response') and cloud_client.session_by_authcode_response,
            hasattr(cloud_client, 'devices_by_account_response') and cloud_client.devices_by_account_response
        ]):
            raise RuntimeError("Missing required API responses")
    except Exception as e:
        _LOGGER.error(f"Test failed: {str(e)}")
        raise

    # Validate all required response data exists before creating MQTT client
    required_fields = [
        ('region_response', 'data.regionId'),
        ('aep_response', 'data.productKey'),
        ('aep_response', 'data.deviceName'),
        ('aep_response', 'data.deviceSecret'),
        ('session_by_authcode_response', 'data.iotToken')
    ]
    
    missing_fields = []
    for field, attr in required_fields:
        try:
            obj = getattr(cloud_client, field)
            parts = attr.split('.')
            for part in parts:
                obj = getattr(obj, part)
        except Exception:
            missing_fields.append(f"{field}.{attr}")
    
    if missing_fields:
        raise ValueError(f"Missing required fields in cloud client responses: {', '.join(missing_fields)}")

    _mammotion_mqtt = MammotionCloud(AliyunMQTT(
        region_id=cloud_client.region_response.data.regionId,
        product_key=cloud_client.aep_response.data.productKey,
        device_name=cloud_client.aep_response.data.deviceName,
        device_secret=cloud_client.aep_response.data.deviceSecret,
        iot_token=cloud_client.session_by_authcode_response.data.iotToken,
        client_id=cloud_client.client_id,
        cloud_client=cloud_client
    ), cloud_client=cloud_client)

    try:
        _mammotion_mqtt.connect_async()
    except Exception as e:
        _LOGGER.error(f"MQTT connection failed: {str(e)}")
        raise

    _devices_list = []
    for device in cloud_client.devices_by_account_response.data.data:
        if device.device_name.startswith(("Luba-")):
            dev = MammotionBaseCloudDevice(
                mqtt=_mammotion_mqtt,
                cloud_device=device,
                state_manager=MowerStateManager(MowingDevice())
            )
            _devices_list.append(dev)
    # Wrap device commands in error handling
    try:
        await exponential_backoff(
            lambda: _devices_list[0].queue_command("send_todev_ble_sync", sync_type=3),
            max_retries=3,
            initial_delay=5.0
        )
        await asyncio.sleep(1)
        
        await exponential_backoff(
            lambda: _devices_list[0].queue_command("get_report_cfg_stop"),
            max_retries=3,
            initial_delay=5.0
        )
        await asyncio.sleep(1)
        
        await exponential_backoff(
            lambda: _devices_list[0].queue_command("get_report_cfg"),
            max_retries=3,
            initial_delay=5.0
        )
        await asyncio.sleep(1)
        
        await exponential_backoff(
            lambda: _devices_list[0].queue_command("read_and_set_rtk_paring_code", op=1),
            max_retries=3,
            initial_delay=5.0
        )
    except json.JSONDecodeError as e:
        _LOGGER.error(f"Invalid JSON response: {str(e)}")
        raise
    except Exception as e:
        _LOGGER.error(f"Device command failed: {str(e)}")
        raise
    # res = cloud_client.list_binding_by_dev(_devices_list[0].iot_id)
    # print(res)
    # Wrap remaining commands in error handling
    try:
        await asyncio.sleep(1)
        await exponential_backoff(
            lambda: _devices_list[0].queue_command("send_todev_ble_sync", sync_type=3),
            max_retries=3,
            initial_delay=5.0
        )
        await exponential_backoff(
            lambda: _devices_list[0].queue_command("read_and_set_rtk_paring_code", op=1),
            max_retries=3,
            initial_delay=5.0
        )
        await asyncio.sleep(1)
        await exponential_backoff(
            lambda: _devices_list[0].queue_command("read_and_set_rtk_paring_code", op=1),
            max_retries=3,
            initial_delay=5.0
        )
        await asyncio.sleep(1)
        await exponential_backoff(
            lambda: _devices_list[0].queue_command("send_todev_ble_sync", sync_type=3),
            max_retries=3,
            initial_delay=5.0
        )
        await exponential_backoff(
            lambda: _devices_list[0].queue_command("read_and_set_rtk_paring_code", op=1),
            max_retries=3,
            initial_delay=5.0
        )
        await asyncio.sleep(1)
        await exponential_backoff(
            lambda: _devices_list[0].queue_command("read_and_set_rtk_paring_code", op=1),
            max_retries=3,
            initial_delay=5.0
        )
    except json.JSONDecodeError as e:
        _LOGGER.error(f"Invalid JSON response in device command: {str(e)}")
        raise
    except Exception as e:
        _LOGGER.error(f"Device command execution failed: {str(e)}")
        raise


async def sync_status_and_map(cloud_device: MammotionBaseCloudDevice):
    await asyncio.sleep(1)
    await cloud_device.start_sync(0)
    await asyncio.sleep(2)
    # await cloud_device.start_map_sync()

    while (True):
        print(cloud_device.mower)
        await asyncio.sleep(5)


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    logger.getChild("paho").setLevel(logging.WARNING)
    event_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(event_loop)
    cloud_client: CloudIOTGateway = event_loop.run_until_complete(run())



    event_loop.run_forever()
