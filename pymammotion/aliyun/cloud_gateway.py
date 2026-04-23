"""Module for interacting with Aliyun Cloud IoT Gateway."""

import base64
import hashlib
import hmac
import itertools
import json
from json.decoder import JSONDecodeError
from logging import getLogger
import random
import string
import time
from typing import Any
import uuid

from aiohttp import ClientSession, ConnectionTimeoutError
from alibabacloud_iot_api_gateway.models import CommonParams, Config, IoTApiRequest
from alibabacloud_tea_util.client import Client as UtilClient
from alibabacloud_tea_util.models import RuntimeOptions
from mashumaro import MissingField

from pymammotion.aliyun.client import Client
from pymammotion.aliyun.exceptions import (
    AuthRefreshException,
    DeviceOfflineException,
    FailedRequestException,
    GatewayTimeoutException,
    LoginException,
    TooManyRequestsException,
)
from pymammotion.aliyun.model.aep_response import AepResponse
from pymammotion.aliyun.model.connect_response import ConnectResponse
from pymammotion.aliyun.model.dev_by_account_response import ListingDevAccountResponse, ShareNoticeListResponse
from pymammotion.aliyun.model.login_by_oauth_response import LoginByOAuthResponse
from pymammotion.aliyun.model.regions_response import RegionResponse
from pymammotion.aliyun.model.session_by_authcode_response import SessionByAuthCodeResponse
from pymammotion.aliyun.model.thing_response import ThingPropertiesResponse
from pymammotion.aliyun.regions import region_mappings
from pymammotion.const import ALIYUN_DOMAIN, APP_KEY, APP_SECRET, APP_VERSION
from pymammotion.http.http import MammotionHTTP
from pymammotion.http.model.http import (
    DeviceInfo,
    DeviceRecords,
    JWTTokenInfo,
    LoginResponseData,
    MQTTConnection,
    Response,
)
from pymammotion.http.model.response_factory import response_factory
from pymammotion.transport.base import ReLoginRequiredError, SessionExpiredError, TransportType
from pymammotion.utility.datatype_converter import DatatypeConverter

logger = getLogger(__name__)

MOVE_HEADERS = (
    "x-ca-signature",
    "x-ca-signature-headers",
    "accept",
    "content-md5",
    "content-type",
    "date",
    "host",
    "token",
    "user-agent",
)


class CloudIOTGateway:
    """Class for interacting with Aliyun Cloud IoT Gateway."""

    _client_id = ""
    _device_sn = ""
    _utdid = ""

    converter = DatatypeConverter()

    def __init__(
        self,
        mammotion_http: MammotionHTTP,
        connect_response: ConnectResponse | None = None,
        login_by_oauth_response: LoginByOAuthResponse | None = None,
        aep_response: AepResponse | None = None,
        session_by_authcode_response: SessionByAuthCodeResponse | None = None,
        region_response: RegionResponse | None = None,
        dev_by_account: ListingDevAccountResponse | None = None,
    ) -> None:
        """Initialize the CloudIOTGateway."""
        self.mammotion_http: MammotionHTTP = mammotion_http
        self._app_key = APP_KEY
        self._app_secret = APP_SECRET
        self.domain = ALIYUN_DOMAIN
        self.message_delay = 1
        # Rate-limiting circuit breaker for send_cloud_command.
        # When a 429 is received, _rate_limited_until is set to a future
        # monotonic timestamp.  All send attempts before that time raise
        # TooManyRequestsException immediately without hitting the network.
        # _rate_limit_backoff doubles on each successive 429 (60 s → 120 s → …).
        self._rate_limited_until: float = 0.0
        self._rate_limit_backoff: float = 60.0
        self._client_id = self.generate_hardware_string(8)  # 8 characters
        self._device_sn = self.generate_hardware_string(32)  # 32 characters
        self._utdid = self.generate_hardware_string(32)  # 32 characters
        self._connect_response = connect_response
        self._login_by_oauth_response = login_by_oauth_response
        self._aep_response = aep_response
        self._session_by_authcode_response = session_by_authcode_response
        self._region_response = region_response
        self._devices_by_account_response = dev_by_account
        self._iot_token_issued_at = int(time.time())
        if self._session_by_authcode_response:
            self._iot_token_issued_at = (
                self._session_by_authcode_response.token_issued_at
                if self._session_by_authcode_response.token_issued_at is not None
                else int(time.time())
            )

    @staticmethod
    def generate_random_string(length: int) -> str:
        """Generate a random string of specified length."""
        characters = string.ascii_letters + string.digits
        return "".join(random.choice(characters) for _ in range(length))

    @staticmethod
    def generate_hardware_string(length: int) -> str:
        """Generate hardware string that is consistent per device."""
        hashed_uuid = hashlib.sha1(f"{uuid.getnode()}".encode()).hexdigest()
        return "".join(itertools.islice(itertools.cycle(hashed_uuid), length))

    @staticmethod
    def parse_json_response(response_body_str: str) -> dict:
        """Parse a JSON response string into a dictionary, returning an error code dict on failure."""
        try:
            return json.loads(response_body_str) if response_body_str is not None else {}
        except JSONDecodeError:
            logger.error("Couldn't decode message %s", response_body_str)
            return {"code": 22000}

    def sign(self, data: dict) -> str:
        """Generate signature for the given data."""
        keys = ["appKey", "clientId", "deviceSn", "timestamp"]
        concatenated_str = ""
        for key in keys:
            concatenated_str += f"{key}{data.get(key, '')}"

        logger.debug("sign(), toSignStr = %s", concatenated_str)

        return hmac.new(
            self._app_secret.encode("utf-8"),
            concatenated_str.encode("utf-8"),
            hashlib.sha1,
        ).hexdigest()

    async def get_region(self, country_code: str) -> RegionResponse:
        """Get the region based on country code and auth code."""
        auth_code = self.mammotion_http.login_info.authorization_code

        if self._region_response is not None:
            return self._region_response

        config = Config(app_key=self._app_key, app_secret=self._app_secret, domain=self.domain)
        client = Client(config)

        # build request
        request = CommonParams(api_ver="1.0.2", language="en-US")
        body = IoTApiRequest(
            id=str(uuid.uuid4()),
            params={
                "authCode": auth_code,
                "type": "THIRD_AUTHCODE",
                "countryCode": country_code,
            },
            request=request,
            version="1.0",
        )

        # send request
        try:
            response = await client.async_do_request(
                "/living/account/region/get", "https", "POST", {}, body, RuntimeOptions()
            )
            logger.debug(response.status_message)
            logger.debug(response.headers)
            logger.debug(response.status_code)
            logger.debug(response.body)
        except ConnectionTimeoutError:
            body = {"data": {}, "code": 200}

            region = region_mappings.get(country_code, "US")
            body["data"]["shortRegionId"] = region
            body["data"]["regionEnglishName"] = ""
            body["data"]["oaApiGatewayEndpoint"] = f"living-account.{region}.aliyuncs.com"
            body["data"]["regionId"] = region
            body["data"]["mqttEndpoint"] = f"public.itls.{region}.aliyuncs.com:1883"
            body["data"]["pushChannelEndpoint"] = f"living-accs.{region}.aliyuncs.com"
            body["data"]["apiGatewayEndpoint"] = f"{region}.api-iot.aliyuncs.com"

            RegionResponse.from_dict(body)
            return body
        # Decode the response body
        response_body_str = response.body.decode("utf-8")
        # Load the JSON string into a dictionary
        response_body_dict = self.parse_json_response(response_body_str)

        if int(response_body_dict.get("code")) != 200:
            raise Exception("Error in getting regions: " + response_body_dict)

        self._region_response = RegionResponse.from_dict(response_body_dict)
        logger.debug("Endpoint: %s", self._region_response.data.mqttEndpoint)

        return response.body

    async def aep_handle(self) -> AepResponse:
        """Handle AEP authentication."""
        aep_domain = self.domain

        if self._region_response.data.apiGatewayEndpoint is not None:
            aep_domain = self._region_response.data.apiGatewayEndpoint

        config = Config(app_key=self._app_key, app_secret=self._app_secret, domain=aep_domain)
        client = Client(config)

        request = CommonParams(api_ver="1.0.0", language="en-US")
        logger.debug("client id %s", self._client_id)
        time_now = time.time()
        data_to_sign = {
            "appKey": self._app_key,
            "clientId": self._client_id,  # needs to be unique to device
            "deviceSn": self._device_sn,  # same here
            "timestamp": str(time_now),
        }

        body = IoTApiRequest(
            id=str(uuid.uuid4()),
            params={
                "authInfo": {
                    "clientId": self._client_id,
                    "sign": self.sign(data_to_sign),
                    "deviceSn": self._device_sn,
                    "timestamp": str(time_now),
                }
            },
            request=request,
            version="1.0",
        )

        # send request
        response = await client.async_do_request("/app/aepauth/handle", "https", "POST", None, body, RuntimeOptions())
        logger.debug(response.status_message)
        logger.debug(response.headers)
        logger.debug(response.status_code)
        logger.debug(response.body)

        response_body_str = response.body.decode("utf-8")

        response_body_dict = self.parse_json_response(response_body_str)

        if int(response_body_dict.get("code")) != 200:
            raise Exception("Error in getting mqtt credentials: " + response_body_dict["msg"])

        self._aep_response = AepResponse.from_dict(response_body_dict)

        logger.debug(response_body_dict)

        return self._aep_response

    async def connect(self) -> ConnectResponse:
        """Connect to the Aliyun Cloud IoT Gateway."""
        region_url = "sdk.openaccount.aliyun.com"
        time_now = time.time()
        async with ClientSession() as session:
            headers = {
                "host": region_url,
                "date": UtilClient.get_date_utcstring(),
                "x-ca-nonce": UtilClient.get_nonce(),
                "x-ca-key": self._app_key,
                "x-ca-signaturemethod": "HmacSHA256",
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded",
                "user-agent": UtilClient.get_user_agent(None),
            }

            _bodyParam = {
                "context": {
                    "sdkVersion": "3.4.2",
                    "platformName": "android",
                    "netType": "wifi",
                    "appKey": self._app_key,
                    "yunOSId": "",
                    "appVersion": APP_VERSION,
                    "utDid": self._utdid,
                    "appAuthToken": self._utdid,  # ???
                    "securityToken": self._utdid,  # ???
                },
                "config": {"version": 0, "lastModify": 0},
                "device": {
                    "model": "sdk_gphone_x86_arm",
                    "brand": "goldfish_x86",
                    "platformVersion": "30",
                },
            }

            # Get sign header
            dic = headers.copy()
            for key in MOVE_HEADERS:
                dic.pop(key, None)

            keys = sorted(dic.keys())
            sign_headers = ",".join(keys)
            header = "".join(f"{k}:{dic[k]}\n" for k in keys).strip()

            headers["x-ca-signature-headers"] = sign_headers
            string_to_sign = "POST\n{}\n\n{}\n{}\n{}\n/api/prd/connect.json?request={}".format(
                headers["accept"],
                headers["content-type"],
                headers["date"],
                header,
                json.dumps(_bodyParam, separators=(",", ":")),
            )

            hash_val = hmac.new(
                self._app_secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                hashlib.sha256,
            ).digest()
            signature = base64.b64encode(hash_val).decode("utf-8")
            headers["x-ca-signature"] = signature

            async with session.post(
                f"https://{region_url}/api/prd/connect.json",
                headers=headers,
                params={"request": json.dumps(_bodyParam, separators=(",", ":"))},
            ) as resp:
                data = await resp.json()
                logger.debug(data)
                if resp.status == 200:
                    self._connect_response = ConnectResponse.from_dict(data)
                    return self._connect_response
                raise LoginException(data)

    async def login_by_oauth(self, country_code: str):
        """Login by OAuth."""
        auth_code = self.mammotion_http.login_info.authorization_code
        region_url = self._region_response.data.oaApiGatewayEndpoint

        async with ClientSession() as session:
            headers = {
                "host": region_url,
                "date": UtilClient.get_date_utcstring(),
                "x-ca-nonce": UtilClient.get_nonce(),
                "x-ca-key": self._app_key,
                "x-ca-signaturemethod": "HmacSHA256",
                "accept": "application/json",
                "content-type": "application/x-www-form-urlencoded; charset=utf-8",
                "user-agent": UtilClient.get_user_agent(None),
                "vid": self._connect_response.data.vid,
            }

            _bodyParam = {
                "country": country_code,
                "authCode": auth_code,
                "oauthPlateform": 23,
                "oauthAppKey": self._app_key,
                "riskControlInfo": {
                    "appID": "com.agilexrobotics",
                    "appAuthToken": "",
                    "signType": "RSA",
                    "sdkVersion": "3.4.2",
                    "utdid": self._utdid,
                    "umidToken": self._utdid,
                    "deviceId": self._connect_response.data.data.device.data.deviceId,
                    "USE_OA_PWD_ENCRYPT": "true",
                    "USE_H5_NC": "true",
                },
            }

            # Get sign header
            dic = headers.copy()
            for key in MOVE_HEADERS:
                dic.pop(key, None)

            keys = sorted(dic.keys())
            sign_headers = ",".join(keys)
            header = "".join(f"{k}:{dic[k]}\n" for k in keys).strip()

            headers["x-ca-signature-headers"] = sign_headers
            string_to_sign = "POST\n{}\n\n{}\n{}\n{}\n/api/prd/loginbyoauth.json?{}".format(
                headers["accept"],
                headers["content-type"],
                headers["date"],
                header,
                f"loginByOauthRequest={json.dumps(_bodyParam, separators=(',', ':'))}",
            )

            hash_val = hmac.new(
                self._app_secret.encode("utf-8"),
                string_to_sign.encode("utf-8"),
                hashlib.sha256,
            ).digest()
            signature = base64.b64encode(hash_val).decode("utf-8")
            headers["x-ca-signature"] = signature
            async with session.post(
                f"https://{region_url}/api/prd/loginbyoauth.json",
                headers=headers,
                data={"loginByOauthRequest": json.dumps(_bodyParam, separators=(",", ":"))},
            ) as resp:
                data = await resp.json()
                logger.debug(data)
                if resp.status == 200:
                    self._login_by_oauth_response = LoginByOAuthResponse.from_dict(data)
                    return self._login_by_oauth_response
                raise LoginException(data)

    async def session_by_auth_code(self) -> SessionByAuthCodeResponse:
        """Create a session by auth code."""
        config = Config(
            app_key=self._app_key, app_secret=self._app_secret, domain=self._region_response.data.apiGatewayEndpoint
        )
        client = Client(config)

        # build request
        request = CommonParams(api_ver="1.0.4", language="en-US")
        body = IoTApiRequest(
            id=str(uuid.uuid4()),
            params={
                "request": {
                    "authCode": self._login_by_oauth_response.data.data.loginSuccessResult.sid,
                    "accountType": "OA_SESSION",
                    "appKey": self._app_key,
                }
            },
            request=request,
            version="1.0",
        )

        # send request
        response = await client.async_do_request(
            "/account/createSessionByAuthCode",
            "https",
            "POST",
            None,
            body,
            RuntimeOptions(),
        )
        logger.debug(response.status_message)
        logger.debug(response.headers)
        logger.debug(response.status_code)
        logger.debug(response.body)

        # Decode the response body
        response_body_str = response.body.decode("utf-8")

        # Load the JSON string into a dictionary
        response_body_dict = self.parse_json_response(response_body_str)

        session_by_auth = SessionByAuthCodeResponse.from_dict(response_body_dict)

        if int(session_by_auth.code) != 200:
            raise Exception("Error in creating session: " + response_body_str)

        if session_by_auth.data.identityId is None:
            raise Exception("Error in creating session: " + response_body_str)

        self._session_by_authcode_response = session_by_auth
        self._iot_token_issued_at = int(time.time())

        return response.body

    async def sign_out(self) -> dict:
        """Invalidate the current IoT session and return the raw response dictionary."""
        config = Config(
            app_key=self._app_key, app_secret=self._app_secret, domain=self._region_response.data.apiGatewayEndpoint
        )
        client = Client(config)

        # build request
        request = CommonParams(api_ver="1.0.4", language="en-US")
        body = IoTApiRequest(
            id=str(uuid.uuid4()),
            params={
                "request": {
                    "refreshToken": self._session_by_authcode_response.data.refreshToken,
                    "identityId": self._session_by_authcode_response.data.identityId,
                }
            },
            request=request,
            version="1.0",
        )

        # send request
        # possibly need to do this ourselves
        response = await client.async_do_request(
            "/iotx/account/invalidSession",
            "https",
            "POST",
            None,
            body,
            RuntimeOptions(),
        )
        logger.debug(response.status_message)
        logger.debug(response.headers)
        logger.debug(response.status_code)
        logger.debug(response.body)

        # Decode the response body
        response_body_str = response.body.decode("utf-8")

        # Load the JSON string into a dictionary
        response_body_dict = self.parse_json_response(response_body_str)
        return response_body_dict

    async def check_or_refresh_session(self) -> None:
        """Check or refresh the session."""
        logger.debug("Trying to refresh token")
        config = Config(
            app_key=self._app_key, app_secret=self._app_secret, domain=self._region_response.data.apiGatewayEndpoint
        )
        client = Client(config)

        # build request
        request = CommonParams(api_ver="1.0.4", language="en-US")
        body = IoTApiRequest(
            id=str(uuid.uuid4()),
            params={
                "request": {
                    "refreshToken": self._session_by_authcode_response.data.refreshToken,
                    "identityId": self._session_by_authcode_response.data.identityId,
                }
            },
            request=request,
            version="1.0",
        )

        # send request
        # possibly need to do this ourselves
        response = await client.async_do_request(
            "/account/checkOrRefreshSession",
            "https",
            "POST",
            None,
            body,
            RuntimeOptions(),
        )
        logger.debug(response.status_message)
        logger.debug(response.headers)
        logger.debug(response.status_code)
        logger.debug(response.body)

        # Decode the response body
        response_body_str = response.body.decode("utf-8")

        # Load the JSON string into a dictionary
        response_body_dict = self.parse_json_response(response_body_str)

        if int(response_body_dict.get("code")) != 200:
            logger.error(response_body_dict)
            await self.sign_out()
            raise SessionExpiredError(
                TransportType.CLOUD_ALIYUN, "Error check or refresh token: " + response_body_dict.__str__()
            )

        if response_body_dict.get("code") == 2401:
            await self.sign_out()
            raise SessionExpiredError(
                TransportType.CLOUD_ALIYUN, "Error check or refresh token: " + response_body_dict.__str__()
            )

        session = SessionByAuthCodeResponse.from_dict(response_body_dict)
        session_data = session.data

        if (
            session_data is None
            or session_data.identityId is None
            or session_data.refreshTokenExpire is None
            or session_data.iotToken is None
            or session_data.iotTokenExpire is None
            or session_data.refreshToken is None
        ):
            raise Exception("Error check or refresh token: Parameters not correct")

        self._session_by_authcode_response = session
        self._iot_token_issued_at = int(time.time())

    async def list_binding_by_account(self) -> ListingDevAccountResponse:
        """List bindings by account."""
        config = Config(
            app_key=self._app_key, app_secret=self._app_secret, domain=self._region_response.data.apiGatewayEndpoint
        )

        client = Client(config)

        # build request
        request = CommonParams(
            api_ver="1.0.8",
            language="en-US",
            iot_token=self._session_by_authcode_response.data.iotToken,
        )
        body = IoTApiRequest(
            id=str(uuid.uuid4()),
            params={"pageSize": 100, "pageNo": 1},
            request=request,
            version="1.0",
        )

        # send request
        response = await client.async_do_request(
            "/uc/listBindingByAccount", "https", "POST", None, body, RuntimeOptions()
        )
        logger.debug(response.status_message)
        logger.debug(response.headers)
        logger.debug(response.status_code)
        logger.debug(response.body)

        # Decode the response body
        response_body_str = response.body.decode("utf-8")

        # Load the JSON string into a dictionary
        response_body_dict = self.parse_json_response(response_body_str)

        if int(response_body_dict.get("code")) != 200:
            raise Exception("Error in creating session: " + response_body_dict["message"])

        self._devices_by_account_response = ListingDevAccountResponse.from_dict(response_body_dict)
        return self._devices_by_account_response

    async def list_binding_by_dev(self, iot_id: str):
        """Retrieve the list of accounts bound to the specified device IoT ID."""
        config = Config(
            app_key=self._app_key, app_secret=self._app_secret, domain=self._region_response.data.apiGatewayEndpoint
        )

        client = Client(config)

        # build request
        request = CommonParams(
            api_ver="1.0.8",
            language="en-US",
            iot_token=self._session_by_authcode_response.data.iotToken,
        )
        body = IoTApiRequest(
            id=str(uuid.uuid4()),
            params={"pageSize": 100, "pageNo": 1, "iotId": iot_id},
            request=request,
            version="1.0",
        )

        # send request
        response = await client.async_do_request("/uc/listBindingByDev", "https", "POST", None, body, RuntimeOptions())
        logger.debug(response.status_message)
        logger.debug(response.headers)
        logger.debug(response.status_code)
        logger.debug(response.body)

        # Decode the response body
        response_body_str = response.body.decode("utf-8")

        # Load the JSON string into a dictionary
        response_body_dict = self.parse_json_response(response_body_str)

        if int(response_body_dict.get("code")) != 200:
            raise Exception("Error in getting shared device list: " + response_body_dict["msg"])

        self._devices_by_account_response = ListingDevAccountResponse.from_dict(response_body_dict)
        return self._devices_by_account_response

    async def confirm_share(self, record_list: list[str]) -> bool:
        """Accept pending share invitations for the given list of record IDs."""
        config = Config(
            app_key=self._app_key, app_secret=self._app_secret, domain=self._region_response.data.apiGatewayEndpoint
        )

        client = Client(config)

        # build request
        request = CommonParams(
            api_ver="1.0.7",
            language="en-US",
            iot_token=self._session_by_authcode_response.data.iotToken,
        )
        body = IoTApiRequest(
            id=str(uuid.uuid4()),
            params={"agree": 1, "recordIdList": record_list},
            request=request,
            version="1.0",
        )

        # send request
        response = await client.async_do_request("/uc/confirmShare", "https", "POST", None, body, RuntimeOptions())
        logger.debug(response.status_message)
        logger.debug(response.headers)
        logger.debug(response.status_code)
        logger.debug(response.body)

        # Decode the response body
        response_body_str = response.body.decode("utf-8")

        # Load the JSON string into a dictionary
        response_body_dict = self.parse_json_response(response_body_str)

        if int(response_body_dict.get("code")) != 200:
            raise Exception("Error in accepting share: " + response_body_dict["msg"])

        return True

    async def get_shared_notice_list(self) -> ShareNoticeListResponse:
        """Fetch the list of share notices for the current account (status: 0=accepted, -1=pending, 3=expired)."""
        ### status 0 accepted status -1 ready to be accepted 3 expired
        config = Config(
            app_key=self._app_key, app_secret=self._app_secret, domain=self._region_response.data.apiGatewayEndpoint
        )

        client = Client(config)

        # build request
        request = CommonParams(
            api_ver="1.0.9",
            language="en-US",
            iot_token=self._session_by_authcode_response.data.iotToken,
        )
        body = IoTApiRequest(
            id=str(uuid.uuid4()),
            params={"pageSize": 100, "pageNo": 1},
            request=request,
            version="1.0",
        )

        # send request
        response = await client.async_do_request(
            "/uc/getShareNoticeList", "https", "POST", None, body, RuntimeOptions()
        )
        logger.debug(response.status_message)
        logger.debug(response.headers)
        logger.debug(response.status_code)
        logger.debug(response.body)

        # Decode the response body
        response_body_str = response.body.decode("utf-8")

        # Load the JSON string into a dictionary
        response_body_dict = self.parse_json_response(response_body_str)

        if int(response_body_dict.get("code")) != 200:
            raise Exception("Error in getting shared notice list: " + response_body_dict["msg"])

        return ShareNoticeListResponse.from_dict(response_body_dict)

    async def send_cloud_command(self, iot_id: str, command: bytes) -> str:
        """Sends a cloud command to a specified IoT device.

        This function checks if the IoT token is expired and attempts to refresh it if
        possible. It then constructs a request using the provided command and sends it
        to the IoT device via an asynchronous HTTP POST request. The function handles
        various error codes and exceptions based on the response from the cloud
        service.

        When the gateway returns HTTP 429 (Too Many Requests) the call raises
        :exc:`TooManyRequestsException` and a circuit-breaker is armed: all
        subsequent calls are rejected immediately (without touching the network)
        until the backoff window expires.  The window starts at 60 seconds and
        doubles on each consecutive 429 (60 s → 120 s → 240 s → …).  A
        successful response resets both the window and the backoff counter.

        Args:
            iot_id (str): The unique identifier of the IoT device.
            command (bytes): The command to be sent to the IoT device in binary format.

        Returns:
            str: A unique message ID for the sent command.

        Raises:
            TooManyRequestsException: If the gateway returned 429 or the rate-limit
                window from a previous 429 has not yet expired.

        """
        if command is None:
            raise Exception("Command is missing / None")

        # Circuit-breaker gate: reject immediately while rate-limited.
        if time.monotonic() < self._rate_limited_until:
            raise TooManyRequestsException("rate limited — retry after backoff window", iot_id)

        """Check if iotToken is expired"""
        if self._iot_token_issued_at + self._session_by_authcode_response.data.iotTokenExpire <= (
            int(time.time()) + 3600
        ):
            """Token expired - Try to refresh - Check if refreshToken is not expired"""
            if self._iot_token_issued_at + self._session_by_authcode_response.data.refreshTokenExpire > (
                int(time.time())
            ):
                await self.check_or_refresh_session()
            else:
                raise AuthRefreshException("Refresh token expired. Please re-login")

        config = Config(
            app_key=self._app_key, app_secret=self._app_secret, domain=self._region_response.data.apiGatewayEndpoint
        )

        client = Client(config)
        # build request
        request = CommonParams(
            api_ver="1.0.5",
            language="en-US",
            iot_token=self._session_by_authcode_response.data.iotToken,
        )

        # TODO move to using InvokeThingServiceRequest()

        message_id = str(uuid.uuid4())

        body = IoTApiRequest(
            id=message_id,
            params={
                "args": {"content": self.converter.printBase64Binary(command)},
                "identifier": "device_protobuf_sync_service",
                "iotId": f"{iot_id}",
            },
            request=request,
            version="1.0",
        )
        logger.debug(self.converter.printBase64Binary(command))
        logger.debug(body)
        # send request
        runtime_options = RuntimeOptions(autoretry=True, backoff_policy="yes")
        response = await client.async_do_request("/thing/service/invoke", "https", "POST", None, body, runtime_options)
        logger.debug(response.status_message)
        logger.debug(response.headers)
        logger.debug(response.status_code)
        logger.debug(response.body)
        logger.debug(iot_id)

        if response.status_code == 429:
            logger.debug("too many requests — arming rate-limit circuit breaker for %.0f s", self._rate_limit_backoff)
            self._rate_limited_until = time.monotonic() + self._rate_limit_backoff
            self._rate_limit_backoff = self._rate_limit_backoff * 2
            raise TooManyRequestsException(response.status_message, iot_id)

        response_body_str = response.body.decode("utf-8")
        response_body_dict = self.parse_json_response(response_body_str)

        if int(response_body_dict.get("code")) != 200:
            if response_body_dict.get("code") == 6205:
                logger.debug("Device offline (6205): %s", iot_id)
                raise DeviceOfflineException(response_body_dict.get("code"), iot_id)
            logger.error(
                "Error in sending cloud command: %s - %s",
                str(response_body_dict.get("code")),
                str(response_body_dict.get("message")),
            )
            if response_body_dict.get("code") == 22000:
                logger.error(response.body)
                raise FailedRequestException(iot_id)
            if response_body_dict.get("code") == 20056:
                logger.debug("Gateway timeout.")
                raise GatewayTimeoutException(response_body_dict.get("code"), iot_id)

            if response_body_dict.get("code") == 29003:
                logger.debug("identityId is blank, refreshing Aliyun credentials")
                raise SessionExpiredError(
                    TransportType.CLOUD_ALIYUN, "identityId is blank (29003) — token refresh required"
                )

            if response_body_dict.get("code") == 460:
                logger.debug("iotToken expired, must re-login.")
                raise SessionExpiredError(TransportType.CLOUD_ALIYUN, response_body_dict.get("message"))

        if self.message_delay != 1:
            self.message_delay = 1
        # Successful response — reset the rate-limit circuit breaker.
        self._rate_limited_until = 0.0
        self._rate_limit_backoff = 60.0

        return message_id

    async def get_device_properties(self, iot_id: str) -> ThingPropertiesResponse:
        """List bindings by account."""
        config = Config(
            app_key=self._app_key, app_secret=self._app_secret, domain=self._region_response.data.apiGatewayEndpoint
        )

        client = Client(config)

        # build request
        request = CommonParams(
            api_ver="1.0.0",
            language="en-US",
            iot_token=self._session_by_authcode_response.data.iotToken,
        )
        body = IoTApiRequest(
            id=str(uuid.uuid4()),
            params={
                "iotId": f"{iot_id}",
            },
            request=request,
            version="1.0",
        )

        # send request
        response = await client.async_do_request("/thing/properties/get", "https", "POST", None, body, RuntimeOptions())
        logger.debug(response.status_message)
        logger.debug(response.headers)
        logger.debug(response.status_code)
        logger.debug(response.body)

        # Decode the response body
        response_body_str = response.body.decode("utf-8")

        # Load the JSON string into a dictionary
        response_body_dict = self.parse_json_response(response_body_str)

        if int(response_body_dict.get("code")) != 200:
            if msg := response_body_dict.get("msg"):
                raise ReLoginRequiredError("Error in getting properties: " + msg)
            raise ReLoginRequiredError("Error in getting properties: " + response_body_dict)

        return ThingPropertiesResponse.from_dict(response_body_dict)

    async def get_device_status(self, iot_id: str) -> ThingPropertiesResponse:
        """List bindings by account."""
        config = Config(
            app_key=self._app_key, app_secret=self._app_secret, domain=self._region_response.data.apiGatewayEndpoint
        )

        client = Client(config)

        # build request
        request = CommonParams(
            api_ver="1.0.5",
            language="en-US",
            iot_token=self._session_by_authcode_response.data.iotToken,
        )
        body = IoTApiRequest(
            id=str(uuid.uuid4()),
            params={
                "iotId": f"{iot_id}",
            },
            request=request,
            version="1.0",
        )

        # send request
        response = await client.async_do_request("/thing/status/get", "https", "POST", None, body, RuntimeOptions())
        logger.debug(response.status_message)
        logger.debug(response.headers)
        logger.debug(response.status_code)
        logger.debug(response.body)

        # Decode the response body
        response_body_str = response.body.decode("utf-8")

        # Load the JSON string into a dictionary
        response_body_dict = self.parse_json_response(response_body_str)

        if int(response_body_dict.get("code")) != 200:
            if msg := response_body_dict.get("msg"):
                raise ReLoginRequiredError("Error in getting properties: " + msg)
            raise ReLoginRequiredError("Error in getting properties: " + response_body_dict)
        logger.debug(response_body_dict)
        return ThingPropertiesResponse.from_dict(response_body_dict)

    @property
    def devices_by_account_response(self):
        """Return the cached device listing response for the current account."""
        return self._devices_by_account_response

    def set_http(self, mammotion_http: MammotionHTTP) -> None:
        """Replace the underlying MammotionHTTP instance used for authentication."""
        self.mammotion_http = mammotion_http

    @property
    def region_response(self) -> RegionResponse | None:
        """Return the cached region response, or None if not yet fetched."""
        return self._region_response

    @property
    def aep_response(self) -> AepResponse | None:
        """Return the cached AEP authentication response, or None if not yet fetched."""
        return self._aep_response

    @property
    def session_by_authcode_response(self) -> SessionByAuthCodeResponse:
        """Return the current session-by-auth-code response containing the IoT token."""
        return self._session_by_authcode_response

    @property
    def client_id(self) -> str:
        """Return the hardware-derived client ID used for MQTT authentication."""
        return self._client_id

    @property
    def login_by_oauth_response(self) -> LoginByOAuthResponse | None:
        """Return the cached OAuth login response, or None if not yet performed."""
        return self._login_by_oauth_response

    @property
    def connect_response(self) -> ConnectResponse | None:
        """Return the cached connect response, or None if not yet performed."""
        return self._connect_response

    def to_cache(self) -> dict[str, Any]:
        """Serialize cloud credentials to a cache dictionary.

        Returns a dict containing all response objects needed to restore the cloud
        connection without re-authenticating. Fields with a None value are omitted.
        """
        raw: dict[str, Any] = {
            "connect_response": self._connect_response,
            "auth_data": self._login_by_oauth_response,
            "region_data": self._region_response,
            "aep_data": self._aep_response,
            "session_data": self._session_by_authcode_response,
            "device_data": self._devices_by_account_response,
            "mammotion_data": self.mammotion_http.response,
            "mammotion_mqtt": self.mammotion_http.mqtt_credentials,
            "mammotion_device_list": self.mammotion_http.device_info,
            "mammotion_device_records": self.mammotion_http.device_records,
            "mammotion_jwt_info": self.mammotion_http.jwt_info,
        }
        return {k: v for k, v in raw.items() if v is not None}

    @classmethod
    async def from_cache(
        cls,
        data: dict[str, Any],
        account: str,
        password: str,
        ha_version: str | None = None,
    ) -> "CloudIOTGateway | None":
        """Reconstruct a CloudIOTGateway from a previously serialized cache dictionary.

        Returns None if any required field is missing or if an error occurs during
        reconstruction or session refresh.

        Args:
            data: Cache dictionary previously produced by :meth:`to_cache`.
            account: User account (email / username) for the MammotionHTTP instance.
            password: User password for the MammotionHTTP instance.
            ha_version: Optional Home Assistant integration version forwarded to
                the inner MammotionHTTP for the ``App-Version`` header.

        """
        required_keys = (
            "connect_response",
            "auth_data",
            "region_data",
            "aep_data",
            "session_data",
            "device_data",
            "mammotion_data",
        )
        if any(k not in data for k in required_keys):
            return None

        connect_data = data["connect_response"]
        auth_data = data["auth_data"]
        region_data = data["region_data"]
        aep_data = data["aep_data"]
        session_data = data["session_data"]
        device_data = data["device_data"]
        mammotion_data = data["mammotion_data"]
        mammotion_mqtt = data.get("mammotion_mqtt")
        mammotion_device_list = data.get("mammotion_device_list")
        mammotion_device_records = data.get("mammotion_device_records")
        mammotion_jwt = data.get("mammotion_jwt_info")

        if any(
            v is None
            for v in [connect_data, auth_data, region_data, aep_data, session_data, device_data, mammotion_data]
        ):
            return None

        mammotion_response_data: Response[LoginResponseData] = (
            response_factory(Response[LoginResponseData], mammotion_data)
            if isinstance(mammotion_data, dict)
            else mammotion_data
        )

        mammotion_http = MammotionHTTP(account, password, ha_version=ha_version)
        mammotion_http.response = mammotion_response_data
        if mammotion_device_list:
            mammotion_http.device_info = (
                [DeviceInfo.from_dict(d) if isinstance(d, dict) else d for d in mammotion_device_list]
                if isinstance(mammotion_device_list, list)
                else mammotion_device_list
            )
        if mammotion_device_records:
            mammotion_http.device_records = (
                DeviceRecords.from_dict(mammotion_device_records)
                if isinstance(mammotion_device_records, dict)
                else mammotion_device_records
            )
        try:
            if mammotion_mqtt:
                mammotion_http.mqtt_credentials = (
                    MQTTConnection.from_dict(mammotion_mqtt) if isinstance(mammotion_mqtt, dict) else mammotion_mqtt
                )
        except MissingField:
            mammotion_http.mqtt_credentials = None

        if mammotion_jwt:
            mammotion_http.jwt_info = (
                JWTTokenInfo.from_dict(mammotion_jwt) if isinstance(mammotion_jwt, dict) else mammotion_jwt
            )
        mammotion_http.login_info = (
            LoginResponseData.from_dict(mammotion_response_data.data)
            if isinstance(mammotion_response_data.data, dict)
            else mammotion_response_data.data
        )

        try:
            cloud_client = cls(
                connect_response=ConnectResponse.from_dict(connect_data)
                if isinstance(connect_data, dict)
                else connect_data,
                aep_response=AepResponse.from_dict(aep_data) if isinstance(aep_data, dict) else aep_data,
                region_response=RegionResponse.from_dict(region_data) if isinstance(region_data, dict) else region_data,
                session_by_authcode_response=SessionByAuthCodeResponse.from_dict(session_data)
                if isinstance(session_data, dict)
                else session_data,
                dev_by_account=ListingDevAccountResponse.from_dict(device_data)
                if isinstance(device_data, dict)
                else device_data,
                login_by_oauth_response=LoginByOAuthResponse.from_dict(auth_data)
                if isinstance(auth_data, dict)
                else auth_data,
                mammotion_http=mammotion_http,
            )
        except Exception:
            logger.exception("Error while restoring cloud data")
            return None

        await cloud_client.check_or_refresh_session()
        return cloud_client
