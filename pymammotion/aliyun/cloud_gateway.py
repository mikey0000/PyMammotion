"""Module for interacting with Aliyun Cloud IoT Gateway."""

import base64
import hashlib
import hmac
import itertools
import json
from logging import getLogger
import random
import string
import time
import uuid

from aiohttp import ClientSession, ConnectionTimeoutError
from alibabacloud_iot_api_gateway.models import CommonParams, Config, IoTApiRequest
from alibabacloud_tea_util.client import Client as UtilClient
from alibabacloud_tea_util.models import RuntimeOptions
from orjson.orjson import JSONDecodeError
from Tea.exceptions import UnretryableException

from pymammotion.aliyun.client import Client
from pymammotion.aliyun.model.aep_response import AepResponse
from pymammotion.aliyun.model.connect_response import ConnectResponse
from pymammotion.aliyun.model.dev_by_account_response import ListingDevByAccountResponse
from pymammotion.aliyun.model.login_by_oauth_response import LoginByOAuthResponse
from pymammotion.aliyun.model.regions_response import RegionResponse
from pymammotion.aliyun.model.session_by_authcode_response import SessionByAuthCodeResponse
from pymammotion.aliyun.regions import region_mappings
from pymammotion.const import ALIYUN_DOMAIN, APP_KEY, APP_SECRET, APP_VERSION
from pymammotion.http.http import MammotionHTTP
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


class SetupException(Exception):
    """Raise when mqtt expires token or token is invalid."""

    def __init__(self, *args: object) -> None:
        super().__init__(args)
        self.iot_id = args[1]


class AuthRefreshException(Exception):
    """Raise exception when library cannot refresh token."""


class DeviceOfflineException(Exception):
    """Raise exception when device is offline."""

    def __init__(self, *args: object) -> None:
        super().__init__(args)
        self.iot_id = args[1]


class FailedRequestException(Exception):
    """Raise exception when request response is bad."""

    def __init__(self, *args: object) -> None:
        super().__init__(args)
        self.iot_id = args[0]


class NoConnectionException(UnretryableException):
    """Raise exception when device is unreachable."""


class GatewayTimeoutException(Exception):
    """Raise exception when the gateway times out."""

    def __init__(self, *args: object) -> None:
        super().__init__(args)
        self.iot_id = args[1]


class LoginException(Exception):
    """Raise exception when library cannot log in."""


class CheckSessionException(Exception):
    """Raise exception when checking session results in a failure."""


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
        dev_by_account: ListingDevByAccountResponse | None = None,
    ) -> None:
        """Initialize the CloudIOTGateway."""
        self.mammotion_http: MammotionHTTP = mammotion_http
        self._app_key = APP_KEY
        self._app_secret = APP_SECRET
        self.domain = ALIYUN_DOMAIN

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
    def generate_random_string(length: int):
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
        try:
            return json.loads(response_body_str) if response_body_str is not None else {}
        except JSONDecodeError:
            logger.error("Couldn't decode message %s", response_body_str)
            return {'code': 22000}

    def sign(self, data):
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

    async def get_region(self, country_code: str):
        """Get the region based on country code and auth code."""
        auth_code = self.mammotion_http.login_info.authorization_code

        if self._region_response is not None:
            return self._region_response

        config = Config(
            app_key=self._app_key,
            app_secret=self._app_secret,
            domain=self.domain,
        )
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
                "/living/account/region/get", "https", "POST", None, body, RuntimeOptions()
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
            raise Exception("Error in getting regions: " + response_body_dict["msg"])

        self._region_response = RegionResponse.from_dict(response_body_dict)
        logger.debug("Endpoint: %s", self._region_response.data.mqttEndpoint)

        return response.body

    async def aep_handle(self):
        """Handle AEP authentication."""
        aep_domain = self.domain

        if self._region_response.data.apiGatewayEndpoint is not None:
            aep_domain = self._region_response.data.apiGatewayEndpoint

        config = Config(
            app_key=self._app_key,
            app_secret=self._app_secret,
            domain=aep_domain,
        )
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

        return response.body

    async def connect(self):
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
                f"loginByOauthRequest={json.dumps(_bodyParam, separators=(",", ":"))}",
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

    async def session_by_auth_code(self):
        """Create a session by auth code."""
        config = Config(
            app_key=self._app_key,
            app_secret=self._app_secret,
            domain=self._region_response.data.apiGatewayEndpoint,
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
        config = Config(
            app_key=self._app_key,
            app_secret=self._app_secret,
            domain=self._region_response.data.apiGatewayEndpoint,
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

    async def check_or_refresh_session(self):
        """Check or refresh the session."""
        logger.debug("Trying to refresh token")
        config = Config(
            app_key=self._app_key,
            app_secret=self._app_secret,
            domain=self._region_response.data.apiGatewayEndpoint,
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
            raise CheckSessionException("Error check or refresh token: " + response_body_dict.__str__())

        session = SessionByAuthCodeResponse.from_dict(response_body_dict)
        session_data = session.data

        if (
            session_data.identityId is None
            or session_data.refreshTokenExpire is None
            or session_data.iotToken is None
            or session_data.iotTokenExpire is None
            or session_data.refreshToken is None
        ):
            raise Exception("Error check or refresh token: Parameters not correct")

        self._session_by_authcode_response = session
        self._iot_token_issued_at = int(time.time())

    async def list_binding_by_account(self) -> ListingDevByAccountResponse:
        """List bindings by account."""
        config = Config(
            app_key=self._app_key,
            app_secret=self._app_secret,
            domain=self._region_response.data.apiGatewayEndpoint,
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
            raise Exception("Error in creating session: " + response_body_dict["msg"])

        self._devices_by_account_response = ListingDevByAccountResponse.from_dict(response_body_dict)
        return self._devices_by_account_response

    async def list_binding_by_dev(self, iot_id: str):
        config = Config(
            app_key=self._app_key,
            app_secret=self._app_secret,
            domain=self._region_response.data.apiGatewayEndpoint,
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
            raise Exception("Error in creating session: " + response_body_dict["msg"])

        self._devices_by_account_response = ListingDevByAccountResponse.from_dict(response_body_dict)
        return self._devices_by_account_response

    async def send_cloud_command(self, iot_id: str, command: bytes) -> str:

        """Sends a cloud command to a specified IoT device.
        
        This function checks if the IoT token is expired and attempts to refresh it if
        possible. It then constructs a request using the provided command and sends it
        to the IoT device via an asynchronous HTTP POST request. The function handles
        various error codes and exceptions based on the response from the cloud
        service.
        
        Args:
            iot_id (str): The unique identifier of the IoT device.
            command (bytes): The command to be sent to the IoT device in binary format.
        
        Returns:
            str: A unique message ID for the sent command.
        """
        if command is None:
            raise Exception("Command is missing / None")

        """Check if iotToken is expired"""
        if self._iot_token_issued_at + self._session_by_authcode_response.data.iotTokenExpire <= (
            int(time.time()) + (5 * 3600)
        ):
            """Token expired - Try to refresh - Check if refreshToken is not expired"""
            if self._iot_token_issued_at + self._session_by_authcode_response.data.refreshTokenExpire > (
                int(time.time())
            ):
                await self.check_or_refresh_session()
            else:
                raise AuthRefreshException("Refresh token expired. Please re-login")

        config = Config(
            app_key=self._app_key,
            app_secret=self._app_secret,
            domain=self._region_response.data.apiGatewayEndpoint,
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
        # send request
        runtime_options = RuntimeOptions(autoretry=True, backoff_policy="yes")
        response = await client.async_do_request("/thing/service/invoke", "https", "POST", None, body, runtime_options)
        logger.debug(response.status_message)
        logger.debug(response.headers)
        logger.debug(response.status_code)
        logger.debug(response.body)
        logger.debug(iot_id)

        response_body_str = response.body.decode("utf-8")
        response_body_dict = self.parse_json_response(response_body_str)

        if int(response_body_dict.get("code")) != 200:
            logger.error(
                "Error in sending cloud command: %s - %s",
                str(response_body_dict.get("code")),
                str(response_body_dict.get("message")),
            )
            if response_body_dict.get("code") == 22000:
                logger.error(response)
                raise FailedRequestException(iot_id)
            if response_body_dict.get("code") == 20056:
                logger.debug("Gateway timeout.")
                raise GatewayTimeoutException(response_body_dict.get("code"), iot_id)

            if response_body_dict.get("code") == 29003:
                logger.debug(self._session_by_authcode_response.data.identityId)
                await self.sign_out()
                raise SetupException(response_body_dict.get("code"), iot_id)
            if response_body_dict.get("code") == 6205:
                raise DeviceOfflineException(response_body_dict.get("code"), iot_id)

        return message_id

    @property
    def devices_by_account_response(self):
        return self._devices_by_account_response

    def set_http(self, mammotion_http: MammotionHTTP) -> None:
        self.mammotion_http = mammotion_http

    @property
    def region_response(self) -> RegionResponse:
        return self._region_response

    @property
    def aep_response(self) -> AepResponse:
        return self._aep_response

    @property
    def session_by_authcode_response(self) -> SessionByAuthCodeResponse:
        return self._session_by_authcode_response

    @property
    def client_id(self) -> str:
        return self._client_id

    @property
    def login_by_oauth_response(self) -> LoginByOAuthResponse:
        return self._login_by_oauth_response

    @property
    def connect_response(self) -> ConnectResponse:
        return self._connect_response
