import hashlib
import hmac
import os
import time

from alibabacloud_iot_api_gateway.models import Config, IoTApiRequest, CommonParams
from alibabacloud_iot_api_gateway.client import Client
from alibabacloud_tea_util.models import RuntimeOptions


# init client


class CloudIOTGateway:

    _app_secret = ""

    def __init__(self):
        self._region = None
        self._app_key = "34231230"
        self._app_secret = "1ba85698bb10e19c6437413b61ba3445"
        self.domain = 'api.link.aliyun.com'


    def sign(self, data):
        keys = ["appKey", "clientId", "deviceSn", "timestamp"]
        concatenated_str = ""
        for key in keys:
            concatenated_str += f"{key}{data.get(key, '')}"

        print(f"sign(), toSignStr = {concatenated_str}")

        sign = hmac.new(self._app_secret.encode('utf-8'), concatenated_str.encode("utf-8"), hashlib.sha1).hexdigest()

        return sign

    def get_region(self, countryCode: str, authCode: str):
        # shim out the regions?
        #  https://api.link.aliyun.com/living/account/region/get?x-ca-request-id=59abc767-fbbc-4333-9127-e65d792133a8
        # x-ca-request-id is a random UUID on each request

        config = Config(
            app_key=self._app_key,  # correct
            app_secret=self._app_secret,
            domain=self.domain
        )
        client = Client(config)

        # build request
        request = CommonParams(api_ver='1.0.2', language='en-US')
        body = IoTApiRequest(
            id='d829602f-dd48-457b-8fae-6c83a788299d',
            params={
                "authCode": authCode,
                "type": "THIRD_AUTHCODE",
                "countryCode": countryCode
            },
            request=request,
            version='1.0'
        )

        # send request
        # possibly need to do this ourselves
        response = client.do_request(
            '/living/account/region/get',
            'https',
            'POST',
            None,
            body,
            RuntimeOptions()
        )
        print(response.status_message)
        print(response.headers)
        print(response.status_code)
        print(response.body)
        
        self._region = response.body.data

        return response.body

    def aep_handle(self):

        # https://api.link.aliyun.com/app/aepauth/handle

        config = Config(
            app_key=self._app_key,  # correct
            app_secret=self._app_secret,
            domain=self.domain
        )
        client = Client(config)

        request = CommonParams(api_ver='1.0.0', language='en-US')

        time_now = time.time()
        data_to_sign = {
            'appKey': self._app_key,
            "clientId": "J5Qvtx7G", # needs to be unique to device
            "deviceSn": "1Pcsgh7S2BPAKEJCw3ZwmowQf4QxmpGC", # same here
            "timestamp": str(time_now)
        }


        body = IoTApiRequest(
            id='d829602f-dd48-457b-8fae-6c83a788299d',
            params={
                "authInfo": {
                  "clientId": "J5Qvtx7G",
                  "sign": self.sign(data_to_sign),
                  "deviceSn": "1Pcsgh7S2BPAKEJCw3ZwmowQf4QxmpGC",
                  "timestamp": str(time_now)
                }
              },
            request=request,
            version='1.0'
        )

        # send request
        # possibly need to do this ourselves
        response = client.do_request(
            '/app/aepauth/handle',
            'https',
            'POST',
            None,
            body,
            RuntimeOptions()
        )
        print(response.status_message)
        print(response.headers)
        print(response.status_code)
        print(response.body)


    def connect(self):
        pass
        # https://living-account.ap-southeast-1.aliyuncs.com/api/prd/connect.json
        # URL encoded

        # {"refreshSid":
    # {"refreshToken":"OA-a9447417e01d4b4b96d3fc97948e6b4b",
    # "sid":"180aefe93476485dbb5cbc115fcd9654"},
    # "context":{"sdkVersion":"3.4.2","utDid":"Zi2hDodJNvIDAIvdzsWJ2o0w","platformName":"android","netType":"wifi","appKey":"34231230","yunOSId":"","appVersion":"1.11.220",
    # "appAuthToken":"TIABYmVLPIfeLAKPT+Gd69A+j7LVXA0d",
    # "securityToken":"TIABYmVLPIfeLAKPT+Gd69A+j7LVXA0d"},
    # "config":{"version":0,"lastModify":0}}


    def login_by_oauth(self):
        """loginbyoauth.json."""

        region_url = self._region.oaApiGatewayEndpoint

        config = Config(
            app_key=self._app_key,  # correct
            app_secret=self._app_secret,
            domain=region_url
        )
        client = Client(config)

        # headers require sid vid

    def session_by_auth_code(self, auth_code):

        # {"id":"a52f2d54-fd62-4f04-a0dd-efca0adaff9c",
        # "params":
        # ,"request":{"apiVer":"1.0.4","language":"en-US"},"version":"1.0"}
        config = Config(
            app_key=self._app_key,  # correct
            app_secret=self._app_secret,
            domain=self.domain
        )
        client = Client(config)

        # build request
        request = CommonParams(api_ver='1.0.2', language='en-US')
        body = IoTApiRequest(
            id='d829602f-dd48-457b-8fae-6c83a788299d',
            params={"request":{"authCode":"180aefe93476485dbb5cbc115fcd9654","accountType":"OA_SESSION","appKey":"34231230"}},
            request=request,
            version='1.0'
        )

        # send request
        # possibly need to do this ourselves
        response = client.do_request(
            '/living/account/region/get',
            'https',
            'POST',
            None,
            body,
            RuntimeOptions()
        )
        print(response.status_message)
        print(response.headers)
        print(response.status_code)
        print(response.body)

        self._region = response.body.data

        return response.body






