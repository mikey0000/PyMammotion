#
# Copyright (c) 2014-2018 Alibaba Group. All rights reserved.
# License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
#

import concurrent.futures
import hashlib
import hmac
import logging
import os
import ssl
import threading
import time
from types import TracebackType

import crcmod
import hyper


def _assert_value(condition, error_msg):
    if not condition:
        raise ValueError(error_msg)


_H2_OPT_HEART_BEAT_TIME_DEFAULT = 25
_H2_OPT_PORT_DEFAULT = 443
_H2_MAX_FILE_SIZE = 1024 * 1024 * 1024


def h2_set_option(opt, value) -> None:
    if opt == "heart_beat_interval":
        global _H2_OPT_HEART_BEAT_TIME_DEFAULT
        _H2_OPT_HEART_BEAT_TIME_DEFAULT = value
    elif opt == "port":
        global _H2_OPT_PORT_DEFAULT
        _H2_OPT_PORT_DEFAULT = value
    elif opt == "max_file_size":
        global _H2_MAX_FILE_SIZE
        _H2_MAX_FILE_SIZE = value


class StreamHandler:
    def __init__(self) -> None:
        pass

    def __enter__(self) -> None:
        pass

    def __exit__(
        self, type: type[BaseException] | None, value: BaseException | None, trace: TracebackType | None
    ) -> None:
        pass

    def get_content_length(self):
        return None

    def next(self):
        return None

    def has_next(self) -> bool:
        return False


class FileStreamHandler(StreamHandler):
    def __init__(self, filename, block_size=512 * 1024, opt_crc64=False) -> None:
        self.__filename = filename
        self.__block_size = block_size
        self.__size = os.stat(filename).st_size
        self.__opt_crc64 = opt_crc64
        self.__last_crc = 0
        self.__read_size = 0

    def get_content_length(self):
        return self.__size

    def __enter__(self) -> None:
        logging.debug("open the file, filename:%s" % self.__filename)
        self.__f = open(self.__filename, "rb")
        self.__read_size = 0

    def __exit__(
        self, type: type[BaseException] | None, value: BaseException | None, trace: TracebackType | None
    ) -> None:
        if self.__f:
            self.__f.close()
            self.__f = None

    def next(self):
        if not self.__f or self.__read_size >= self.__size:
            return None
        data = self.__f.read(self.__block_size)
        if data:
            self.__read_size += len(data)
        if self.__opt_crc64:
            do_crc64 = crcmod.mkCrcFun(
                0x142F0E1EBA9EA3693, initCrc=self.__last_crc, xorOut=0xFFFFFFFFFFFFFFFF, rev=True
            )
            self.__last_crc = do_crc64(data)
        return data

    def has_next(self):
        return self.__f.tell() < self.__size

    def get_crc64(self):
        return self.__last_crc

    def get_read_size(self):
        return self.__read_size


class H2Exception(Exception):
    def __init__(self, code, msg) -> None:
        Exception.__init__(self, msg)
        self.__code = code
        self.__msg = msg

    def get_code(self):
        return self.__code

    def get_msg(self):
        return self.__msg

    def __name__(self) -> str:
        return "H2Exception"


class UploadFileInfo:
    def __init__(self, local_filename, remote_filename=None, overwrite=True) -> None:
        self.local_filename = local_filename
        self.opt_overwrite = overwrite
        if not remote_filename:
            self.remote_filename = os.path.basename(local_filename)
        else:
            self.remote_filename = remote_filename

    def __name__(self) -> str:
        return "UploadFileInfo"


class UploadFileResult:
    def __init__(self, code=None, exception=None, upload_size=None, total_size=None, file_store_id=None) -> None:
        self.upload_size = upload_size
        self.total_size = total_size
        self.file_store_id = file_store_id
        self.code = code
        self.exception = exception

    def __name__(self) -> str:
        return "UploadFileResult"


class H2FileUploadSink:
    def on_file_upload_start(self, id, upload_file_info, user_data) -> None:
        pass

    def on_file_upload_end(self, id, upload_file_info, upload_file_result, user_data) -> None:
        pass

    def on_file_upload_progress(self, id, upload_file_info, upload_file_result, user_data) -> None:
        pass


class H2FileTask:
    def __init__(self, id, file_info, future_result) -> None:
        self.__file_info = file_info
        self.__future_result = future_result
        self.__id = id

    def get_file_info(self):
        return self.__file_info

    def get_future_result(self):
        return self.__future_result

    def result(self, timeout=None):
        return self.__future_result.result(timeout)

    def cancel(self) -> None:
        self.__future_result.call()

    def get_id(self):
        return self.__id

    def __name__(self) -> str:
        return "H2FileTask"


class H2Stream:
    def __init__(self, client, id) -> None:
        self.__client = client
        self.__conn = None
        # self.__length = None
        self.__total_sent_size = 0
        self.__path = None
        self.__id = id
        self.__stream_id = None
        self.__x_request_id = None
        self.__x_data_stream_id = None

    def __name__(self) -> str:
        return "H2Stream"

    def get_id(self):
        return self.__id

    def open(self, path, header):
        _assert_value(path, "path is required")

        with self.__client._get_auth_lock():
            url = "/stream/open" + path
            self.__conn = self.__client.get_connect()

            # self.__length = length
            self.__total_sent_size = 0
            self.__path = path

            logging.debug("request url: %s" % url)

            # open the stream
            conn_header = self.__client.get_default_header()
            if header:
                conn_header.update(header)

            req_id = self.__conn.request("GET", url, None, conn_header)
            response = self.__conn.get_response(req_id)

            self.__check_response(response)
            self.__x_request_id = response.headers["x-request-id"][0]
            self.__x_data_stream_id = response.headers["x-data-stream-id"][0]

            logging.debug("x_request_id: %s" % self.__x_request_id)
            logging.debug("x_data_stream_id: %s" % self.__x_data_stream_id)

            return response

    def close(self, header):
        logging.debug("close the stream")
        final_header = {"x-request-id": self.__x_request_id, "x-data-stream-id": self.__x_data_stream_id}
        final_header.update(header)
        req_id = self.__conn.request("GET", "/stream/close/" + self.__path, None, final_header)
        response = self.__conn.get_response(req_id)
        self.__check_response(response)
        return response

    def send(self, headers, data_handler):
        # prepare for sending
        with self.__client._get_auth_lock():
            url = "/stream/send" + self.__path
            logging.debug("request url: %s" % url)
            self.__stream_id = self.__conn.putrequest("GET", url)
            self.__conn.putheader("x-request-id", self.__x_request_id, stream_id=self.__stream_id)
            self.__conn.putheader("x-data-stream-id", self.__x_data_stream_id, stream_id=self.__stream_id)
            content_length = data_handler.get_content_length()
            if content_length:
                self.__conn.putheader("content-length", "%s" % (content_length), self.__stream_id)
            for k, v in headers.items():
                self.__conn.putheader(k, v, self.__stream_id)
            self.__conn.endheaders(stream_id=self.__stream_id)

        with data_handler:
            final = False
            while not final:
                data = data_handler.next()
                if data == None or len(data) == 0:
                    break
                final = not data_handler.has_next()
                self.__conn.send(data, final, stream_id=self.__stream_id)

        response = self.__conn.get_response(self.__stream_id)
        # response.read()
        self.__check_response(response)
        return response

    def __check_response(self, response, msg=None):
        if response.status != 200:
            raise H2Exception(response.status, msg if msg else "fail to request http/2, code:%d" % (response.status))

    def __str__(self) -> str:
        return "H2Stream(id=%s,stream_x_id=%s,x_request_id=%s,x_data_stream_id:%s" % (
            self.__id,
            self.__stream_id,
            self.__x_request_id,
            self.__x_data_stream_id,
        )


class H2Client:
    def __init__(
        self, region, product_key, device_name, device_secret, client_id=None, opt_max_thread_num=4, endpoint=None
    ) -> None:
        _assert_value(region, "region is not empty")
        _assert_value(product_key, "product_key is not empty")
        _assert_value(device_name, "device_name is not empty")

        self.__product_key = product_key
        self.__device_name = device_name
        self.__client_id = client_id
        self.__device_secret = device_secret
        self.__region = region
        self.__endpoint = endpoint
        self.__opt_free_idle_connect = False
        self.__connected = False
        self.__port = _H2_OPT_PORT_DEFAULT
        self.__conn = None
        self.__opt_heart_beat_time = _H2_OPT_HEART_BEAT_TIME_DEFAULT
        self.__conn_lock = threading.RLock()
        self.__lock = threading.RLock()
        self.__stream_list = []
        self.__stream_list_lock = threading.RLock()
        self.__thread_executor = concurrent.futures.ThreadPoolExecutor(max_workers=opt_max_thread_num)
        self.__auth_lock = threading.RLock()
        self.__id = 0
        self.__heart_beat_lock = threading.RLock()
        self.__timer = None

    def get_endpoint(self):
        return self.__endpoint

    def get_actual_endpoint(self):
        return self.__generate_endpoint()

    def __generate_endpoint(self):
        if self.__endpoint:
            return self.__endpoint
        else:
            return self.__product_key + ".iot-as-http2.%s.aliyuncs.com" % (self.__region)

    def open(self):
        with self.__conn_lock:
            if self.__conn:
                logging.info("the client is opened")
                return -1
            return self.__connect()

    def close(self):
        with self.__conn_lock:
            return self.__close_connect()
        self.__close_all_streams()

    def upload_file_async(
        self, local_filename, remote_filename=None, over_write=True, upload_file_sink=None, upload_sink_user_data=None
    ):
        _assert_value(local_filename, "local_filename is required")
        self.__check_file(local_filename)

        file_info = UploadFileInfo(local_filename, remote_filename, over_write)

        future_result = self.__thread_executor.submit(
            self.__post_file_task, file_info, upload_file_sink, upload_sink_user_data
        )
        return H2FileTask(id, file_info, future_result)

    def upload_file_sync(
        self,
        local_filename,
        remote_filename=None,
        over_write=True,
        timeout=None,
        upload_file_sink=None,
        upload_sink_user_data=None,
    ):
        self.__check_file(local_filename)
        f = self.upload_file_async(local_filename, remote_filename, over_write, upload_file_sink, upload_sink_user_data)
        return f.result(timeout)

    def __create_stream_id(self):
        with self.__lock:
            self.__id += 1
            return self.__id

    def new_stream(self):
        return H2Stream(self, self.__create_stream_id())

    def _get_auth_lock(self):
        return self.__auth_lock

    def __crc_equal(self, value1, value2):
        if value1 == value2:
            return True
        return self.__to_unsign(value1) == self.__to_unsign(value2)

    def __to_unsign(self, value):
        return value if value > 0 else (0xFFFFFFFFFFFFFFFF + 1 + value)

    def __check_file(self, path):
        stat_info = os.stat(path)
        if stat_info.st_size >= _H2_MAX_FILE_SIZE:
            raise ValueError("maximum file size exceeded")

    def __post_file_task(self, file_info, sink=None, user_data=None):
        local_filename = file_info.local_filename
        remote_filename = file_info.remote_filename
        over_write = file_info.opt_overwrite
        fs = None
        file_store_id = None
        exception = None
        code = 0
        x_file_upload_id = None

        stream = self.new_stream()
        self.__on_new_stream(stream)
        try:
            logging.info(
                "start to post file, local_filename:%s, remote:%s, over_write:%d"
                % (local_filename, remote_filename, over_write)
            )

            # callback
            if sink:
                sink.on_file_upload_start(stream.get_id(), file_info, user_data)

            # open stream
            header = {"x-file-name": remote_filename, "x-file-overwrite": "1" if over_write else "0"}
            response = stream.open("/c/iot/sys/thing/file/upload", header)
            x_file_upload_id = response.headers["x-file-upload-id"][0]

            # send stream
            header = {"x-file-upload-id": x_file_upload_id}
            fs = FileStreamHandler(local_filename, opt_crc64=True)
            stream.send(header, fs)

            # close stream
            response = stream.close(header)
            remote_crc64 = int(response.headers["x-file-crc64ecma"][0])
            logging.info("crc64, local:%ld, remote:%ld" % (fs.get_crc64(), remote_crc64))
            if not self.__crc_equal(fs.get_crc64(), remote_crc64):
                raise Exception("fail to check crc64, local:%ld, remote:%ld" % (fs.get_crc64(), remote_crc64))
            file_store_id = response.headers["x-file-store-id"][0]
            logging.info(
                "finish uploading file, local_filename:%s, remote:%s, over_write:%d, file_store_id:%s"
                % (local_filename, remote_filename, over_write, file_store_id)
            )

            return UploadFileResult(code, exception, fs.get_read_size(), fs.get_content_length, file_store_id)
        except H2Exception as e:
            logging.error(
                "fail to upload the file, local_filename:%s, remote:%s, over_write:%d, x_file_upload_id:%s, stream:%s, code:%s, error:%s"
                % (local_filename, remote_filename, over_write, x_file_upload_id, stream, e.get_code(), e)
            )
            return UploadFileResult(
                e.get_code(),
                exception,
                (fs.get_read_size() if fs else -1),
                (fs.get_content_length() if fs else -1),
                file_store_id,
            )
        except Exception as e:
            logging.error(
                "fail to upload the file, local_filename:%s, remote:%s, over_write:%d, x_file_upload_id:%s, stream:%s, error:%s"
                % (local_filename, remote_filename, over_write, x_file_upload_id, stream, e)
            )
            return UploadFileResult(
                -1,
                exception,
                (fs.get_read_size() if fs else -1),
                (fs.get_content_length() if fs else -1),
                file_store_id,
            )
            # raise e
        finally:
            self.__on_free_stream(stream)
            if sink:
                result = UploadFileResult(
                    code,
                    exception,
                    (fs.get_read_size() if fs else -1),
                    (fs.get_content_length() if fs else -1),
                    file_store_id,
                )
                sink.on_file_upload_end(stream.get_id(), file_info, result, user_data)

    def __connect(self) -> int:
        with self.__conn_lock:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS)
            h2_endpoint = self.__generate_endpoint()
            logging.debug("http/2 endpoint:%s" % (h2_endpoint))
            self.__conn = hyper.HTTP20Connection(
                h2_endpoint, port=self.__port, force_proto=hyper.tls.NPN_PROTOCOL, ssl_context=ctx
            )
            return 0

    def get_connect(self):
        with self.__conn_lock:
            if self.__conn:
                return self.__conn
            return self.__connect()

    def __fill_auth_header(self, header):
        client_id = self.__client_id or self.__device_name
        timestamp = str(int(time.time() * 1000))
        sign_content = (
            "clientId"
            + client_id
            + "deviceName"
            + self.__device_name
            + "productKey"
            + self.__product_key
            + "timestamp"
            + timestamp
        )
        sign = hmac.new(self.__device_secret.encode("utf-8"), sign_content.encode("utf-8"), hashlib.sha256).hexdigest()
        header["x-auth-param-timestamp"] = timestamp
        header["x-auth-param-signmethod"] = "hmacsha256"
        header["x-auth-param-sign"] = sign
        header["x-auth-param-product-key"] = self.__product_key
        header["x-auth-param-device-name"] = self.__device_name
        header["x-auth-param-client-id"] = client_id
        header["x-auth-name"] = "devicename"
        return header

    def __fill_sdk_header(self, header):
        header["x-sdk-version"] = "1.2.0"
        header["x-sdk-version-name"] = "1.2.0"
        header["x-sdk-platform"] = "python"
        return header

    def get_default_header(self):
        header = {}
        self.__fill_auth_header(header)
        self.__fill_sdk_header(header)
        return header

    def __close_connect(self) -> int:
        with self.__conn_lock:
            if self.__conn:
                self.__conn.close(0)
            return 0

    def __close_all_streams(self) -> None:
        with self.__stream_list_lock:
            self.__stream_list.clear()
            self.__stream_list = None
        self.__stop_heart_beat()

    def __on_new_stream(self, stream) -> None:
        with self.__stream_list_lock:
            self.__stream_list.append(stream)

            if len(self.__stream_list) == 1:
                self.__start_heart_beat()

    def __on_free_stream(self, stream) -> None:
        with self.__stream_list_lock:
            self.__stream_list.remove(stream)

            if len(self.__stream_list) == 0:
                self.__stop_heart_beat()

    def __start_heart_beat(self) -> None:
        logging.debug("start heart_beat")
        self.__schedule_heart_beat()

    def __handle_heart_beat(self) -> None:
        logging.debug("heart...")
        self.__conn.ping(b"PINGPONG")
        self.__schedule_heart_beat()

    def __stop_heart_beat(self) -> None:
        logging.debug("stop heart")
        self.__cancel_heart_beat()

    def __schedule_heart_beat(self) -> None:
        with self.__heart_beat_lock:
            if self.__opt_heart_beat_time and self.__opt_heart_beat_time > 0:
                self.__timer = threading.Timer(self.__opt_heart_beat_time, self.__handle_heart_beat)
                self.__timer.start()

    def __cancel_heart_beat(self) -> None:
        with self.__heart_beat_lock:
            if self.__timer:
                self.__timer.cancel()
                self.__timer = None
