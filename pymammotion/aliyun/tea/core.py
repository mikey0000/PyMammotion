import asyncio
import logging
import os
import socket
import ssl
import time
from typing import Any
from urllib.parse import urlencode, urlparse

import aiohttp
import certifi
from requests import PreparedRequest, adapters, status_codes
from Tea.exceptions import RequiredArgumentException, RetryError
from Tea.model import TeaModel
from Tea.request import TeaRequest
from Tea.response import TeaResponse
from Tea.stream import BaseStream

DEFAULT_CONNECT_TIMEOUT = 5000
DEFAULT_READ_TIMEOUT = 10000
DEFAULT_POOL_SIZE = 10

logger = logging.getLogger("alibabacloud-tea")
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
logger.addHandler(ch)


class TeaCore:
    http_adapter = adapters.HTTPAdapter(pool_connections=DEFAULT_POOL_SIZE, pool_maxsize=DEFAULT_POOL_SIZE * 4)
    https_adapter = adapters.HTTPAdapter(pool_connections=DEFAULT_POOL_SIZE, pool_maxsize=DEFAULT_POOL_SIZE * 4)

    @staticmethod
    def get_adapter(prefix):
        if prefix.upper() == "HTTP":
            return TeaCore.http_adapter
        else:
            return TeaCore.https_adapter

    @staticmethod
    def _prepare_http_debug(request, symbol):
        base = ""
        for key, value in request.headers.items():
            base += f"\n{symbol} {key} : {value}"
        return base

    @staticmethod
    def _do_http_debug(request, response) -> None:
        # logger the request
        url = urlparse(request.url)
        request_base = f"\n> {request.method.upper()} {url.path + url.query} HTTP/1.1"
        logger.debug(request_base + TeaCore._prepare_http_debug(request, ">"))

        # logger the response
        response_base = (
            f"\n< HTTP/1.1 {response.status_code}" f" {status_codes._codes.get(response.status_code)[0].upper()}"
        )
        logger.debug(response_base + TeaCore._prepare_http_debug(response, "<"))

    @staticmethod
    def compose_url(request):
        host = request.headers.get("host")
        if not host:
            raise RequiredArgumentException("endpoint")
        else:
            host = host.rstrip("/")
        protocol = f"{request.protocol.lower()}://"
        pathname = request.pathname

        if host.startswith(("http://", "https://")):
            protocol = ""

        if request.port == 80:
            port = ""
        else:
            port = f":{request.port}"

        url = protocol + host + port + pathname

        if request.query:
            if "?" in url:
                if not url.endswith("&"):
                    url += "&"
            else:
                url += "?"

            encode_query = {}
            for key in request.query:
                value = request.query[key]
                if value is not None:
                    encode_query[key] = str(value)
            url += urlencode(encode_query)
        return url.rstrip("?&")

    @staticmethod
    async def async_do_action(request: TeaRequest, runtime_option=None) -> TeaResponse:
        runtime_option = runtime_option or {}

        url = TeaCore.compose_url(request)
        verify = not runtime_option.get("ignoreSSL", False)

        timeout = runtime_option.get("timeout")
        connect_timeout = runtime_option.get("connectTimeout") or timeout or DEFAULT_CONNECT_TIMEOUT
        read_timeout = runtime_option.get("readTimeout") or timeout or DEFAULT_READ_TIMEOUT

        connect_timeout, read_timeout = (int(connect_timeout) / 1000, int(read_timeout) / 1000)

        proxy = None
        if request.protocol.upper() == "HTTP":
            proxy = runtime_option.get("httpProxy")
            if not proxy:
                proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        elif request.protocol.upper() == "HTTPS":
            proxy = runtime_option.get("httpsProxy")
            if not proxy:
                proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")

        connector = None
        ca_cert = certifi.where()
        if ca_cert and request.protocol.upper() == "HTTPS":
            loop = asyncio.get_event_loop()

            ssl_context = await loop.run_in_executor(None, ssl.create_default_context, ssl.Purpose.SERVER_AUTH)
            await loop.run_in_executor(None, ssl_context.load_verify_locations, ca_cert)
            connector = aiohttp.TCPConnector(
                ssl=ssl_context,
                family=socket.AF_INET,
            )
        else:
            verify = False

        timeout = aiohttp.ClientTimeout(sock_read=read_timeout, sock_connect=connect_timeout)
        async with aiohttp.ClientSession(connector=connector) as s:
            body = b""
            if isinstance(request.body, BaseStream):
                for content in request.body:
                    body += content
            elif isinstance(request.body, str):
                body = request.body.encode("utf-8")
            else:
                body = request.body
            try:
                async with s.request(
                    request.method, url, data=body, headers=request.headers, ssl=verify, proxy=proxy, timeout=timeout
                ) as response:
                    tea_resp = TeaResponse()
                    tea_resp.body = await response.read()
                    tea_resp.headers = {k.lower(): v for k, v in response.headers.items()}
                    tea_resp.status_code = response.status
                    tea_resp.status_message = response.reason
                    tea_resp.response = response
            except OSError as e:
                raise RetryError(str(e))
        return tea_resp

    @staticmethod
    def do_action(request: TeaRequest, runtime_option=None) -> TeaResponse:
        url = TeaCore.compose_url(request)

        runtime_option = runtime_option or {}

        verify = not runtime_option.get("ignoreSSL", False)
        if verify:
            verify = runtime_option.get("ca", True) if runtime_option.get("ca", True) is not None else True
        cert = runtime_option.get("cert", None)

        timeout = runtime_option.get("timeout")
        connect_timeout = runtime_option.get("connectTimeout") or timeout or DEFAULT_CONNECT_TIMEOUT
        read_timeout = runtime_option.get("readTimeout") or timeout or DEFAULT_READ_TIMEOUT

        timeout = (int(connect_timeout) / 1000, int(read_timeout) / 1000)

        if isinstance(request.body, str):
            request.body = request.body.encode("utf-8")

        p = PreparedRequest()
        p.prepare(
            method=request.method.upper(),
            url=url,
            data=request.body,
            headers=request.headers,
        )

        proxies = {}
        http_proxy = runtime_option.get("httpProxy")
        https_proxy = runtime_option.get("httpsProxy")
        no_proxy = runtime_option.get("noProxy")

        if not http_proxy:
            http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        if not https_proxy:
            https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")

        if http_proxy:
            proxies["http"] = http_proxy
        if https_proxy:
            proxies["https"] = https_proxy
        if no_proxy:
            proxies["no_proxy"] = no_proxy

        adapter = TeaCore.get_adapter(request.protocol)
        try:
            resp = adapter.send(
                p,
                proxies=proxies,
                timeout=timeout,
                verify=verify,
                cert=cert,
            )
        except OSError as e:
            raise RetryError(str(e))

        debug = runtime_option.get("debug") or os.getenv("DEBUG")
        if debug and debug.lower() == "sdk":
            TeaCore._do_http_debug(p, resp)

        response = TeaResponse()
        response.status_message = resp.reason
        response.status_code = resp.status_code
        response.headers = {k.lower(): v for k, v in resp.headers.items()}
        response.body = resp.content
        response.response = resp
        return response

    @staticmethod
    def get_response_body(resp) -> str:
        return resp.content.decode("utf-8")

    @staticmethod
    def allow_retry(dic, retry_times, now=None) -> bool:
        if retry_times == 0:
            return True
        if dic is None or not dic.__contains__("maxAttempts") or dic.get("retryable") is not True and retry_times >= 1:
            return False
        else:
            retry = 0 if dic.get("maxAttempts") is None else int(dic.get("maxAttempts"))
        return retry >= retry_times

    @staticmethod
    def get_backoff_time(dic, retry_times) -> int:
        default_back_off_time = 0
        if dic is None or not dic.get("policy") or dic.get("policy") == "no":
            return default_back_off_time

        back_off_time = dic.get("period", default_back_off_time)
        if not isinstance(back_off_time, int) and not (isinstance(back_off_time, str) and back_off_time.isdigit()):
            return default_back_off_time

        back_off_time = int(back_off_time)
        if back_off_time < 0:
            return retry_times

        return back_off_time

    @staticmethod
    async def sleep_async(t) -> None:
        await asyncio.sleep(t)

    @staticmethod
    def sleep(t) -> None:
        time.sleep(t)

    @staticmethod
    def is_retryable(ex) -> bool:
        return isinstance(ex, RetryError)

    @staticmethod
    def bytes_readable(body):
        return body

    @staticmethod
    def merge(*dic_list) -> dict:
        dic_result = {}
        for item in dic_list:
            if isinstance(item, dict):
                dic_result.update(item)
            elif isinstance(item, TeaModel):
                dic_result.update(item.to_map())
        return dic_result

    @staticmethod
    def to_map(model: TeaModel | None) -> dict[str, Any]:
        if isinstance(model, TeaModel):
            return model.to_map()
        else:
            return dict()

    @staticmethod
    def from_map(model: TeaModel, dic: dict[str, Any]) -> TeaModel:
        if isinstance(model, TeaModel):
            try:
                return model.from_map(dic)
            except Exception:
                model._map = dic
                return model
        else:
            return model
