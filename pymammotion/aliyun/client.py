import asyncio
import time
import uuid

from alibabacloud_apigateway_util.client import Client as APIGatewayUtilClient
from alibabacloud_tea_util.client import Client as UtilClient
from Tea.exceptions import UnretryableException
from Tea.request import TeaRequest

from pymammotion.aliyun.tea.core import TeaCore


class Client:
    """test."""

    _app_key: str | None = None
    _app_secret: str | None = None
    _protocol: str | None = None
    _user_agent: str | None = None
    _read_timeout: int | None = None
    _connect_timeout: int | None = None
    _http_proxy: str | None = None
    _https_proxy: str | None = None
    _no_proxy: str | None = None
    _max_idle_conns: int | None = None
    _domain: str | None = None

    def __init__(self, config) -> None:
        self._domain = config.domain
        self._app_key = config.app_key
        self._app_secret = config.app_secret
        self._protocol = config.protocol
        self._read_timeout = config.read_timeout
        self._connect_timeout = config.connect_timeout
        self._http_proxy = config.http_proxy
        self._https_proxy = config.https_proxy
        self._no_proxy = config.no_proxy
        self._max_idle_conns = config.max_idle_conns

    async def async_do_request(self, pathname: str, protocol: str, method: str, header: dict[str, str], body, runtime):
        """Send request.

        @type pathname: str
        @param pathname: the url path

        @type protocol: str
        @param protocol: http or https

        @type method: str
        @param method: example GET

        @type header: Dict[str, str]
        @param header: request header

        @type body: iot_api_gateway_models.IoTApiRequest
        @param body: the object of IoTApiRequest

        @type runtime: util_models.RuntimeOptions
        @param runtime: which controls some details of call api, such as retry times

        @rtype: TeaResponse
        @return: the response
        """
        body.validate()
        runtime.validate()
        _runtime = {
            "timeouted": "retry",
            "readTimeout": UtilClient.default_number(runtime.read_timeout, self._read_timeout or 0),
            "connectTimeout": UtilClient.default_number(runtime.connect_timeout, self._connect_timeout or 0),
            "httpProxy": UtilClient.default_string(runtime.http_proxy, self._http_proxy or ""),
            "httpsProxy": UtilClient.default_string(runtime.https_proxy, self._https_proxy or ""),
            "noProxy": UtilClient.default_string(runtime.no_proxy, self._no_proxy or ""),
            "maxIdleConns": UtilClient.default_number(runtime.max_idle_conns, self._max_idle_conns or 0),
            "retry": {
                "retryable": runtime.autoretry,
                "maxAttempts": UtilClient.default_number(runtime.max_attempts, 3),
            },
            "backoff": {
                "policy": UtilClient.default_string(runtime.backoff_policy, "yes"),
                "period": UtilClient.default_number(runtime.backoff_period, 1),
            },
            "ignoreSSL": runtime.ignore_ssl,
        }
        _last_request = None
        _last_exception = None
        _now = time.time()
        _retry_times = 0
        while TeaCore.allow_retry(_runtime.get("retry"), _retry_times, _now):
            if _retry_times > 0:
                _backoff_time = TeaCore.get_backoff_time(_runtime.get("backoff"), _retry_times)
                if _backoff_time > 0:
                    await TeaCore.sleep_async(_backoff_time)
            _retry_times = _retry_times + 1
            try:
                _request = TeaRequest()
                _request.protocol = UtilClient.default_string(self._protocol or "", protocol)
                _request.method = UtilClient.default_string(method, "POST")
                _request.pathname = pathname
                _request.query = {"x-ca-request-id": str(uuid.uuid4())}
                _request.headers = TeaCore.merge(
                    {
                        "host": self._domain,
                        "date": UtilClient.get_date_utcstring(),
                        "x-ca-nonce": UtilClient.get_nonce(),
                        "x-ca-key": self._app_key,
                        "x-ca-signaturemethod": "HmacSHA256",
                        "accept": "application/json; charset=utf-8",
                        "Accept-Encoding": "gzip",
                        "user-agent": "ALIYUN-ANDROID-DEMO",
                        "x-ca-timestamp": str(int(time.time_ns())),
                    },
                    header,
                )
                if UtilClient.empty(body.id):
                    body.id = UtilClient.get_nonce()
                if not UtilClient.is_unset(body):
                    _request.headers["content-type"] = "application/octet-stream"
                    _request.headers["content-md5"] = APIGatewayUtilClient.get_content_md5(
                        UtilClient.to_jsonstring(TeaCore.to_map(body))
                    )
                    _request.body = UtilClient.to_jsonstring(TeaCore.to_map(body))
                _request.headers["x-ca-signature"] = APIGatewayUtilClient.get_signature(_request, self._app_secret)
                _request.headers["ca_version"] = "1"
                _last_request = _request
                return await TeaCore.async_do_action(_request, _runtime)
            except asyncio.CancelledError:
                # Never swallow cancellation: eating it here re-sends the request
                # (autoretry) or masks the cancel as UnretryableException.
                raise
            except Exception as e:
                if TeaCore.is_retryable(e):
                    _last_exception = e
                    continue
                raise e
        raise UnretryableException(_last_request, _last_exception)  # type: ignore

    def get_user_agent(self) -> str:
        """Get user agent.

        @rtype: str
        @return: user agent
        """
        return self._user_agent or ""
