
import os

from alibabacloud_iot_api_gateway.models import Config, IoTApiRequest, CommonParams
from alibabacloud_iot_api_gateway.client import Client
from alibabacloud_tea_util.models import RuntimeOptions

# init client


class CloudIOTGateway:


    def __init__(self):
        pass

    def get_region(countryCode: str, authCode: str):
        # shim out the regions?
        #  https://api.link.aliyun.com/living/account/region/get?x-ca-request-id=59abc767-fbbc-4333-9127-e65d792133a8
        # x-ca-request-id is a random UUID on each request
        # app key should be right
        # app secret is the authCode / authorisation_code ZUZp6lac2nDJOtF51hLGnnCn
        # 34231230
        config = Config(
            app_key='34231230', # correct
            app_secret='1ba85698bb10e19c6437413b61ba3445', # ? mystery
            domain='api.link.aliyun.com'
        )
        client = Client(config)
        # build request
        request = CommonParams(api_ver='1.0.2', language='en-US')
        body = IoTApiRequest(
            id='d829602f-dd48-457b-8fae-6c83a788299d',
            params= {
              "authCode": authCode,
              "type": "THIRD_AUTHCODE",
              "countryCode": countryCode
            },
            request=request,
            version='1.0'
        )

        testParams = {
          "params": {
            "authCode": "ZUZp6lac2nDJOtF51hLGnnCn",
            "type": "THIRD_AUTHCODE",
            "countryCode": "NZ"
          },
          "request": {
            "apiVer": "1.0.2",
            "language": "en-US"
          },
          "version": "1.0"
        }

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

        return response.body
