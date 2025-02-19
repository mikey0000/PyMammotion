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

from enum import Enum
import hashlib
import hmac
import json
import logging
import os
import queue
import random
import re
import ssl
import string
import sys
import threading
import time
import urllib.parse
import urllib.request

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

REQUIRED_MAJOR_VERSION = 3
REQUIRED_MINOR_VERSION = 5


# check Python version
def lk_check_python_version(major_version, minor_version) -> None:
    version = sys.version_info
    if version[0] < major_version or (version[0] == major_version and version[1] < minor_version):
        print(
            "WARNING: linkit requires Python %d.%d or higher, and the current version is %s"
            % (major_version, minor_version, sys.version)
        )


lk_check_python_version(REQUIRED_MAJOR_VERSION, REQUIRED_MINOR_VERSION)


class LinkKit:
    TAG_KEY = "attrKey"
    TAG_VALUE = "attrValue"

    class LinkKitState(Enum):
        INITIALIZED = 1
        CONNECTING = 2
        CONNECTED = 3
        DISCONNECTING = 4
        DISCONNECTED = 5
        DESTRUCTING = 6
        DESTRUCTED = 7

    class ErrorCode(Enum):
        SUCCESS = 0
        # 错误码一共三位数，第一位为0表示为mqtt相关的错误码
        NETWORK_DISCONNECTED = -0x001  # 当前mqtt连接断开
        INVALID_TOPIC = -0x002  # 输入的topic为空
        INVALID_QOS = -0x003  # 输入的qos非法
        PAHO_MQTT_ERROR = -0x004  # 底层的mqtt报错
        # 0x100开头的表示为网关相关的错误码
        NULL_SUBDEV_ERR = -0x101  # 输入的子设备信息为空错误
        SUBDEV_NOT_ARRAY_ERR = -0x102  # 输入数据并非数组错误
        ARRAY_LENGTH_ERR = -0x103  # 数组长度错误
        # 0x300开头的表示为动态注册相关的错误码
        DYNREG_AUTH_FAILED = -0x301  # 预注册动态注册认证失败
        DYNREG_AUTH_NWL_FAILED = -0x302  # 免白动态注册认证失败
        # 0x400开头表示为OTA有关的错误
        OTA_INVALID_PARAM = -0x401  # 参数非法
        OTA_DIGEST_MISMATCH = -0x402  # 校验和不通过
        OTA_PUB_FAILED = -0x403  # 上报失败
        OTA_INVALID_SIGN_METHOD = -0x404  # 非法校验方法
        OTA_DOWNLOAD_FAIL = -0x405  # 下载失败
        OTA_INVALID_URL = -0x406  # 无法访问HTTP链接
        OTA_INVALID_PATH = -0x407  # 存储路径打开失败

    class StateError(Exception):
        def __init__(self, err) -> None:
            Exception.__init__(self, err)

    class Shadow:
        def __init__(self) -> None:
            self.__version = None
            self.__timestamp = None
            self.__state = None
            self.__metadata = None
            self.__latest_shadow_lock = threading.Lock()
            self.__latest_received_time = None
            self.__lastest_received_payload = None

        def get_version(self):
            with self.__latest_shadow_lock:
                return self.__version

        def get_metadata(self):
            with self.__latest_shadow_lock:
                return self.__metadata

        def get_state(self):
            with self.__latest_shadow_lock:
                return self.__state

        def set_state(self, state) -> None:
            with self.__latest_shadow_lock:
                self.__state = state

        def set_metadata(self, metadata) -> None:
            with self.__latest_shadow_lock:
                self.__metadata = metadata

        def set_version(self, version) -> None:
            with self.__latest_shadow_lock:
                self.__version = version

        def set_timestamp(self, timestamp) -> None:
            with self.__latest_shadow_lock:
                self.__timestamp = timestamp

        def set_latest_recevied_time(self, timestamp) -> None:
            with self.__latest_shadow_lock:
                self.__latest_received_time = timestamp

        def get_latest_recevied_time(self):
            with self.__latest_shadow_lock:
                return self.__latest_received_time

        def set_latest_recevied_payload(self, payload) -> None:
            with self.__latest_shadow_lock:
                self.__latest_received_payload = payload

        def get_latest_recevied_payload(self):
            with self.__latest_shadow_lock:
                return self.__latest_received_payload

        def to_dict(self):
            return {
                "state": self.__state,
                "metadata": self.__metadata,
                "version": self.__version,
                "timestamp": self.__timestamp,
            }

        def to_json_string(self):
            return json.dumps(self.to_dict())

    class __HandlerTask:
        def __init__(self, logger=None) -> None:
            self.__logger = logger
            if self.__logger is not None:
                self.__logger.info("HandlerTask init enter")
            self.__message_queue = queue.Queue(2000)
            self.__cmd_callback = {}
            self.__started = False
            self.__exited = False
            self.__thread = None

        def register_cmd_callback(self, cmd, callback) -> int:
            if self.__started is False:
                if cmd != "req_exit":
                    self.__cmd_callback[cmd] = callback
                    return 0
                else:
                    return 1
            else:
                return 2

        def post_message(self, cmd, value) -> bool:
            self.__logger.debug("post_message :%r " % cmd)
            if self.__started and self.__exited is False:
                try:
                    self.__message_queue.put((cmd, value), timeout=5)
                except queue.Full as e:
                    self.__logger.error("queue full: %r" % e)
                    return False
                self.__logger.debug("post_message success")
                return True
            self.__logger.debug("post_message fail started:%r,exited:%r" % (self.__started, self.__exited))
            return False

        def start(self) -> int:
            if self.__logger is not None:
                self.__logger.info("HandlerTask start")
            if self.__started is False:
                if self.__logger is not None:
                    self.__logger.info("HandlerTask try start")
                self.__exited = False
                self.__started = True
                self.__message_queue = queue.Queue(2000)
                self.__thread = threading.Thread(target=self.__thread_runnable)
                self.__thread.daemon = True
                self.__thread.start()
                return 0
            return 1

        def stop(self) -> None:
            if self.__started and self.__exited is False:
                self.__exited = True
                self.__message_queue.put(("req_exit", None))

        def wait_stop(self) -> None:
            if self.__started is True:
                self.__thread.join()

        def __thread_runnable(self) -> None:
            if self.__logger is not None:
                self.__logger.debug("thread runnable enter")
            while True:
                cmd, value = self.__message_queue.get()
                self.__logger.debug("thread runnable pop cmd:%r" % cmd)
                if cmd == "req_exit":
                    break
                if self.__cmd_callback[cmd] is not None:
                    try:
                        self.__cmd_callback[cmd](value)
                    except Exception as e:
                        if self.__logger is not None:
                            self.__logger.error("thread runnable raise exception:%s" % e)
            self.__started = False
            if self.__logger is not None:
                self.__logger.debug("thread runnable exit")

    class LoopThread:
        def __init__(self, logger=None) -> None:
            self.__logger = logger
            if logger is not None:
                self.__logger.info("LoopThread init enter")
            self.__callback = None
            self.__thread = None
            self.__started = False
            self.__req_wait = threading.Event()
            if logger is not None:
                self.__logger.info("LoopThread init exit")

        def start(self, callback) -> int:
            if self.__started is True:
                self.__logger.info("LoopThread already ")
                return 1
            else:
                self.__callback = callback
                self.__thread = threading.Thread(target=self.__thread_main)
                self.__thread.daemon = True
                self.__thread.start()
                return 0

        def stop(self) -> None:
            self.__req_wait.wait()
            self.__req_wait.clear()

        def __thread_main(self) -> None:
            self.__started = True
            try:
                if self.__logger is not None:
                    self.__logger.debug("LoopThread thread enter")
                if self.__callback is not None:
                    self.__callback()
                if self.__logger is not None:
                    self.__logger.debug("LoopThread thread exit")
            except Exception as e:
                self.__logger.error("LoopThread thread Exception:" + str(e))
            self.__started = False
            self.__req_wait.set()

    def _on_file_upload_start(self, id, upload_file_info, user_data) -> None:
        if self.__on_file_upload_begin != None:
            self.__on_file_upload_begin(id, upload_file_info, self.__user_data)

    def _on_file_upload_end(self, id, upload_file_info, upload_file_result, user_data) -> None:
        if self.__on_file_upload_end != None:
            self.__on_file_upload_end(id, upload_file_info, upload_file_result, self.__user_data)

    def _on_file_upload_progress(self, id, upload_file_result, upload_file_info, user_data) -> None:
        pass

    class __LinkKitLog:
        def __init__(self) -> None:
            self.__logger = logging.getLogger("linkkit")
            self.__enabled = False

        def enable_logger(self) -> None:
            self.__enabled = True

        def disable_logger(self) -> None:
            self.__enabled = False

        def is_enabled(self):
            return self.__enabled

        def config_logger(self, level) -> None:
            self.__logger.setLevel(level)

        def debug(self, fmt, *args) -> None:
            if self.__enabled:
                self.__logger.debug(fmt, *args)

        def warring(self, fmt, *args) -> None:
            if self.__enabled:
                self.__logger.warning(fmt, *args)

        def info(self, fmt, *args) -> None:
            if self.__enabled:
                self.__logger.info(fmt, *args)

        def error(self, fmt, *args) -> None:
            if self.__enabled:
                self.__logger.error(fmt, *args)

        def critical(self, fmt, *args) -> None:
            if self.__enabled:
                self.__logger.critical(fmt, *args)

    __USER_TOPIC_PREFIX = "/%s/%s/%s"
    __ALIYUN_BROKER_CA_DATA = """
-----BEGIN CERTIFICATE-----
MIIDdTCCAl2gAwIBAgILBAAAAAABFUtaw5QwDQYJKoZIhvcNAQEFBQAwVzELMAkG
A1UEBhMCQkUxGTAXBgNVBAoTEEdsb2JhbFNpZ24gbnYtc2ExEDAOBgNVBAsTB1Jv
b3QgQ0ExGzAZBgNVBAMTEkdsb2JhbFNpZ24gUm9vdCBDQTAeFw05ODA5MDExMjAw
MDBaFw0yODAxMjgxMjAwMDBaMFcxCzAJBgNVBAYTAkJFMRkwFwYDVQQKExBHbG9i
YWxTaWduIG52LXNhMRAwDgYDVQQLEwdSb290IENBMRswGQYDVQQDExJHbG9iYWxT
aWduIFJvb3QgQ0EwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQDaDuaZ
jc6j40+Kfvvxi4Mla+pIH/EqsLmVEQS98GPR4mdmzxzdzxtIK+6NiY6arymAZavp
xy0Sy6scTHAHoT0KMM0VjU/43dSMUBUc71DuxC73/OlS8pF94G3VNTCOXkNz8kHp
1Wrjsok6Vjk4bwY8iGlbKk3Fp1S4bInMm/k8yuX9ifUSPJJ4ltbcdG6TRGHRjcdG
snUOhugZitVtbNV4FpWi6cgKOOvyJBNPc1STE4U6G7weNLWLBYy5d4ux2x8gkasJ
U26Qzns3dLlwR5EiUWMWea6xrkEmCMgZK9FGqkjWZCrXgzT/LCrBbBlDSgeF59N8
9iFo7+ryUp9/k5DPAgMBAAGjQjBAMA4GA1UdDwEB/wQEAwIBBjAPBgNVHRMBAf8E
BTADAQH/MB0GA1UdDgQWBBRge2YaRQ2XyolQL30EzTSo//z9SzANBgkqhkiG9w0B
AQUFAAOCAQEA1nPnfE920I2/7LqivjTFKDK1fPxsnCwrvQmeU79rXqoRSLblCKOz
yj1hTdNGCbM+w6DjY1Ub8rrvrTnhQ7k4o+YviiY776BQVvnGCv04zcQLcFGUl5gE
38NflNUVyRRBnMRddWQVDf9VMOyGj/8N7yy5Y0b2qvzfvGn9LhJIZJrglfCm7ymP
AbEVtQwdpf5pLGkkeB6zpxxxYu7KyJesF12KwvhHhm4qxFYxldBniYUr+WymXUad
DKqC5JlR3XC321Y9YeRq4VzW9v493kHMB65jUr9TU/Qr6cf9tveCX4XSQRjbgbME
HMUfpIBvFSDJ3gyICh3WZlXi/EjJKSZp4A==
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIID3zCCAsegAwIBAgISfiX6mTa5RMUTGSC3rQhnestIMA0GCSqGSIb3DQEBCwUA
MHcxCzAJBgNVBAYTAkNOMREwDwYDVQQIDAhaaGVqaWFuZzERMA8GA1UEBwwISGFu
Z3pob3UxEzARBgNVBAoMCkFsaXl1biBJb1QxEDAOBgNVBAsMB1Jvb3QgQ0ExGzAZ
BgNVBAMMEkFsaXl1biBJb1QgUm9vdCBDQTAgFw0yMzA3MDQwNjM2NThaGA8yMDUz
MDcwNDA2MzY1OFowdzELMAkGA1UEBhMCQ04xETAPBgNVBAgMCFpoZWppYW5nMREw
DwYDVQQHDAhIYW5nemhvdTETMBEGA1UECgwKQWxpeXVuIElvVDEQMA4GA1UECwwH
Um9vdCBDQTEbMBkGA1UEAwwSQWxpeXVuIElvVCBSb290IENBMIIBIjANBgkqhkiG
9w0BAQEFAAOCAQ8AMIIBCgKCAQEAoK//6vc2oXhnvJD7BVhj6grj7PMlN2N4iNH4
GBmLmMdkF1z9eQLjksYc4Zid/FX67ypWFtdycOei5ec0X00m53Gvy4zLGBo2uKgi
T9IxMudmt95bORZbaph4VK82gPNU4ewbiI1q2loRZEHRdyPORTPpvNLHu8DrYBnY
Vg5feEYLLyhxg5M1UTrT/30RggHpaa0BYIPxwsKyylQ1OskOsyZQeOyPe8t8r2D4
RBpUGc5ix4j537HYTKSyK3Hv57R7w1NzKtXoOioDOm+YySsz9sTLFajZkUcQci4X
aedyEeguDLAIUKiYicJhRCZWljVlZActorTgjCY4zRajodThrQIDAQABo2MwYTAO
BgNVHQ8BAf8EBAMCAQYwDwYDVR0TAQH/BAUwAwEB/zAdBgNVHQ4EFgQUkWHoKi2h
DlS1/rYpcT/Ue+aKhP8wHwYDVR0jBBgwFoAUkWHoKi2hDlS1/rYpcT/Ue+aKhP8w
DQYJKoZIhvcNAQELBQADggEBADrrLcBY7gDXN8/0KHvPbGwMrEAJcnF9z4MBxRvt
rEoRxhlvRZzPi7w/868xbipwwnksZsn0QNIiAZ6XzbwvIFG01ONJET+OzDy6ZqUb
YmJI09EOe9/Hst8Fac2D14Oyw0+6KTqZW7WWrP2TAgv8/Uox2S05pCWNfJpRZxOv
Lr4DZmnXBJCMNMY/X7xpcjylq+uCj118PBobfH9Oo+iAJ4YyjOLmX3bflKIn1Oat
vdJBtXCj3phpfuf56VwKxoxEVR818GqPAHnz9oVvye4sQqBp/2ynrKFxZKUaJtk0
7UeVbtecwnQTrlcpWM7ACQC0OO0M9+uNjpKIbksv1s11xu0=
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIIFgzCCA2ugAwIBAgIORea7A4Mzw4VlSOb/RVEwDQYJKoZIhvcNAQEMBQAwTDE
gMB4GA1UECxMXR2xvYmFsU2lnbiBSb290IENBIC0gUjYxEzARBgNVBAoTCkdsb2
JhbFNpZ24xEzARBgNVBAMTCkdsb2JhbFNpZ24wHhcNMTQxMjEwMDAwMDAwWhcNM
zQxMjEwMDAwMDAwWjBMMSAwHgYDVQQLExdHbG9iYWxTaWduIFJvb3QgQ0EgLSBS
NjETMBEGA1UEChMKR2xvYmFsU2lnbjETMBEGA1UEAxMKR2xvYmFsU2lnbjCCAiI
wDQYJKoZIhvcNAQEBBQADggIPADCCAgoCggIBAJUH6HPKZvnsFMp7PPcNCPG0RQ
ssgrRIxutbPK6DuEGSMxSkb3/pKszGsIhrxbaJ0cay/xTOURQh7ErdG1rG1ofuT
ToVBu1kZguSgMpE3nOUTvOniX9PeGMIyBJQbUJmL025eShNUhqKGoC3GYEOfsSK
vGRMIRxDaNc9PIrFsmbVkJq3MQbFvuJtMgamHvm566qjuL++gmNQ0PAYid/kD3n
16qIfKtJwLnvnvJO7bVPiSHyMEAc4/2ayd2F+4OqMPKq0pPbzlUoSB239jLKJz9
CgYXfIWHSw1CM69106yqLbnQneXUQtkPGBzVeS+n68UARjNN9rkxi+azayOeSsJ
Da38O+2HBNXk7besvjihbdzorg1qkXy4J02oW9UivFyVm4uiMVRQkQVlO6jxTiW
m05OWgtH8wY2SXcwvHE35absIQh1/OZhFj931dmRl4QKbNQCTXTAFO39OfuD8l4
UoQSwC+n+7o/hbguyCLNhZglqsQY6ZZZZwPA1/cnaKI0aEYdwgQqomnUdnjqGBQ
Ce24DWJfncBZ4nWUx2OVvq+aWh2IMP0f/fMBH5hc8zSPXKbWQULHpYT9NLCEnFl
WQaYw55PfWzjMpYrZxCRXluDocZXFSxZba/jJvcE+kNb7gu3GduyYsRtYQUigAZ
cIN5kZeR1BonvzceMgfYFGM8KEyvAgMBAAGjYzBhMA4GA1UdDwEB/wQEAwIBBjA
PBgNVHRMBAf8EBTADAQH/MB0GA1UdDgQWBBSubAWjkxPioufi1xzWx/B/yGdToD
AfBgNVHSMEGDAWgBSubAWjkxPioufi1xzWx/B/yGdToDANBgkqhkiG9w0BAQwFA
AOCAgEAgyXt6NH9lVLNnsAEoJFp5lzQhN7craJP6Ed41mWYqVuoPId8AorRbrcW
c+ZfwFSY1XS+wc3iEZGtIxg93eFyRJa0lV7Ae46ZeBZDE1ZXs6KzO7V33EByrKP
rmzU+sQghoefEQzd5Mr6155wsTLxDKZmOMNOsIeDjHfrYBzN2VAAiKrlNIC5waN
rlU/yDXNOd8v9EDERm8tLjvUYAGm0CuiVdjaExUd1URhxN25mW7xocBFymFe944
Hn+Xds+qkxV/ZoVqW/hpvvfcDDpw+5CRu3CkwWJ+n1jez/QcYF8AOiYrg54NMMl
+68KnyBr3TsTjxKM4kEaSHpzoHdpx7Zcf4LIHv5YGygrqGytXm3ABdJ7t+uA/iU
3/gKbaKxCXcPu9czc8FB10jZpnOZ7BN9uBmm23goJSFmH63sUYHpkqmlD75HHTO
wY3WzvUy2MmeFe8nI+z1TIvWfspA9MRf/TuTAjB0yPEL+GltmZWrSZVxykzLsVi
VO6LAUP5MSeGbEYNNVMnbrt9x+vJJUEeKgDu+6B5dpffItKoZB0JaezPkvILFa9
x8jvOOJckvB595yEunQtYQEgfn7R8k8HWV+LLUNS60YMlOH1Zkd5d9VUWx+tJDf
LRVpOoERIyNiwmcUVhAn21klJwGW45hpxbqCo8YLoRT5s1gLXCmeDBVrJpBA=
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIICCzCCAZGgAwIBAgISEdK7ujNu1LzmJGjFDYQdmOhDMAoGCCqGSM49BAMDME
YxCzAJBgNVBAYTAkJFMRkwFwYDVQQKExBHbG9iYWxTaWduIG52LXNhMRwwGgYD
VQQDExNHbG9iYWxTaWduIFJvb3QgRTQ2MB4XDTE5MDMyMDAwMDAwMFoXDTQ2MD
MyMDAwMDAwMFowRjELMAkGA1UEBhMCQkUxGTAXBgNVBAoTEEdsb2JhbFNpZ24g
bnYtc2ExHDAaBgNVBAMTE0dsb2JhbFNpZ24gUm9vdCBFNDYwdjAQBgcqhkjOPQ
IBBgUrgQQAIgNiAAScDrHPt+ieUnd1NPqlRqetMhkytAepJ8qUuwzSChDH2omw
lwxwEwkBjtjqR+q+soArzfwoDdusvKSGN+1wCAB16pMLey5SnCNoIwZD7JIvU4
Tb+0cUB+hflGddyXqBPCCjQjBAMA4GA1UdDwEB/wQEAwIBhjAPBgNVHRMBAf8E
BTADAQH/MB0GA1UdDgQWBBQxCpCPtsad0kRLgLWi5h+xEk8blTAKBggqhkjOPQ
QDAwNoADBlAjEA31SQ7Zvvi5QCkxeCmb6zniz2C5GMn0oUsfZkvLtoURMMA/cV
i4RguYv/Uo7njLwcAjA8+RHUjE7AwWHCFUyqqx0LMV87HOIAl0Qx5v5zli/alt
P+CAezNIm8BZ/3Hobui3A=
-----END CERTIFICATE-----
-----BEGIN CERTIFICATE-----
MIIFWjCCA0KgAwIBAgISEdK7udcjGJ5AXwqdLdDfJWfRMA0GCSqGSIb3DQEBDAU
AMEYxCzAJBgNVBAYTAkJFMRkwFwYDVQQKExBHbG9iYWxTaWduIG52LXNhMRwwGg
YDVQQDExNHbG9iYWxTaWduIFJvb3QgUjQ2MB4XDTE5MDMyMDAwMDAwMFoXDTQ2M
DMyMDAwMDAwMFowRjELMAkGA1UEBhMCQkUxGTAXBgNVBAoTEEdsb2JhbFNpZ24g
bnYtc2ExHDAaBgNVBAMTE0dsb2JhbFNpZ24gUm9vdCBSNDYwggIiMA0GCSqGSIb
3DQEBAQUAA4ICDwAwggIKAoICAQCsrHQy6LNl5brtQyYdpokNRbopiLKkHWPd08
EsCVeJOaFV6Wc0dwxu5FUdUiXSE2te4R2pt32JMl8Nnp8semNgQB+msLZ4j5lUl
ghYruQGvGIFAha/r6gjA7aUD7xubMLL1aa7DOn2wQL7Id5m3RerdELv8HQvJfTq
a1VbkNud316HCkD7rRlr+/fKYIje2sGP1q7Vf9Q8g+7XFkyDRTNrJ9CG0Bwta/O
rffGFqfUo0q3v84RLHIf8E6M6cqJaESvWJ3En7YEtbWaBkoe0G1h6zD8K+kZPT
Xhc+CtI4wSEy132tGqzZfxCnlEmIyDLPRT5ge1lFgBPGmSXZgjPjHvjK8Cd+RTy
G/FWaha/LIWFzXg4mutCagI0GIMXTpRW+LaCtfOW3T3zvn8gdz57GSNrLNRyc0N
XfeD412lPFzYE+cCQYDdF3uYM2HSNrpyibXRdQr4G9dlkbgIQrImwTDsHTUB+JM
WKmIJ5jqSngiCNI/onccnfxkF0oE32kRbcRoxfKWMxWXEM2G/CtjJ9++ZdU6Z+F
fy7dXxd7Pj2Fxzsx2sZy/N78CsHpdlseVR2bJ0cpm4O6XkMqCNqo98bMDGfsVR7
/mrLZqrcZdCinkqaByFrgY/bxFn63iLABJzjqls2k+g9vXqhnQt2sQvHnf3PmKg
Gwvgqo6GDoLclcqUC4wIDAQABo0IwQDAOBgNVHQ8BAf8EBAMCAYYwDwYDVR0TAQ
H/BAUwAwEB/zAdBgNVHQ4EFgQUA1yrc4GHqMywptWU4jaWSf8FmSwwDQYJKoZIh
vcNAQEMBQADggIBAHx47PYCLLtbfpIrXTncvtgdokIzTfnvpCo7RGkerNlFo048
p9gkUbJUHJNOxO97k4VgJuoJSOD1u8fpaNK7ajFxzHmuEajwmf3lH7wvqMxX63b
EIaZHU1VNaL8FpO7XJqti2kM3S+LGteWygxk6x9PbTZ4IevPuzz5i+6zoYMzRx6
Fcg0XERczzF2sUyQQCPtIkpnnpHs6i58FZFZ8d4kuaPp92CC1r2LpXFNqD6v6MV
enQTqnMdzGxRBF6XLE+0xRFFRhiJBPSy03OXIPBNvIQtQ6IbbjhVp+J3pZmOUdk
LG5NrmJ7v2B0GbhWrJKsFjLtrWhV/pi60zTe9Mlhww6G9kuEYO4Ne7UyWHmRVSy
BQ7N0H3qqJZ4d16GLuc1CLgSkZoNNiTW2bKg2SnkheCLQQrzRQDGQob4Ez8pn7f
XwgNNgyYMqIgXQBztSvwyeqiv5u+YfjyW6hY0XHgL+XVAEV8/+LbzvXMAaq7afJ
Mbfc2hIkCwU9D9SGuTSyxTDYWnP4vkYxboznxSjBF25cfe1lNj2M8FawTSLfJvd
kzrnE6JwYZ+vj+vYxXX4M2bUdGc6N3ec592kD3ZDZopD8p/7DEJ4Y9HiD2971KE
9dJeFt0g5QdYg/NA6s/rob8SKunE3vouXsXgxT7PntgMTzlSdriVZzH81Xwj3QE
UxeCp6
-----END CERTIFICATE-----
    """

    def __init__(
        self,
        host_name,
        product_key,
        device_name,
        device_secret,
        auth_type=None,
        username=None,
        client_id=None,
        password=None,
        instance_id=None,
        product_secret=None,
        user_data=None,
    ) -> None:
        # logging configs
        self.__just_for_pycharm_autocomplete = False

        def __str_is_empty(value) -> bool:
            if value is None or value == "":
                return True
            else:
                return False

        # param check
        if __str_is_empty(host_name):
            raise ValueError("host_name wrong")
        if __str_is_empty(product_key):
            raise ValueError("product key wrong")
        if __str_is_empty(device_name):
            raise ValueError("device name wrong")
        if __str_is_empty(device_secret) and __str_is_empty(product_secret):
            lack_other_auth_info = __str_is_empty(username) or __str_is_empty(client_id) or __str_is_empty(password)
            if lack_other_auth_info:
                raise ValueError("device secret & product secret are both empty")

        self.__link_log = LinkKit.__LinkKitLog()
        self.__PahoLog = logging.getLogger("Paho")
        self.__PahoLog.setLevel(logging.DEBUG)

        # config internal property
        self.__host_name = host_name
        self.__product_key = product_key
        self.__device_name = device_name
        self.__device_secret = device_secret
        self.__product_secret = product_secret
        self.__user_data = user_data
        self.__device_interface_info = ""
        self.__device_mac = None
        self.__cellular_IMEI = None
        self.__cellular_ICCID = None
        self.__cellular_IMSI = None
        self.__cellular_MSISDN = None
        self.__mqtt_client = None
        self.__sdk_version = "1.2.13"
        self.__sdk_program_language = "Python"
        self.__endpoint = None
        self.__check_hostname = True
        self.__instance_id = instance_id

        self.__mqtt_port = 8883
        self.__mqtt_protocol = "MQTTv311"
        self.__mqtt_transport = "TCP"
        self.__mqtt_secure = "TLS"
        self.__mqtt_keep_alive = 60
        self.__mqtt_clean_session = True
        self.__mqtt_max_inflight_message = 20
        self.__mqtt_max_queued_message = 40
        self.__mqtt_auto_reconnect_min_sec = 1
        self.__mqtt_auto_reconnect_max_sec = 60
        self.__mqtt_auto_reconnect_sec = 0
        self.__mqtt_request_timeout = 10
        # 动态注册(免预注册)的flag
        self.__dynamic_register_nwl_flag = 0
        # 动态注册(预注册)的flag
        self.__dynamic_register_flag = 0
        self.__linkkit_state = LinkKit.LinkKitState.INITIALIZED
        self.__aliyun_broker_ca_data = self.__ALIYUN_BROKER_CA_DATA
        self.__force_reconnect = False

        self.__latest_shadow = LinkKit.Shadow()
        self.__auth_type = auth_type
        self.__username = username
        self.__client_id = client_id
        self.__password = password

        # aliyun IoT callbacks
        self.__on_device_dynamic_register = None

        # mqtt callbacks
        self.__on_connect = None
        self.__on_disconnect = None
        self.__on_publish_topic = None
        self.__on_subscribe_topic = None
        self.__on_unsubscribe_topic = None
        self.__on_topic_message = None

        self.__on_topic_rrpc_message = None
        self.__on_subscribe_rrpc_topic = None
        self.__on_unsubscribe_rrpc_topic = None

        # thing model callbacks
        self.__on_thing_create = None
        self.__on_thing_enable = None
        self.__on_thing_disable = None
        self.__on_thing_raw_data_arrived = None
        self.__on_thing_raw_data_post = None
        self.__on_thing_call_service = None
        self.__on_thing_prop_changed = None
        self.__on_thing_event_post = None
        self.__on_thing_prop_post = None
        self.__on_thing_shadow_get = None
        self.__on_thing_device_info_update = None
        self.__on_thing_device_info_delete = None

        self.__on_file_upload_begin = None
        self.__on_file_upload_end = None

        self.__user_topics = {}
        self.__user_topics_subscribe_request = {}
        self.__user_topics_unsubscribe_request = {}
        self.__user_topics_request_lock = threading.Lock()
        self.__user_topics_unsubscribe_request_lock = threading.Lock()

        self.__user_rrpc_topics = {}
        self.__user_rrpc_topics_lock = threading.RLock()
        self.__user_rrpc_topics_subscribe_request = {}
        self.__user_rrpc_topics_unsubscribe_request = {}
        self.__user_rrpc_topics_subscribe_request_lock = threading.RLock()
        self.__user_rrpc_topics_unsubscribe_request_lock = threading.RLock()
        self.__user_rrpc_request_ids = []
        self.__user_rrpc_request_id_index_map = {}
        self.__user_rrpc_request_ids_lock = threading.RLock()
        self.__user_rrpc_request_max_len = 100

        # things topic - Alink
        self.__thing_topic_prop_post = "/sys/%s/%s/thing/event/property/post" % (self.__product_key, self.__device_name)
        self.__thing_topic_prop_post_reply = self.__thing_topic_prop_post + "_reply"
        self.__thing_topic_prop_set = "/sys/%s/%s/thing/service/property/set" % (self.__product_key, self.__device_name)
        self.__thing_topic_prop_set_reply = self.__thing_topic_prop_set + "_reply"
        self.__thing_topic_prop_get = "/sys/%s/%s/thing/service/property/get" % (self.__product_key, self.__device_name)
        self.__thing_topic_event_post_pattern = "/sys/%s/%s/thing/event/%s/post"
        self.__gateway_topic_add_subdev_topo = "/sys/%s/%s/thing/topo/add" % (self.__product_key, self.__device_name)
        self.__gateway_topic_add_subdev_topo_reply = self.__gateway_topic_add_subdev_topo + "_reply"

        self.__gateway_topic_delete_subdev_topo = "/sys/%s/%s/thing/topo/delete" % (
            self.__product_key,
            self.__device_name,
        )
        self.__gateway_topic_delete_subdev_topo_reply = self.__gateway_topic_delete_subdev_topo + "_reply"

        self.__gateway_topic_login_subdev = "/ext/session/%s/%s/combine/batch_login" % (
            self.__product_key,
            self.__device_name,
        )
        self.__gateway_topic_login_subdev_reply = self.__gateway_topic_login_subdev + "_reply"

        self.__gateway_topic_logout_subdev = "/ext/session/%s/%s/combine/batch_logout" % (
            self.__product_key,
            self.__device_name,
        )
        self.__gateway_topic_logout_subdev_reply = self.__gateway_topic_logout_subdev + "_reply"

        self.__gateway_topic_register_subdev = "/sys/%s/%s/thing/sub/register" % (
            self.__product_key,
            self.__device_name,
        )
        self.__gateway_topic_register_subdev_reply = self.__gateway_topic_register_subdev + "_reply"

        self.__gateway_topic_product_register_subdev = "/sys/%s/%s/thing/proxy/provisioning/product_register" % (
            self.__product_key,
            self.__device_name,
        )
        self.__gateway_topic_product_register_subdev_reply = self.__gateway_topic_product_register_subdev + "_reply"

        self.__gateway_topic_topo_change = "/sys/%s/%s/thing/topo/change" % (self.__product_key, self.__device_name)
        self.__dynamic_register_nwl_topic = "/ext/regnwl"
        self.__dynamic_register_topic = "/ext/register"

        self.__ota_report_version_topic = "/ota/device/inform/%s/%s" % (self.__product_key, self.__device_name)
        self.__ota_push_topic = "/ota/device/upgrade/%s/%s" % (self.__product_key, self.__device_name)
        self.__ota_pull_topic = "/sys/%s/%s/thing/ota/firmware/get" % (self.__product_key, self.__device_name)
        self.__ota_pull_reply_topic = "/sys/%s/%s/thing/ota/firmware/get_reply" % (
            self.__product_key,
            self.__device_name,
        )

        self.__thing_prop_post_mid = {}
        self.__thing_prop_post_mid_lock = threading.Lock()
        self.__thing_prop_set_reply_mid = {}
        self.__thing_prop_set_reply_mid_lock = threading.Lock()
        self.__gateway_add_subdev_topo_mid = {}
        self.__gateway_add_subdev_topo_mid_lock = threading.Lock()
        self.__gateway_delete_subdev_topo_mid = {}
        self.__gateway_delete_subdev_topo_mid_lock = threading.Lock()
        # event:post topic
        self.__thing_topic_event_post = {}
        self.__thing_topic_event_post_reply = set()
        self.__thing_events = set()
        self.__thing_request_id_max = 1000000
        self.__thing_request_value = 0
        self.__thing_request_id = {}
        self.__thing_request_id_lock = threading.Lock()
        self.__thing_event_post_mid = {}
        self.__thing_event_post_mid_lock = threading.Lock()

        self.__thing_topic_shadow_get = "/shadow/get/%s/%s" % (self.__product_key, self.__device_name)
        self.__thing_topic_shadow_update = "/shadow/update/%s/%s" % (self.__product_key, self.__device_name)
        self.__thing_shadow_mid = {}
        self.__thing_shadow_mid_lock = threading.Lock()

        # service topic
        self.__thing_topic_service_pattern = "/sys/%s/%s/thing/service/%s"
        self.__thing_topic_services = set()
        self.__thing_topic_services_reply = set()
        self.__thing_services = set()
        self.__thing_answer_service_mid = {}
        self.__thing_answer_service_mid_lock = threading.Lock()

        # thing topic - raw
        self.__thing_topic_raw_up = "/sys/%s/%s/thing/model/up_raw" % (self.__product_key, self.__device_name)
        self.__thing_topic_raw_up_reply = self.__thing_topic_raw_up + "_reply"
        self.__thing_topic_raw_down = "/sys/%s/%s/thing/model/down_raw" % (self.__product_key, self.__device_name)
        self.__thing_topic_raw_down_reply = self.__thing_topic_raw_down + "_reply"
        self.__thing_raw_up_mid = {}
        self.__thing_raw_up_mid_lock = threading.Lock()
        self.__thing_raw_down_reply_mid = {}
        self.__thing_raw_down_reply_mid_lock = threading.Lock()

        # thing topic - device_info
        self.__thing_topic_update_device_info_up = "/sys/%s/%s/thing/deviceinfo/update" % (
            self.__product_key,
            self.__device_name,
        )
        self.__thing_topic_update_device_info_reply = self.__thing_topic_update_device_info_up + "_reply"
        self.__thing_topic_delete_device_info_up = "/sys/%s/%s/thing/deviceinfo/delete" % (
            self.__product_key,
            self.__device_name,
        )
        self.__thing_topic_delete_device_info_reply = self.__thing_topic_delete_device_info_up + "_reply"
        self.__thing_update_device_info_up_mid = {}
        self.__thing_update_device_info_up_mid_lock = threading.Lock()
        self.__thing_delete_device_info_up_mid = {}
        self.__thing_delete_device_info_up_mid_lock = threading.Lock()

        # properties
        self.__thing_properties_set = set()
        self.__thing_properties_get = set()
        self.__thing_properties_post = set()

        # thing setup state
        self.__thing_setup_state = False
        self.__thing_raw_only = False
        self.__thing_enable_state = False
        self.__on_gateway_add_subdev_topo_reply = None
        self.__on_gateway_delete_subdev_topo_reply = None
        self.__on_gateway_login_subdev_reply = None
        self.__on_gateway_logout_subdev_reply = None
        self.__on_gateway_register_subdev_reply = None
        self.__on_gateway_product_register_subdev_reply = None
        self.__on_gateway_topo_change = None
        self.__on_device_dynamic_register_nwl_reply = None
        self.__on_ota_message_arrived = None

        if self.__just_for_pycharm_autocomplete:
            self.__mqtt_client = mqtt.Client(CallbackAPIVersion.VERSION1)

        # device interface info
        self.__device_info_topic = "/sys/%s/%s/thing/deviceinfo/update" % (self.__product_key, self.__device_name)
        self.__device_info_topic_reply = self.__device_info_topic + "_reply"
        self.__device_info_mid_lock = threading.Lock()
        self.__device_info_mid = {}

        # connect_async
        self.__connect_async_req = False
        self.__worker_loop_exit_req = False
        self.__worker_loop_runing_state = False
        self.__worker_loop_exit_req_lock = threading.Lock()

        # loop thread
        self.__loop_thread = LinkKit.LoopThread(self.__link_log)

        # HandlerTask
        self.__handler_task = LinkKit.__HandlerTask(self.__link_log)
        self.__handler_task_cmd_on_connect = "on_connect"
        self.__handler_task_cmd_on_disconnect = "on_disconnect"
        self.__handler_task_cmd_on_message = "on_message"
        self.__handler_task_cmd_on_publish = "on_publish"
        self.__handler_task_cmd_on_subscribe = "on_subscribe"
        self.__handler_task_cmd_on_unsubscribe = "on_unsubscribe"
        self.__handler_task.register_cmd_callback(
            self.__handler_task_cmd_on_connect, self.__handler_task_on_connect_callback
        )
        self.__handler_task.register_cmd_callback(
            self.__handler_task_cmd_on_disconnect, self.__handler_task_on_disconnect_callback
        )
        self.__handler_task.register_cmd_callback(
            self.__handler_task_cmd_on_message, self.__handler_task_on_message_callback
        )
        self.__handler_task.register_cmd_callback(
            self.__handler_task_cmd_on_publish, self.__handler_task_on_publish_callback
        )
        self.__handler_task.register_cmd_callback(
            self.__handler_task_cmd_on_subscribe, self.__handler_task_on_subscribe_callback
        )
        self.__handler_task.register_cmd_callback(
            self.__handler_task_cmd_on_unsubscribe, self.__handler_task_on_unsubscribe_callback
        )
        self.__handler_task.start()

    @property
    def on_device_dynamic_register(self):
        return None

    @on_device_dynamic_register.setter
    def on_device_dynamic_register(self, value) -> None:
        self.__on_device_dynamic_register = value

    @property
    def on_connect(self):
        return self.__on_connect

    @on_connect.setter
    def on_connect(self, value) -> None:
        self.__on_connect = value

    @property
    def on_disconnect(self):
        return self.__on_disconnect

    @on_disconnect.setter
    def on_disconnect(self, value) -> None:
        self.__on_disconnect = value

    @property
    def on_publish_topic(self):
        return None

    @on_publish_topic.setter
    def on_publish_topic(self, value) -> None:
        self.__on_publish_topic = value

    @property
    def on_subscribe_topic(self):
        return None

    @on_subscribe_topic.setter
    def on_subscribe_topic(self, value) -> None:
        self.__on_subscribe_topic = value

    @property
    def on_unsubscribe_topic(self):
        return None

    @on_unsubscribe_topic.setter
    def on_unsubscribe_topic(self, value) -> None:
        self.__on_unsubscribe_topic = value

    @property
    def on_topic_message(self):
        return None

    @on_topic_message.setter
    def on_topic_message(self, value) -> None:
        self.__on_topic_message = value

    @property
    def on_topic_rrpc_message(self):
        return None

    @on_topic_rrpc_message.setter
    def on_topic_rrpc_message(self, value) -> None:
        self.__on_topic_rrpc_message = value

    @property
    def on_thing_create(self):
        return None

    @on_thing_create.setter
    def on_thing_create(self, value) -> None:
        self.__on_thing_create = value

    @property
    def on_thing_enable(self):
        return None

    @on_thing_enable.setter
    def on_thing_enable(self, value) -> None:
        self.__on_thing_enable = value

    @property
    def on_thing_disable(self):
        return None

    @on_thing_disable.setter
    def on_thing_disable(self, value) -> None:
        self.__on_thing_disable = value

    @property
    def on_thing_raw_data_arrived(self):
        return None

    @on_thing_raw_data_arrived.setter
    def on_thing_raw_data_arrived(self, value) -> None:
        self.__on_thing_raw_data_arrived = value

    @property
    def on_thing_raw_data_post(self):
        return self.__on_thing_raw_data_post

    @property
    def on_thing_device_info_update(self):
        return self.__on_thing_device_info_update

    @on_thing_device_info_update.setter
    def on_thing_device_info_update(self, value) -> None:
        self.__on_thing_device_info_update = value

    @property
    def on_thing_device_info_delete(self):
        return self.__on_thing_device_info_delete

    @on_thing_device_info_delete.setter
    def on_thing_device_info_delete(self, value) -> None:
        self.__on_thing_device_info_delete = value

    @on_thing_raw_data_post.setter
    def on_thing_raw_data_post(self, value) -> None:
        self.__on_thing_raw_data_post = value

    @property
    def on_thing_call_service(self):
        return None

    @on_thing_call_service.setter
    def on_thing_call_service(self, value) -> None:
        self.__on_thing_call_service = value

    @property
    def on_thing_prop_changed(self):
        return None

    @on_thing_prop_changed.setter
    def on_thing_prop_changed(self, value) -> None:
        self.__on_thing_prop_changed = value

    @property
    def on_thing_event_post(self):
        return self.__on_thing_event_post

    @on_thing_event_post.setter
    def on_thing_event_post(self, value) -> None:
        self.__on_thing_event_post = value

    @property
    def on_thing_prop_post(self):
        return self.__on_thing_prop_post

    @on_thing_prop_post.setter
    def on_thing_prop_post(self, value) -> None:
        self.__on_thing_prop_post = value

    @property
    def on_thing_shadow_get(self):
        return self.__on_thing_shadow_get

    @on_thing_shadow_get.setter
    def on_thing_shadow_get(self, value) -> None:
        self.__on_thing_shadow_get = value

    @property
    def on_file_upload_begin(self):
        return self.__on_file_upload_begin

    @on_file_upload_begin.setter
    def on_file_upload_begin(self, value) -> None:
        self.__on_file_upload_begin = value

    @property
    def on_file_upload_end(self):
        return self.__on_file_upload_end

    @on_file_upload_end.setter
    def on_file_upload_end(self, value) -> None:
        self.__on_file_upload_end = value

    @property
    def on_gateway_add_subdev_topo_reply(self):
        return None

    @on_gateway_add_subdev_topo_reply.setter
    def on_gateway_add_subdev_topo_reply(self, value) -> None:
        self.__on_gateway_add_subdev_topo_reply = value

    @property
    def on_gateway_delete_subdev_topo_reply(self):
        return None

    @on_gateway_delete_subdev_topo_reply.setter
    def on_gateway_delete_subdev_topo_reply(self, value) -> None:
        self.__on_gateway_delete_subdev_topo_reply = value

    @property
    def on_gateway_login_subdev_reply(self):
        return None

    @on_gateway_login_subdev_reply.setter
    def on_gateway_login_subdev_reply(self, value) -> None:
        self.__on_gateway_login_subdev_reply = value

    @property
    def on_gateway_logout_subdev_reply(self):
        return None

    @on_gateway_logout_subdev_reply.setter
    def on_gateway_logout_subdev_reply(self, value) -> None:
        self.__on_gateway_logout_subdev_reply = value

    @property
    def on_gateway_register_subdev_reply(self):
        return None

    @on_gateway_register_subdev_reply.setter
    def on_gateway_register_subdev_reply(self, value) -> None:
        self.__on_gateway_register_subdev_reply = value

    @property
    def on_gateway_product_register_subdev_reply(self):
        return None

    @on_gateway_product_register_subdev_reply.setter
    def on_gateway_product_register_subdev_reply(self, value) -> None:
        self.__on_gateway_product_register_subdev_reply = value

    @property
    def on_device_dynamic_register_nwl_reply(self):
        return None

    @on_device_dynamic_register_nwl_reply.setter
    def on_device_dynamic_register_nwl_reply(self, value) -> None:
        self.__on_device_dynamic_register_nwl_reply = value

    @property
    def on_ota_message_arrived(self):
        return None

    @on_ota_message_arrived.setter
    def on_ota_message_arrived(self, value) -> None:
        self.__on_ota_message_arrived = value

    @property
    def on_gateway_topo_change(self):
        return None

    @on_gateway_topo_change.setter
    def on_gateway_topo_change(self, value) -> None:
        self.__on_gateway_topo_change = value

    def enable_logger(self, level) -> None:
        self.__link_log.config_logger(level)
        self.__link_log.enable_logger()
        if self.__mqtt_client is not None:
            self.__mqtt_client.enable_logger(self.__PahoLog)
        self.__PahoLog.setLevel(level)

    def disable_logger(self) -> None:
        self.__link_log.disable_logger()
        if self.__mqtt_client is not None:
            self.__mqtt_client.disable_logger()

    def config_logger(self, level) -> None:
        self.__link_log.config_logger(level)
        if self.__mqtt_client is not None:
            self.__PahoLog.setLevel(level)

    def config_http2(self, endpoint=None):
        raise LinkKit.StateError("not supported any more")

    def config_mqtt(
        self,
        port=8883,
        protocol="MQTTv311",
        transport="TCP",
        secure="TLS",
        keep_alive=60,
        clean_session=True,
        max_inflight_message=20,
        max_queued_message=40,
        auto_reconnect_min_sec=1,
        auto_reconnect_max_sec=60,
        cadata=None,
        endpoint=None,
        check_hostname=True,
    ):
        if self.__linkkit_state is not LinkKit.LinkKitState.INITIALIZED:
            raise LinkKit.StateError("not in INITIALIZED state")
        if port < 1 or port > 65535:
            raise ValueError("port wrong")
        if protocol not in ("MQTTv311", "MQTTv31"):
            raise ValueError("protocol wrong")
        if transport != "TCP":
            raise ValueError("transport wrong")
        if secure != "TLS" and secure != "":
            raise ValueError("secure wrong")
        if keep_alive < 30 or keep_alive > 1200:
            raise ValueError("keep_alive range wrong")
        if clean_session is not True and clean_session is not False:
            raise ValueError("clean session wrong")
        if max_queued_message < 0:
            raise ValueError("max_queued_message wrong")
        if max_inflight_message < 0:
            raise ValueError("max_inflight_message wrong")
        if auto_reconnect_min_sec < 1 or auto_reconnect_min_sec > 120 * 60:
            raise ValueError("auto_reconnect_min_sec wrong")
        if auto_reconnect_max_sec < 1 or auto_reconnect_max_sec > 120 * 60:
            raise ValueError("auto_reconnect_max_sec wrong")
        if auto_reconnect_min_sec > auto_reconnect_max_sec:
            raise ValueError("auto_reconnect_max_sec less than auto_reconnect_min_sec")

        self.__link_log.info("config_mqtt enter")
        if self.__linkkit_state == LinkKit.LinkKitState.INITIALIZED:
            if port is not None:
                self.__mqtt_port = port
            if protocol is not None:
                self.__mqtt_protocol = protocol
            if transport is not None:
                self.__mqtt_transport = transport
            if secure is not None:
                self.__mqtt_secure = secure
            if keep_alive is not None:
                self.__mqtt_keep_alive = keep_alive
            if clean_session is not None:
                self.__mqtt_clean_session = clean_session
            if max_inflight_message is not None:
                self.__mqtt_max_inflight_message = max_inflight_message
            if max_queued_message is not None:
                self.__mqtt_max_queued_message = max_queued_message
            if auto_reconnect_min_sec is not None:
                self.__mqtt_auto_reconnect_min_sec = auto_reconnect_min_sec
            if auto_reconnect_max_sec is not None:
                self.__mqtt_auto_reconnect_max_sec = auto_reconnect_max_sec
            if cadata is not None:
                self.__aliyun_broker_ca_data = cadata
            if endpoint is not None:
                self.__endpoint = endpoint
            if check_hostname is not None:
                self.__check_hostname = check_hostname
                if check_hostname == False:
                    self.__link_log.info("skip hostname check")

    def config_device_info(self, interface_info) -> int:
        if self.__linkkit_state is not LinkKit.LinkKitState.INITIALIZED:
            raise LinkKit.StateError("LinkKit object not in INITIALIZED")
        if not isinstance(interface_info, str):
            raise ValueError("interface info must be string")
        if len(interface_info) > 160:
            return 1
        self.__device_interface_info = interface_info
        return 0

    def get_product(self):
        return self.__product_key

    def get_device_name(self):
        return self.__device_name

    def get_endpoint(self):
        return self.__endpoint

    def get_h2_endpoint(self):
        raise LinkKit.StateError("not supported any more")

    def get_actual_endpoint(self):
        return self.__generate_endpoint()

    def get_actual_h2_endpoint(self):
        raise LinkKit.StateError("not supported any more")

    def __load_json(self, payload):
        return json.loads(self.__to_str(payload))

    def __to_str(self, payload):
        if type(payload) is bytes:
            return str(payload, "utf-8")
        else:
            return payload

    def upload_file_sync(self, local_filename, remote_filename=None, over_write=True, timeout=None):
        raise LinkKit.StateError("not supported any more")

    def upload_file_async(self, local_filename, remote_filename=None, over_write=True):
        raise LinkKit.StateError("not supported any more")

    def __upload_device_interface_info(self) -> int:
        request_id = self.__get_thing_request_id()
        payload = {
            "id": request_id,
            "version": "1.0",
            "params": [
                {"domain": "SYSTEM", "attrKey": "SYS_SDK_LANGUAGE", "attrValue": self.__sdk_program_language},
                {"domain": "SYSTEM", "attrKey": "SYS_LP_SDK_VERSION", "attrValue": self.__sdk_version},
                {"domain": "SYSTEM", "attrKey": "SYS_SDK_IF_INFO", "attrValue": self.__device_interface_info},
            ],
            "method": "thing.deviceinfo.update",
        }
        with self.__device_info_mid_lock:
            rc, mid = self.__mqtt_client.publish(self.__device_info_topic, json.dumps(payload), 0)
            if rc == mqtt.MQTT_ERR_SUCCESS:
                self.__device_info_mid[mid] = self.__timestamp()
                return 0
            else:
                return 1

    def destruct(self) -> None:
        if self.__linkkit_state is LinkKit.LinkKitState.DESTRUCTED:
            self.__link_log.info("LinkKit object has already destructed")
            return
        self.__link_log.debug("destruct enter")
        if (
            self.__linkkit_state == LinkKit.LinkKitState.CONNECTED
            or self.__linkkit_state == LinkKit.LinkKitState.CONNECTING
        ):
            self.__linkkit_state = LinkKit.LinkKitState.DESTRUCTING
            if self.__connect_async_req:
                with self.__worker_loop_exit_req_lock:
                    self.__worker_loop_exit_req = True
            if self.__mqtt_client is not None:
                self.__mqtt_client.disconnect()
            self.__handler_task.wait_stop()
        else:
            self.__linkkit_state = LinkKit.LinkKitState.DESTRUCTING
            if self.__connect_async_req:
                with self.__worker_loop_exit_req_lock:
                    self.__worker_loop_exit_req = True
            self.__handler_task.stop()
            self.__handler_task.wait_stop()
            self.__linkkit_state = LinkKit.LinkKitState.DESTRUCTED

    def destroy(self) -> None:
        self.destruct()

    def check_state(self):
        return self.__linkkit_state

    @staticmethod
    def __generate_random_str(randomlength=16):
        """Generate radom string"""
        random_str = ""
        for i in range(randomlength):
            random_str += random.choice(string.digits + string.ascii_letters)
        return random_str

    # 基于HTTPS的一型一密预注册
    def __dynamic_register_device(self):
        pk = self.__product_key
        ps = self.__product_secret
        dn = self.__device_name
        random_str = self.__generate_random_str(15)
        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cadata=self.__aliyun_broker_ca_data)
        sign_content = "deviceName%sproductKey%srandom%s" % (dn, pk, random_str)
        sign = hmac.new(ps.encode("utf-8"), sign_content.encode("utf-8"), hashlib.sha256).hexdigest()
        post_data = {"productKey": pk, "deviceName": dn, "random": random_str, "sign": sign, "signMethod": "hmacsha256"}
        data = urllib.parse.urlencode(post_data)
        data = data.encode("ascii")
        request_url = "https://iot-auth.%s.aliyuncs.com/auth/register/device" % self.__host_name
        with urllib.request.urlopen(request_url, data, context=context) as f:
            reply_data = f.read().decode("utf-8")
            reply_obj = self.__load_json(reply_data)
            if reply_obj["code"] == 200:
                reply_obj_data = reply_obj["data"]
                if reply_obj_data is not None:
                    return 0, reply_obj_data["deviceSecret"]
            else:
                return 1, reply_obj["message"]

    def __config_mqtt_client_internal(self):
        self.__link_log.info("start connect")

        timestamp = str(int(time.time()))
        if self.__mqtt_secure == "TLS":
            securemode = 2
        else:
            securemode = 3
        if self.__device_interface_info:
            sii_option = "sii=%s," % (self.__device_interface_info)
        else:
            sii_option = ""

        # 普通的一机一密认证方式
        if self.__is_valid_str(self.__device_secret):
            client_id = "%s&%s|securemode=%d,signmethod=hmacsha1,ext=1,_ss=1,lan=%s,_v=%s,%stimestamp=%s|" % (
                self.__product_key,
                self.__device_name,
                securemode,
                self.__sdk_program_language,
                self.__sdk_version,
                sii_option,
                timestamp,
            )
            username = self.__device_name + "&" + self.__product_key
            # calc sign
            sign_content = "clientId%sdeviceName%sproductKey%stimestamp%s" % (
                self.__product_key + "&" + self.__device_name,
                self.__device_name,
                self.__product_key,
                timestamp,
            )
            password = hmac.new(
                self.__device_secret.encode("utf-8"), sign_content.encode("utf-8"), hashlib.sha1
            ).hexdigest()
        # 通过username, passwd, cilentid直连接入的方式
        elif (
            self.__is_valid_str(self.__client_id)
            and self.__is_valid_str(self.__username)
            and self.__is_valid_str(self.__password)
        ):
            # 如果已经通过基于mqtt的免预注册一型一密协议获取到了client_id, user_name, password
            client_id = self.__client_id
            username = self.__username
            password = self.__password
        # 基于mqtt协议的一型一密，包括预注册和非预注册两种, 尝试去获取username, clientid和password
        elif self.__is_valid_str(self.__product_secret):
            if self.__auth_type == "regnwl":
                # 通过一型一密免预注册协议发起认证
                self.__dynamic_register_nwl_flag = 1
            elif self.__auth_type == "register":
                # 通过一型一密预注册协议发起认证
                self.__dynamic_register_flag = 1
            else:
                raise LinkKit.StateError("unknow dynreg param error")

            auth_type_str = self.__auth_type
            random_str = self.__generate_random_str(15)
            if self.__is_valid_str(self.__instance_id):
                client_id = "%s.%s|random=%s,authType=%s,securemode=2,signmethod=hmacsha256,instanceId=%s|" % (
                    self.__device_name,
                    self.__product_key,
                    random_str,
                    auth_type_str,
                    self.__instance_id,
                )
            else:
                client_id = "%s.%s|random=%s,authType=%s,securemode=2,signmethod=hmacsha256|" % (
                    self.__device_name,
                    self.__product_key,
                    random_str,
                    auth_type_str,
                )
            username = "%s&%s" % (self.__device_name, self.__product_key)
            password_src = "deviceName%sproductKey%srandom%s" % (self.__device_name, self.__product_key, random_str)
            password = hmac.new(
                self.__product_secret.encode("utf-8"), password_src.encode("utf-8"), hashlib.sha256
            ).hexdigest()
        else:
            raise LinkKit.StateError("unknow auth error")

        # mqtt client start initialize
        mqtt_protocol_version = mqtt.MQTTv311
        if self.__mqtt_protocol == "MQTTv311":
            mqtt_protocol_version = mqtt.MQTTv311
        elif self.__mqtt_protocol == "MQTTv31":
            mqtt_protocol_version = mqtt.MQTTv31
        self.__mqtt_client = mqtt.Client(
            client_id=client_id, clean_session=self.__mqtt_clean_session, protocol=mqtt_protocol_version
        )

        if self.__link_log.is_enabled():
            self.__mqtt_client.enable_logger(self.__PahoLog)
        self.__mqtt_client.username_pw_set(username, password)
        self.__mqtt_client.on_connect = self.__on_internal_connect
        self.__mqtt_client.on_disconnect = self.__on_internal_disconnect
        self.__mqtt_client.on_message = self.__on_internal_message
        self.__mqtt_client.on_publish = self.__on_internal_publish
        self.__mqtt_client.on_subscribe = self.__on_internal_subscribe
        self.__mqtt_client.on_unsubscribe = self.__on_internal_unsubscribe

        self.__mqtt_client.reconnect_delay_set(self.__mqtt_auto_reconnect_min_sec, self.__mqtt_auto_reconnect_max_sec)
        self.__mqtt_client.max_queued_messages_set(self.__mqtt_max_queued_message)
        self.__mqtt_client.max_inflight_messages_set(self.__mqtt_max_inflight_message)

        # mqtt set tls
        self.__link_log.debug("current working directory:" + os.getcwd())
        if self.__mqtt_secure == "TLS":
            context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cadata=self.__aliyun_broker_ca_data)
            context.check_hostname = self.__check_hostname
            self.__mqtt_client.tls_set_context(context)
        # mqtt client start connect
        self.__host_name_internal = self.__generate_endpoint()

    def __generate_endpoint(self):
        if self.__endpoint:
            return self.__endpoint
        elif self.__host_name == "127.0.0.1" or self.__host_name == "localhost":
            return self.__host_name
        elif self.__is_valid_str(self.__instance_id):
            return self.__instance_id + ".mqtt.iothub.aliyuncs.com"
        else:
            return "%s.iot-as-mqtt.%s.aliyuncs.com" % (self.__product_key, self.__host_name)

    def connect(self):
        raise LinkKit.StateError("not supported")

    def connect_async(self):
        self.__link_log.debug("connect_async")
        if self.__linkkit_state not in (LinkKit.LinkKitState.INITIALIZED, LinkKit.LinkKitState.DISCONNECTED):
            raise LinkKit.StateError("not in INITIALIZED or DISCONNECTED state")
        self.__connect_async_req = True
        with self.__worker_loop_exit_req_lock:
            self.__worker_loop_exit_req = False
        return self.__loop_thread.start(self.__loop_forever_internal)

    def disconnect(self) -> None:
        self.__link_log.debug("disconnect")
        if self.__linkkit_state is not LinkKit.LinkKitState.CONNECTED:
            self.__link_log.info("already disconnected, return")
            return
        self.__linkkit_state = LinkKit.LinkKitState.DISCONNECTING
        if self.__connect_async_req:
            with self.__worker_loop_exit_req_lock:
                self.__worker_loop_exit_req = True
        self.__mqtt_client.disconnect()
        self.__loop_thread.stop()

    @staticmethod
    def __check_topic_string(topic):
        if len(topic) > 128 or len(topic) == 0:
            raise ValueError("topic string length too long,need decrease %d bytes" % (128 - len(topic)))

    def publish_topic(self, topic, payload=None, qos=1):
        if self.__linkkit_state is not LinkKit.LinkKitState.CONNECTED:
            self.__link_log.error("disconnected, pub fail")
            return LinkKit.ErrorCode.NETWORK_DISCONNECTED.value, None
        if topic is None or len(topic) == 0:
            return LinkKit.ErrorCode.INVALID_TOPIC.value, None
        if qos != 0 and qos != 1:
            return LinkKit.ErrorCode.INVALID_QOS.value, None
        self.__check_topic_string(topic)
        rc, mid = self.__mqtt_client.publish(topic, payload, qos)
        if rc == 0:
            return LinkKit.ErrorCode.SUCCESS.value, mid
        else:
            return LinkKit.ErrorCode.PAHO_MQTT_ERROR.value, None

    def subscribe_topic(self, topic, qos=1):
        if self.__linkkit_state is not LinkKit.LinkKitState.CONNECTED:
            self.__link_log.error("disconnected, sub fail")
            return LinkKit.ErrorCode.NETWORK_DISCONNECTED.value, None
        if isinstance(topic, tuple):
            topic, qos = topic

        if isinstance(topic, str):
            if qos < 0 or qos > 1:
                return LinkKit.ErrorCode.INVALID_QOS.value, None
            if topic is None or len(topic) == 0:
                return LinkKit.ErrorCode.INVALID_TOPIC.value, None
            self.__check_topic_string(topic)
            if topic not in self.__user_topics:
                self.__user_topics_request_lock.acquire()
                ret = self.__mqtt_client.subscribe(topic, qos)
                rc, mid = ret
                if rc == mqtt.MQTT_ERR_SUCCESS:
                    self.__user_topics_subscribe_request[mid] = [(topic, qos)]
                self.__user_topics_request_lock.release()
                if rc == mqtt.MQTT_ERR_SUCCESS:
                    return 0, mid
                if rc == mqtt.MQTT_ERR_NO_CONN:
                    return 2, None
                return 3, None
            else:
                return 1, None
        elif isinstance(topic, list):
            topic_qos_list = []
            user_topic_dict = {}
            for t, q in topic:
                if q < 0 or q > 1:
                    return LinkKit.ErrorCode.INVALID_QOS.value, None
                if t is None or len(t) == 0 or not isinstance(t, str):
                    return LinkKit.ErrorCode.INVALID_TOPIC.value, None
                self.__check_topic_string(t)
                user_topic_dict[t] = q
                topic_qos_list.append((t, q))
            self.__user_topics_request_lock.acquire()
            ret = self.__mqtt_client.subscribe(topic_qos_list)
            rc, mid = ret
            if rc == mqtt.MQTT_ERR_SUCCESS:
                self.__user_topics_subscribe_request[mid] = topic_qos_list
                self.__link_log.debug("__user_topics_subscribe_request add mid:%d" % mid)
            self.__user_topics_request_lock.release()
            return rc, mid
        else:
            self.__link_log.error("Parameter type wrong")
            return LinkKit.ErrorCode.INVALID_TOPIC.value, None

    def unsubscribe_topic(self, topic):
        if self.__linkkit_state is not LinkKit.LinkKitState.CONNECTED:
            self.__link_log.error("disconnected, unsub fail")
            return LinkKit.ErrorCode.NETWORK_DISCONNECTED.value, None
        unsubscribe_topics = []
        if topic is None or topic == "":
            return LinkKit.ErrorCode.INVALID_TOPIC.value, None
        if isinstance(topic, str):
            self.__check_topic_string(topic)
            if topic not in self.__user_topics:
                return 1, None
            unsubscribe_topics.append(topic)
        elif isinstance(topic, list):
            for one_topic in topic:
                self.__check_topic_string(one_topic)
                if one_topic in self.__user_topics:
                    unsubscribe_topics.append(one_topic)
                else:
                    pass
        with self.__user_topics_unsubscribe_request_lock:
            if len(unsubscribe_topics) == 0:
                return 2, None
            ret = self.__mqtt_client.unsubscribe(unsubscribe_topics)
            rc, mid = ret
            if rc == mqtt.MQTT_ERR_SUCCESS:
                self.__user_topics_unsubscribe_request[mid] = unsubscribe_topics
                return ret
            else:
                return 1, None

    def __make_rrpc_topic(self, topic) -> str:
        return "/ext/rrpc/+%s" % (topic)

    def subscribe_rrpc_topic(self, topic):
        if self.__linkkit_state is not LinkKit.LinkKitState.CONNECTED:
            self.__link_log.error("disconnected, sub rrpc fail")
            return LinkKit.ErrorCode.NETWORK_DISCONNECTED.value, None
        qos = 0
        if isinstance(topic, str):
            if topic is None or len(topic) == 0:
                return LinkKit.ErrorCode.INVALID_TOPIC.value, None
            self.__check_topic_string(topic)
            topic = self.__tidy_topic(topic)
            rrpc_topic = self.__make_rrpc_topic(topic)
            with self.__user_rrpc_topics_lock:
                not_exist = topic not in self.__user_rrpc_topics.keys()
            if not_exist:
                with self.__user_rrpc_topics_lock:
                    self.__user_rrpc_topics[topic] = qos
                with self.__user_rrpc_topics_subscribe_request_lock:
                    ret = self.__mqtt_client.subscribe(rrpc_topic, qos)
                    rc, mid = ret
                    if rc == mqtt.MQTT_ERR_SUCCESS:
                        self.__user_rrpc_topics_subscribe_request[mid] = [(rrpc_topic, qos)]
                    if rc == mqtt.MQTT_ERR_SUCCESS:
                        return 0, mid
                    if rc == mqtt.MQTT_ERR_NO_CONN:
                        return 2, None
                    return 3, None
            else:
                return 1, None
        elif isinstance(topic, list):
            topic_qos_list = []
            for t in topic:
                if t is None or len(t) == 0 or not isinstance(t, str):
                    return LinkKit.ErrorCode.INVALID_TOPIC.value, None
                self.__check_topic_string(t)
                t = self.__tidy_topic(t)
                rrpc_t = self.__make_rrpc_topic(t)
                with self.__user_rrpc_topics_lock:
                    self.__user_rrpc_topics[t] = qos
                topic_qos_list.append((rrpc_t, qos))
            with self.__user_rrpc_topics_subscribe_request_lock:
                ret = self.__mqtt_client.subscribe(topic_qos_list)
                rc, mid = ret
                if rc == mqtt.MQTT_ERR_SUCCESS:
                    self.__user_rrpc_topics_subscribe_request[mid] = topic_qos_list
                    self.__link_log.debug("__user_rrpc_topics_subscribe_request add mid:%d" % mid)
                return rc, mid
        else:
            self.__link_log.debug("Parameter type wrong")
            return LinkKit.ErrorCode.INVALID_TOPIC.value, None

    def unsubscribe_rrpc_topic(self, topic):
        if self.__linkkit_state is not LinkKit.LinkKitState.CONNECTED:
            self.__link_log.error("disconnected, unsub rrpc fail")
            return LinkKit.ErrorCode.NETWORK_DISCONNECTED.value, None
        unsubscribe_topics = []
        if topic is None or topic == "":
            return LinkKit.ErrorCode.INVALID_TOPIC.value, None
        if isinstance(topic, str):
            self.__check_topic_string(topic)
            topic = self.__tidy_topic(topic)
            with self.__user_rrpc_topics_lock:
                if topic not in self.__user_rrpc_topics:
                    return 1, None
            rrpc_topic = self.__make_rrpc_topic(topic)
            unsubscribe_topics.append(rrpc_topic)
            with self.__user_rrpc_topics_lock:
                del self.__user_rrpc_topics[topic]

        elif isinstance(topic, list):
            for one_topic in topic:
                self.__check_topic_string(one_topic)
                one_topic = self.__tidy_topic(one_topic)
                with self.__user_rrpc_topics_lock:
                    if one_topic in self.__user_rrpc_topics:
                        rrpc_topic = self.__make_rrpc_topic(one_topic)
                        unsubscribe_topics.append(rrpc_topic)
                        del self.__user_rrpc_topics[one_topic]
                    else:
                        pass
        with self.__user_rrpc_topics_unsubscribe_request_lock:
            if len(unsubscribe_topics) == 0:
                return 2, None
            ret = self.__mqtt_client.unsubscribe(unsubscribe_topics)
            rc, mid = ret
            if rc == mqtt.MQTT_ERR_SUCCESS:
                self.__user_rrpc_topics_unsubscribe_request[mid] = unsubscribe_topics
                return ret
            else:
                return 1, None

    def __on_internal_connect_safe(self, client, user_data, session_flag, rc) -> None:
        if rc == 0:
            self.__reset_reconnect_wait()
            self.__force_reconnect = False
        session_flag_internal = {"session present": session_flag}
        self.__handler_task.post_message(
            self.__handler_task_cmd_on_connect, (client, user_data, session_flag_internal, rc)
        )

    def __loop_forever_internal(self):
        self.__link_log.debug("enter")
        self.__linkkit_state = LinkKit.LinkKitState.CONNECTING

        # 为了保持存量设备兼容，保留了基于https的需要预注册的一型一密的预注册
        if not self.__is_valid_str(self.__device_secret) and self.__is_valid_str(self.__product_secret):
            lack_other_auth_info = (
                not self.__is_valid_str(self.__username)
                or not self.__is_valid_str(self.__client_id)
                or not self.__is_valid_str(self.__password)
            )
            if not self.__is_valid_str(self.__auth_type) and lack_other_auth_info:
                rc, value = self.__dynamic_register_device()
                try:
                    self.__on_device_dynamic_register(rc, value, self.__user_data)
                    if rc == 0:
                        self.__device_secret = value
                    else:
                        self.__link_log.error("dynamic register device fail:" + value)
                        self.__linkkit_state = LinkKit.LinkKitState.INITIALIZED
                        return 1
                except Exception as e:
                    self.__link_log.error(e)
                    self.__linkkit_state = LinkKit.LinkKitState.INITIALIZED
                    return 2
        try:
            self.__config_mqtt_client_internal()
        except ssl.SSLError as e:
            self.__link_log.error("config mqtt raise exception:" + str(e))
            self.__linkkit_state = LinkKit.LinkKitState.INITIALIZED
            self.__on_internal_connect_safe(None, None, 0, 6)
            return

        try:
            self.__mqtt_client.connect_async(
                host=self.__host_name_internal, port=self.__mqtt_port, keepalive=self.__mqtt_keep_alive
            )
        except Exception as e:
            self.__link_log.error("__loop_forever_internal connect raise exception:" + str(e))
            self.__linkkit_state = LinkKit.LinkKitState.INITIALIZED
            self.__on_internal_connect_safe(None, None, 0, 7)
            return
        while True:
            if self.__worker_loop_exit_req:
                if self.__linkkit_state == LinkKit.LinkKitState.DESTRUCTING:
                    self.__handler_task.stop()
                    self.__linkkit_state = LinkKit.LinkKitState.DESTRUCTED
                break
            try:
                self.__linkkit_state = LinkKit.LinkKitState.CONNECTING
                self.__mqtt_client.reconnect()
            except OSError as e:
                self.__link_log.error(e)
                # if isinstance(e, socket.timeout):
                #     self.__link_log.error("connect timeout")
                #     self.__on_internal_connect_safe(None, None, 0, 8)
                #     self.__reconnect_wait()
                #     continue
                # if isinstance(e, ssl.SSLError):
                #     self.__on_internal_connect_safe(None, None, 0, 6)
                #     return
                if self.__linkkit_state == LinkKit.LinkKitState.CONNECTING:
                    self.__linkkit_state = LinkKit.LinkKitState.DISCONNECTED
                self.__on_internal_connect_safe(None, None, 0, 9)
                if self.__linkkit_state == LinkKit.LinkKitState.DESTRUCTING:
                    self.__handler_task.stop()
                    self.__linkkit_state = LinkKit.LinkKitState.DESTRUCTED
                    break
                self.__reconnect_wait()
                continue
                # 1. ca wrong 2.socket create timeout 3.connect timeout, call on_connect error
            # connect success
            rc = mqtt.MQTT_ERR_SUCCESS
            while rc == mqtt.MQTT_ERR_SUCCESS:
                try:
                    rc = self.__mqtt_client.loop(self.__mqtt_request_timeout)
                except Exception as e:
                    self.__link_log.info("loop error:" + str(e))
                self.__clean_timeout_message()
                self.__clean_thing_timeout_request_id()
                if self.__force_reconnect is True:
                    self.__force_reconnect = False
                    break

            if self.__linkkit_state == LinkKit.LinkKitState.CONNECTED:
                self.__on_internal_disconnect(None, None, 1)
            self.__link_log.info("loop return:%r" % rc)

            if self.__worker_loop_exit_req:
                if self.__linkkit_state == LinkKit.LinkKitState.DESTRUCTING:
                    self.__handler_task.stop()
                    self.__linkkit_state = LinkKit.LinkKitState.DESTRUCTED
                break
            self.__reconnect_wait()
            # 在mqtt + 一型一密免预注册的情况下，由于三元组不对，导致无法与服务器建连,因此需要退出，否则会一直重试
            if self.__dynamic_register_nwl_flag == 1:
                if self.__on_device_dynamic_register_nwl_reply is not None:
                    self.__on_device_dynamic_register_nwl_reply(
                        LinkKit.ErrorCode.DYNREG_AUTH_NWL_FAILED.value, None, None, None
                    )
                self.__linkkit_state = LinkKit.LinkKitState.DISCONNECTED
                self.__dynamic_register_nwl_flag = 0
                break
            # 在mqtt + 一型一密预注册的情况下，由于三元组不对，导致无法与服务器建连,因此需要退出，否则会一直重试
            if self.__dynamic_register_flag == 1:
                if self.__on_device_dynamic_register is not None:
                    self.__on_device_dynamic_register(LinkKit.ErrorCode.DYNREG_AUTH_FAILED.value, None, None)
                self.__linkkit_state = LinkKit.LinkKitState.DISCONNECTED
                self.__dynamic_register_flag = 0
                break

    def __clean_timeout_message(self) -> None:
        # self.__link_log.debug("__clean_timeout_message enter")
        expire_timestamp = self.__timestamp() - self.__mqtt_request_timeout * 1000
        with self.__thing_prop_post_mid_lock:
            self.__clean_timeout_message_item(self.__thing_prop_post_mid, expire_timestamp)
        with self.__thing_event_post_mid_lock:
            self.__clean_timeout_message_item(self.__thing_event_post_mid, expire_timestamp)
        with self.__thing_answer_service_mid_lock:
            self.__clean_timeout_message_item(self.__thing_answer_service_mid, expire_timestamp)
        with self.__thing_raw_up_mid_lock:
            self.__clean_timeout_message_item(self.__thing_raw_up_mid, expire_timestamp)
        with self.__thing_raw_down_reply_mid_lock:
            self.__clean_timeout_message_item(self.__thing_raw_down_reply_mid, expire_timestamp)
        with self.__thing_prop_set_reply_mid_lock:
            self.__clean_timeout_message_item(self.__thing_prop_set_reply_mid, expire_timestamp)
        self.__clean_timeout_message_item(self.__device_info_mid, expire_timestamp)
        # self.__link_log.debug("__clean_timeout_message exit")

    def __clean_timeout_message_item(self, mids, expire_time) -> None:
        for mid in list(mids.keys()):
            if mids[mid] < expire_time:
                timestamp = mids.pop(mid)
                self.__link_log.error("__clean_timeout_message_item pop:%r,timestamp:%r", mid, timestamp)

    def __reconnect_wait(self) -> None:
        if self.__mqtt_auto_reconnect_sec == 0:
            self.__mqtt_auto_reconnect_sec = self.__mqtt_auto_reconnect_min_sec
        else:
            self.__mqtt_auto_reconnect_sec = min(self.__mqtt_auto_reconnect_sec * 2, self.__mqtt_auto_reconnect_max_sec)
            self.__mqtt_auto_reconnect_sec += random.randint(1, self.__mqtt_auto_reconnect_sec)
        time.sleep(self.__mqtt_auto_reconnect_sec)

    def __reset_reconnect_wait(self) -> None:
        self.__mqtt_auto_reconnect_sec = 0

    def start_worker_loop(self) -> None:
        pass

    def thing_setup(self, file=None) -> int:
        if self.__linkkit_state is not LinkKit.LinkKitState.INITIALIZED:
            raise LinkKit.StateError("not in INITIALIZED state")
        if self.__thing_setup_state:
            return 1
        if file is None:
            self.__thing_raw_only = True
            self.__thing_setup_state = True
            return 0
        try:
            with open(file, encoding="utf-8") as f:
                tsl = json.load(f)
                index = 0
                while "events" in tsl and index < len(tsl["events"]):
                    identifier = tsl["events"][index]["identifier"]
                    if identifier == "post":
                        output_data = tsl["events"][index]["outputData"]
                        output_data_index = 0
                        while output_data_index < len(output_data):
                            output_data_item = output_data[output_data_index]["identifier"]
                            self.__thing_properties_post.add(output_data_item)
                            output_data_index += 1
                    else:
                        self.__thing_events.add(identifier)
                    index += 1
                index = 0
                while "services" in tsl and index < len(tsl["services"]):
                    identifier = tsl["services"][index]["identifier"]
                    if identifier == "set":
                        input_data = tsl["services"][index]["inputData"]
                        input_data_index = 0
                        while input_data_index < len(input_data):
                            input_data_item = input_data[input_data_index]
                            self.__thing_properties_set.add(input_data_item["identifier"])
                            input_data_index += 1
                    elif identifier == "get":
                        output_data = tsl["services"][index]["outputData"]
                        output_data_index = 0
                        while output_data_index < len(output_data):
                            output_data_item = output_data[output_data_index]
                            self.__thing_properties_get.add(output_data_item["identifier"])
                            output_data_index += 1
                    else:
                        self.__thing_services.add(identifier)
                        service_reply_topic = self.__thing_topic_service_pattern % (
                            self.__product_key,
                            self.__device_name,
                            identifier + "_reply",
                        )
                        self.__thing_topic_services_reply.add(service_reply_topic)
                    index += 1

                for event in self.__thing_events:
                    post_topic = self.__thing_topic_event_post_pattern % (self.__product_key, self.__device_name, event)
                    self.__thing_topic_event_post[event] = post_topic
                    self.__thing_topic_event_post_reply.add(post_topic + "_reply")
                # service topic
                for service in self.__thing_services:
                    self.__thing_topic_services.add(
                        self.__thing_topic_service_pattern % (self.__product_key, self.__device_name, service)
                    )

        except Exception as e:
            self.__link_log.info("file open error:" + str(e))
            return 2
        self.__thing_setup_state = True
        return 0

    def thing_raw_post_data(self, payload):
        if self.__linkkit_state is not LinkKit.LinkKitState.CONNECTED:
            self.__link_log.error("disconnected, post raw fail")
            return LinkKit.ErrorCode.NETWORK_DISCONNECTED.value
        with self.__thing_raw_up_mid_lock:
            rc, mid = self.__mqtt_client.publish(self.__thing_topic_raw_up, payload, 0)
            if rc == mqtt.MQTT_ERR_SUCCESS:
                self.__thing_raw_up_mid[mid] = self.__timestamp()
                return 0
        return 1

    def thing_raw_data_reply(self, payload):
        if self.__linkkit_state is not LinkKit.LinkKitState.CONNECTED:
            self.__link_log.error("disconnected, raw data reply fail")
            return LinkKit.ErrorCode.NETWORK_DISCONNECTED.value
        with self.__thing_raw_down_reply_mid_lock:
            rc, mid = self.__mqtt_client.publish(self.__thing_topic_raw_down_reply, payload, 0)
            if rc == mqtt.MQTT_ERR_SUCCESS:
                self.__thing_raw_down_reply_mid[mid] = self.__timestamp()
                return 0
        return 1

    def thing_update_device_info(self, payload):
        if self.__linkkit_state is not LinkKit.LinkKitState.CONNECTED:
            self.__link_log.error("disconnected, update device info fail")
            return LinkKit.ErrorCode.NETWORK_DISCONNECTED.value, None
        if not self.__thing_setup_state or not self.__thing_enable_state:
            raise LinkKit.StateError("not in SETUP & ENABLE state")
            return 1, None
        request_id = self.__get_thing_request_id()
        with self.__thing_update_device_info_up_mid_lock:
            rc, mid = self.__mqtt_client.publish(
                self.__thing_topic_update_device_info_up,
                self.__pack_alink_request(request_id, "thing.deviceinfo.update", payload),
                0,
            )
            if rc == mqtt.MQTT_ERR_SUCCESS:
                self.__thing_update_device_info_up_mid[mid] = self.__timestamp()
                return rc, request_id
        return 1, None

    def thing_delete_device_info(self, payload):
        if self.__linkkit_state is not LinkKit.LinkKitState.CONNECTED:
            self.__link_log.error("disconnected, delete device info fail")
            return LinkKit.ErrorCode.NETWORK_DISCONNECTED.value, None
        if not self.__thing_setup_state or not self.__thing_enable_state:
            return 1
        request_id = self.__get_thing_request_id()
        with self.__thing_delete_device_info_up_mid_lock:
            rc, mid = self.__mqtt_client.publish(
                self.__thing_topic_delete_device_info_up,
                self.__pack_alink_request(request_id, "thing.deviceinfo.delete", payload),
                0,
            )
            if rc == mqtt.MQTT_ERR_SUCCESS:
                self.__thing_delete_device_info_up_mid[mid] = self.__timestamp()
                return rc, request_id
        return 1, None

    def thing_update_tags(self, tagMap):
        if not isinstance(tagMap, dict):
            raise ValueError("tagMap must be a dictionary")
            return 1, None

        payload = []
        for k, v in tagMap.items():
            payload.append({LinkKit.TAG_KEY: k, LinkKit.TAG_VALUE: v})
        return self.thing_update_device_info(payload)

    def thing_remove_tags(self, tagKeys):
        if not isinstance(tagKeys, list) and not isinstance(tagKeys, tuple):
            raise ValueError("tagKeys must be a list or tuple")
            return 1, None

        payload = []
        for tagKey in tagKeys:
            payload.append({LinkKit.TAG_KEY: tagKey})
        return self.thing_delete_device_info(payload)

    def __pack_alink_request(self, request_id, method, params):
        request = {"id": request_id, "version": "1.0", "params": params, "method": method}
        return json.dumps(request)

    def thing_answer_service(self, identifier, request_id, code, data=None):
        if self.__linkkit_state is not LinkKit.LinkKitState.CONNECTED:
            self.__link_log.error("disconnected, answer service fail")
            return LinkKit.ErrorCode.NETWORK_DISCONNECTED.value
        if not self.__thing_setup_state or not self.__thing_enable_state:
            return 1
        if data is None:
            data = {}
        response = {"id": request_id, "code": code, "data": data}

        item = self.__pop_rrpc_service("alink_" + str(request_id))
        if item:
            service_reply_topic = item["topic"]
        else:
            service_reply_topic = self.__thing_topic_service_pattern % (
                self.__product_key,
                self.__device_name,
                identifier + "_reply",
            )
        with self.__thing_answer_service_mid_lock:
            rc, mid = self.__mqtt_client.publish(service_reply_topic, json.dumps(response), 0)
            if rc == mqtt.MQTT_ERR_SUCCESS:
                self.__thing_answer_service_mid[mid] = self.__timestamp()
                return 0
        return 1

    def __get_thing_request_id(self):
        with self.__thing_request_id_lock:
            self.__thing_request_value += 1
            if self.__thing_request_value > self.__thing_request_id_max:
                self.__thing_request_value = 0
            if len(self.__thing_request_id) > self.__mqtt_max_queued_message:
                return None
            if self.__thing_request_value not in self.__thing_request_id:
                self.__thing_request_id[self.__thing_request_value] = self.__timestamp()
                self.__link_log.debug("__get_thing_request_id pop:%r" % self.__thing_request_value)
                return str(self.__thing_request_value)
            return None

    def __back_thing_request_id(self, post_id) -> None:
        with self.__thing_request_id_lock:
            try:
                self.__thing_request_id.pop(int(post_id))
            except Exception as e:
                self.__link_log.error("__back_thing_request_id pop:%r,%r" % (post_id, e))

    def __reset_thing_request_id(self) -> None:
        with self.__thing_request_id_lock:
            self.__thing_request_value = 0
            self.__thing_request_id.clear()

    def __clean_thing_timeout_request_id(self) -> None:
        with self.__thing_request_id_lock:
            expire_timestamp = self.__timestamp() - self.__mqtt_request_timeout * 1000
            for request_id in list(self.__thing_request_id.keys()):
                if self.__thing_request_id[request_id] < expire_timestamp:
                    timestamp = self.__thing_request_id.pop(request_id)
                    self.__link_log.error("__clean_thing_timeout_request_id pop:%r,timestamp:%r", request_id, timestamp)

    def thing_trigger_event(self, event_tuple):
        if self.__linkkit_state is not LinkKit.LinkKitState.CONNECTED:
            self.__link_log.error("disconnected, trigger event fail")
            return LinkKit.ErrorCode.NETWORK_DISCONNECTED.value, None
        if not self.__thing_setup_state or not self.__thing_enable_state:
            return 1, None
        if isinstance(event_tuple, tuple):
            event, params = event_tuple
        else:
            return 1, None
        if event not in self.__thing_topic_event_post.keys():
            return 1, None
        request_id = self.__get_thing_request_id()
        if request_id is None:
            return 1
        request = {
            "id": request_id,
            "version": "1.0",
            "params": {
                "value": params,
            },
            "method": "thing.event.%s.post" % event,
        }
        with self.__thing_event_post_mid_lock:
            event_topic = self.__thing_topic_event_post[event]
            self.__link_log.debug("thing_trigger_event publish topic")
            rc, mid = self.__mqtt_client.publish(event_topic, json.dumps(request), 0)
            self.__link_log.debug("thing_trigger_event publish done")
            if rc == mqtt.MQTT_ERR_SUCCESS:
                self.__thing_event_post_mid[mid] = self.__timestamp()
                return 0, request_id
            else:
                return 1, None

    def thing_post_property(self, property_data):
        if self.__linkkit_state is not LinkKit.LinkKitState.CONNECTED:
            self.__link_log.error("disconnected, post property fail")
            return LinkKit.ErrorCode.NETWORK_DISCONNECTED.value, None
        if not self.__thing_setup_state or not self.__thing_enable_state:
            return 1, None
        request_params = property_data
        request_id = self.__get_thing_request_id()
        if request_id is None:
            return 1, None
        request = {"id": request_id, "version": "1.0", "params": request_params, "method": "thing.event.property.post"}
        with self.__thing_prop_post_mid_lock:
            rc, mid = self.__mqtt_client.publish(self.__thing_topic_prop_post, json.dumps(request), 1)
            if rc == mqtt.MQTT_ERR_SUCCESS:
                self.__thing_prop_post_mid[mid] = self.__timestamp()
                return 0, request_id
            else:
                return 1, None

    def __on_internal_async_message(self, message) -> None:
        self.__link_log.debug("__on_internal_async_message topic:%r" % message.topic)
        triggered_flag = 0

        if message.topic == self.__thing_topic_prop_set:
            payload = self.__load_json(message.payload)
            params = payload["params"]
            try:
                reply = {"id": payload["id"], "code": 200, "data": {}}
                with self.__thing_prop_set_reply_mid_lock:
                    rc, mid = self.__mqtt_client.publish(self.__thing_topic_prop_set_reply, json.dumps(reply), 1)
                    if rc == 0:
                        self.__link_log.info("prop changed reply success,mid:%d" % mid)
                        self.__thing_prop_set_reply_mid[mid] = self.__timestamp()
                        self.__link_log.info("prop changed reply success")
                    else:
                        self.__link_log.info("prop changed reply fail")
                if self.__on_thing_prop_changed is not None:
                    triggered_flag = 1
                    self.__on_thing_prop_changed(params, self.__user_data)
            except Exception as e:
                self.__link_log.error("on_thing_prop_changed raise exception:%s" % e)
        elif message.topic == self.__device_info_topic_reply:
            payload = self.__load_json(message.payload)
            request_id = payload["id"]
            code = payload["code"]
            reply_message = payload["message"]
            data = payload["data"]
            self.__back_thing_request_id(request_id)
            if code != 200:
                self.__link_log.error("upload device info reply error:%s" % reply_message)
            try:
                if self.__on_thing_device_info_update is not None:
                    triggered_flag = 1
                    self.__on_thing_device_info_update(request_id, code, data, reply_message, self.__user_data)
            except Exception as e:
                self.__link_log.error("__on_thing_device_info_update process raise exception:%s" % e)
        elif message.topic == self.__thing_topic_prop_post_reply:
            payload = self.__load_json(message.payload)
            request_id = payload["id"]
            code = payload["code"]
            data = payload["data"]
            reply_message = payload["message"]
            try:
                if self.__on_thing_prop_post is not None:
                    triggered_flag = 1
                    self.__on_thing_prop_post(request_id, code, data, reply_message, self.__user_data)
            except Exception as e:
                self.__link_log.error("on_thing_prop_post raise exception:%s" % e)
            self.__back_thing_request_id(request_id)
        elif message.topic == self.__thing_topic_prop_get:
            pass
        elif message.topic in self.__thing_topic_event_post_reply:
            event = message.topic.split("/", 7)[6]
            payload = self.__load_json(message.payload)
            request_id = payload["id"]
            code = payload["code"]
            data = payload["data"]
            reply_message = payload["message"]
            self.__link_log.info("on_thing_event_post message:%s" % reply_message)
            try:
                if self.on_thing_event_post is not None:
                    triggered_flag = 1
                    self.on_thing_event_post(event, request_id, code, data, reply_message, self.__user_data)
            except Exception as e:
                self.__link_log.error("on_thing_event_post raise exception:%s" % e)
            self.__back_thing_request_id(request_id)
        elif message.topic in self.__thing_topic_services:
            identifier = message.topic.split("/", 6)[6]
            payload = self.__load_json(message.payload)
            try:
                request_id = payload["id"]
                params = payload["params"]
                if self.__on_thing_call_service is not None:
                    triggered_flag = 1
                    self.__on_thing_call_service(identifier, request_id, params, self.__user_data)
            except Exception as e:
                self.__link_log.error("on_thing_call_service raise exception: %s" % e)
        elif message.topic == self.__thing_topic_raw_down:
            try:
                if self.__on_thing_raw_data_arrived is not None:
                    triggered_flag = 1
                    self.__on_thing_raw_data_arrived(message.payload, self.__user_data)
            except Exception as e:
                self.__link_log.error("on_thing_raw_data_arrived process raise exception:%s" % e)
        elif message.topic == self.__thing_topic_raw_up_reply:
            try:
                if self.__on_thing_raw_data_post is not None:
                    triggered_flag = 1
                    self.__on_thing_raw_data_post(message.payload, self.__user_data)
            except Exception as e:
                self.__link_log.error("on_thing_raw_post_data process raise exception:%s" % e)
        elif message.topic == self.__thing_topic_update_device_info_reply:
            try:
                if self.__on_thing_device_info_update is not None:
                    triggered_flag = 1
                    payload = self.__load_json(message.payload)
                    request_id = payload["id"]
                    code = payload["code"]
                    data = payload["data"]
                    msg = payload["message"]
                    self.__on_thing_device_info_update(request_id, code, data, msg, self.__user_data)
            except Exception as e:
                self.__link_log.error("__on_thing_device_info_update process raise exception:%s" % e)
        elif message.topic == self.__thing_topic_delete_device_info_reply:
            try:
                if self.__on_thing_device_info_delete is not None:
                    triggered_flag = 1
                    payload = self.__load_json(message.payload)
                    request_id = payload["id"]
                    code = payload["code"]
                    data = payload["data"]
                    msg = payload["message"]
                    self.__on_thing_device_info_delete(request_id, code, data, msg, self.__user_data)
            except Exception as e:
                self.__link_log.error("__on_thing_device_info_update process raise exception:%s" % e)
        elif message.topic == self.__thing_topic_shadow_get:
            self.__try_parse_try_shadow(message.payload)
            try:
                if self.__on_thing_shadow_get is not None:
                    triggered_flag = 1
                    self.__on_thing_shadow_get(self.__load_json(message.payload), self.__user_data)
            except Exception as e:
                self.__link_log.error("__on_thing_shadow_get process raise exception:%s" % e)
        elif message.topic.startswith("/ext/rrpc/"):
            triggered_flag = self.__try_parse_rrpc_topic(message)
        elif message.topic == self.__gateway_topic_topo_change:
            try:
                payload = self.__load_json(message.payload)
                request_id = payload["id"]
                params = payload["params"]
                if self.__on_gateway_topo_change is not None:
                    triggered_flag = 1
                    self.__on_gateway_topo_change(request_id, params, self.__user_data)
            except Exception as e:
                self.__link_log.error("__on_gateway_topo_change process raise exception:%s" % e)
        elif message.topic == self.__gateway_topic_add_subdev_topo_reply:
            try:
                payload = self.__load_json(message.payload)
                request_id = payload["id"]
                code = payload["code"]
                data = payload["data"]
                msg = payload["message"]
                self.__back_thing_request_id(request_id)
                if self.__on_gateway_add_subdev_topo_reply is not None:
                    triggered_flag = 1
                    self.__on_gateway_add_subdev_topo_reply(request_id, code, data, msg, self.__user_data)
            except Exception as e:
                self.__link_log.error("__on_gateway_add_subdev_topo_reply process raise exception:%s" % e)
        elif message.topic == self.__gateway_topic_delete_subdev_topo_reply:
            try:
                payload = self.__load_json(message.payload)
                request_id = payload["id"]
                code = payload["code"]
                data = payload["data"]
                msg = payload["message"]
                self.__back_thing_request_id(request_id)
                if self.__on_gateway_delete_subdev_topo_reply is not None:
                    triggered_flag = 1
                    self.__on_gateway_delete_subdev_topo_reply(request_id, code, data, msg, self.__user_data)
            except Exception as e:
                self.__link_log.error("__on_gateway_delete_subdev_topo_reply process raise exception:%s" % e)
        elif message.topic == self.__gateway_topic_login_subdev_reply:
            try:
                payload = self.__load_json(message.payload)
                request_id = payload["id"]
                code = payload["code"]
                data = payload["data"]
                msg = payload["message"]
                self.__back_thing_request_id(request_id)
                if self.__on_gateway_login_subdev_reply is not None:
                    triggered_flag = 1
                    self.__on_gateway_login_subdev_reply(request_id, code, data, msg, self.__user_data)
            except Exception as e:
                self.__link_log.error("__on_gateway_login_subdev_reply process raise exception:%s" % e)
        elif message.topic == self.__gateway_topic_logout_subdev_reply:
            try:
                payload = self.__load_json(message.payload)
                request_id = payload["id"]
                code = payload["code"]
                data = payload["data"]
                msg = payload["message"]
                self.__back_thing_request_id(request_id)
                if self.__on_gateway_logout_subdev_reply is not None:
                    triggered_flag = 1
                    self.__on_gateway_logout_subdev_reply(request_id, code, data, msg, self.__user_data)
            except Exception as e:
                self.__link_log.error("__on_gateway_logout_subdev_reply process raise exception:%s" % e)
        elif message.topic == self.__gateway_topic_register_subdev_reply:
            try:
                payload = self.__load_json(message.payload)
                request_id = payload["id"]
                code = payload["code"]
                data = payload["data"]
                msg = payload["message"]
                self.__back_thing_request_id(request_id)
                if self.__on_gateway_register_subdev_reply is not None:
                    triggered_flag = 1
                    self.__on_gateway_register_subdev_reply(request_id, code, data, msg, self.__user_data)
            except Exception as e:
                self.__link_log.error("__on_gateway_register_subdev_reply process raise exception:%s" % e)
        elif message.topic == self.__gateway_topic_product_register_subdev_reply:
            try:
                payload = self.__load_json(message.payload)
                request_id = payload["id"]
                code = payload["code"]
                data = payload["data"]
                msg = payload["message"]
                self.__back_thing_request_id(request_id)
                if self.__on_gateway_product_register_subdev_reply is not None:
                    triggered_flag = 1
                    self.__on_gateway_product_register_subdev_reply(request_id, code, data, msg, self.__user_data)
            except Exception as e:
                self.__link_log.error("__on_gateway_product_register_subdev_reply process raise exception:%s" % e)
        elif message.topic == self.__dynamic_register_topic:
            try:
                payload = self.__load_json(message.payload)
                device_secret = payload["deviceSecret"]
                self.disconnect()
                self.__dynamic_register_flag = 0
                if self.__on_device_dynamic_register is not None:
                    triggered_flag = 1
                    self.__on_device_dynamic_register(LinkKit.ErrorCode.SUCCESS.value, device_secret, None)
            except Exception as e:
                self.__link_log.error("__on_device_dynamic_register process raise exception:%s" % e)

        elif message.topic == self.__dynamic_register_nwl_topic:
            # 一型一密免动态注册获取到username和token
            try:
                payload = self.__load_json(message.payload)
                client_id = payload["clientId"]
                client_id = client_id + "|authType=connwl,securemode=-2,_ss=1,ext=3,lan=%s,_v=%s|" % (
                    self.__sdk_program_language,
                    self.__sdk_version,
                )
                product_key = payload["productKey"]
                device_name = payload["deviceName"]
                username = device_name + "&" + product_key
                password = payload["deviceToken"]
                self.disconnect()
                self.__dynamic_register_nwl_flag = 0
                if self.__on_device_dynamic_register_nwl_reply is not None:
                    triggered_flag = 1
                    self.__on_device_dynamic_register_nwl_reply(
                        LinkKit.ErrorCode.SUCCESS.value, client_id, username, password
                    )
            except Exception as e:
                self.__link_log.error("__on_device_dynamic_register_nwl_reply process raise exception:%s" % e)
        elif message.topic == self.__ota_push_topic or message.topic == self.__ota_pull_reply_topic:
            try:
                payload = json.loads(self.__to_str(message.payload))
                data = payload.setdefault("data", "")

                json_data = json.dumps(data)
                download_info = json.loads(str(json_data))

                url = download_info.setdefault("url", "")
                version = download_info.setdefault("version", "")
                size = download_info.setdefault("size", "")
                sign_method = download_info.setdefault("signMethod", "")
                sign = download_info.setdefault("sign", "")
                extra = download_info.setdefault("extData", "")
                module = download_info.setdefault("module", "default")

                if (
                    not self.__is_valid_str(url)
                    or not self.__is_valid_str(version)
                    or not self.__is_valid_str(size)
                    or not self.__is_valid_str(sign_method)
                    or not self.__is_valid_str(sign)
                ):
                    self.__link_log.error("invalid download params")
                    return

                ota_notice_type = 0
                if message.topic == self.__ota_push_topic:
                    ota_notice_type = 1
                else:
                    ota_notice_type = 2

                if self.__on_ota_message_arrived is not None:
                    triggered_flag = 1
                    self.__on_ota_message_arrived(
                        ota_notice_type, version, size, url, sign_method, sign, module, str(extra)
                    )
            except Exception as e:
                self.__link_log.error("__on_ota_message_arrived process raise exception:%s" % e)

        if triggered_flag == 1:
            return

        if self.__on_topic_message is not None:
            try:
                self.__on_topic_message(message.topic, message.payload, message.qos, self.__user_data)
            except Exception as e:
                self.__link_log.error("on_topic_message process raise exception:%s" % e)
        else:
            self.__link_log.error("receive unscubscibe topic : %s" % message.topic)

    def query_ota_firmware(self, module=None):
        request_id = self.__get_thing_request_id()
        if request_id is None:
            request_id = "1"

        if self.__is_valid_str(module):
            payload = '{"id": %s, "params": {"module": "%s"}}' % (request_id, module)
        else:
            payload = '{"id": %s, "params": {}}' % request_id

        rc = self.__mqtt_client.publish(self.__ota_pull_topic, payload, 0)
        if rc == mqtt.MQTT_ERR_SUCCESS:
            return 0
        else:
            return LinkKit.ErrorCode.OTA_PUB_FAILED

    def __cal_file_sign(self, filename, sign_method):
        if sign_method == "Md5":
            hash_tool = hashlib.md5()
        elif sign_method == "SHA256":
            hash_tool = hashlib.sha256()
        else:
            return LinkKit.ErrorCode.OTA_INVALID_SIGN_METHOD, -1

        with open(filename, "rb") as f:
            while True:
                chunk = f.read(4096)
                if not chunk:
                    break
                hash_tool.update(chunk)
        return LinkKit.ErrorCode.SUCCESS, hash_tool.hexdigest()

    def ota_report_version(self, module, version):
        if not self.__is_valid_str(version):
            return LinkKit.ErrorCode.OTA_INVALID_PARAM

        request_id = "1"
        if self.__is_valid_str(module):
            payload = '{"id": %s,"params": {"version":"%s","module": "%s"}}' % (request_id, version, module)
        else:
            payload = '{"id": %s, "params": {"version": "%s"}}' % (request_id, version)

        rc = self.__mqtt_client.publish(self.__ota_report_version_topic, payload, 0)
        if rc == mqtt.MQTT_ERR_SUCCESS:
            return LinkKit.ErrorCode.SUCCESS
        else:
            return LinkKit.ErrorCode.OTA_PUB_FAILED

    def download_ota_firmware(self, url, local_path, sign_method, sign, download_step=10 * 1024):
        if (
            not self.__is_valid_str(url)
            or not self.__is_valid_str(local_path)
            or not self.__is_valid_str(sign_method)
            or not self.__is_valid_str(sign)
        ):
            return LinkKit.ErrorCode.OTA_INVALID_PARAM

        context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cadata=self.__aliyun_broker_ca_data)

        try:
            conn = urllib.request.urlopen(url, context=context)
        except Exception as e:
            # Return code error (e.g. 404, 501, ...)
            self.__link_log.error("HTTPError: {} %s" % e)
            return LinkKit.ErrorCode.OTA_INVALID_URL
        else:
            # 200
            self.__link_log.info("https return 200")

            try:
                file = open(local_path, "wb")
            except OSError as e:
                self.__link_log.error("open file error: {}" + e.filename)
                return LinkKit.ErrorCode.OTA_INVALID_PATH
            else:
                # Download ota file
                with file:
                    while True:
                        try:
                            data = conn.read(download_step)
                        except Exception as e:
                            self.__link_log.error("download exception %s" % e)
                            return LinkKit.ErrorCode.OTA_DOWNLOAD_FAIL
                        else:
                            if len(data) <= 0:
                                break
                            else:
                                file.write(data)

                # Compare checksum
                ret, firmware_sign = self.__cal_file_sign(local_path, sign_method)
                if ret == LinkKit.ErrorCode.SUCCESS and firmware_sign == sign:
                    self.__link_log.info("sign match")
                    return LinkKit.ErrorCode.SUCCESS
                else:
                    self.__link_log.error("sign mismatch, expect:" + firmware_sign + ", actually:" + sign)
                    return LinkKit.ErrorCode.OTA_DIGEST_MISMATCH

    def __parse_raw_topic(self, topic):
        return re.search("/ext/rrpc/.*?(/.*)", topic).group(1)

    def __tidy_topic(self, topic):
        if topic == None:
            return None
        topic = topic.strip()
        if len(topic) == 0:
            return None
        if topic[0] != "/":
            topic = "/" + topic
        return topic

    def __push_rrpc_service(self, item) -> None:
        with self.__user_rrpc_request_ids_lock:
            if len(self.__user_rrpc_request_ids) > self.__user_rrpc_request_max_len:
                removed_item = self.__user_rrpc_request_ids.pop(0)
                del self.__user_rrpc_request_id_index_map[removed_item["id"]]

        self.__user_rrpc_request_ids.append(item)
        self.__user_rrpc_request_id_index_map[item["id"]] = 0

    def __pop_rrpc_service(self, id):
        with self.__user_rrpc_request_ids_lock:
            if id not in self.__user_rrpc_request_id_index_map:
                return None
            del self.__user_rrpc_request_id_index_map[id]
            for index in range(len(self.__user_rrpc_request_ids)):
                item = self.__user_rrpc_request_ids[index]
                if item["id"] == id:
                    del self.__user_rrpc_request_ids[index]
                    return item
            return None

    def thing_answer_rrpc(self, id, response):
        item = self.__pop_rrpc_service("rrpc_" + id)
        if item == None:
            self.__link_log.error("answer_rrpc_topic, the id does not exist: %s" % id)
            return 1, None
        rc, mid = self.__mqtt_client.publish(item["topic"], response, 0)
        self.__link_log.debug("reply topic:%s" % item["topic"])
        return rc, mid

    def __try_parse_rrpc_topic(self, message):
        self.__link_log.debug("receive a rrpc topic:%s" % message.topic)
        raw_topic = self.__parse_raw_topic(message.topic)
        triggered = 0
        # if it is a service, log it...
        if raw_topic.startswith("/sys") and raw_topic in self.__thing_topic_services:
            identifier = raw_topic.split("/", 6)[6]
            payload = self.__load_json(self.__to_str(message.payload))
            try:
                request_id = payload["id"]
                params = payload["params"]
                item_id = "alink_" + request_id
                item = {
                    "id": item_id,
                    "request_id": request_id,
                    "payload": payload,
                    "identifier": identifier,
                    "topic": message.topic,
                }
                self.__push_rrpc_service(item)
                if self.__on_thing_call_service is not None:
                    triggered = 1
                    self.__on_thing_call_service(identifier, request_id, params, self.__user_data)
            except Exception as e:
                self.__link_log.error("on_thing_call_service raise exception: %s" % e)
            return triggered

        # parse
        with self.__user_rrpc_topics_subscribe_request_lock:
            with self.__user_rrpc_topics_lock:
                if raw_topic not in self.__user_rrpc_topics:
                    self.__link_log.error("%s is not in the rrpc-subscribed list" % raw_topic)
                    return
        if not self.__on_topic_rrpc_message:
            return
        try:
            rrpc_id = message.topic.split("/", 4)[3]
            item_id = "rrpc_" + rrpc_id
            item = {"id": item_id, "payload": message.payload, "topic": message.topic}
            self.__push_rrpc_service(item)
            self.__on_topic_rrpc_message(rrpc_id, message.topic, message.payload, message.qos, self.__user_data)
            # self.__mqtt_client.publish(message.topic, response, 0)
            # self.__link_log.debug('reply topic:%s' % message.topic)
        except Exception as e:
            self.__link_log.error("on_topic_rrpc_message process raise exception:%r" % e)

    def __try_parse_try_shadow(self, payload) -> None:
        try:
            self.__latest_shadow.set_latest_recevied_time(self.__timestamp())
            self.__latest_shadow.set_latest_recevied_payload(payload)

            # parse the pay load
            msg = self.__load_json(payload)
            # set version
            if "version" in msg:
                self.__latest_shadow.set_version(msg["version"])
            elif "payload" in msg and "version" in msg["payload"]:
                self.__latest_shadow.set_version(msg["payload"]["version"])

            # set timestamp
            if "timestamp" in msg:
                self.__latest_shadow.set_timestamp(msg["timestamp"])
            elif "payload" in msg and "timestamp" in msg["payload"]:
                self.__latest_shadow.set_timestamp(msg["payload"]["timestamp"])

            # set state and metadata
            if "payload" in msg and msg["payload"]["status"] == "success":
                if "state" in msg["payload"]:
                    self.__latest_shadow.set_state(msg["payload"]["state"])
                if "metadata" in msg["payload"]:
                    self.__latest_shadow.set_metadata(msg["payload"]["metadata"])
        except Exception:
            pass

    def thing_update_shadow(self, reported, version):
        request = {"state": {"reported": reported}, "method": "update", "version": version}
        return self.__thing_update_shadow(request)

    def thing_get_shadow(self):
        request = {"method": "get"}
        return self.__thing_update_shadow(request)

    def local_get_latest_shadow(self):
        return self.__latest_shadow

    def __thing_update_shadow(self, request):
        if self.__linkkit_state is not LinkKit.LinkKitState.CONNECTED:
            self.__link_log.error("disconnected, update shadow fail")
            return LinkKit.ErrorCode.NETWORK_DISCONNECTED.value, None
        if not self.__thing_setup_state or not self.__thing_enable_state:
            return 1, None
        with self.__thing_shadow_mid_lock:
            rc, mid = self.__mqtt_client.publish(self.__thing_topic_shadow_update, json.dumps(request), 1)
            if rc == mqtt.MQTT_ERR_SUCCESS:
                self.__thing_shadow_mid[mid] = self.__timestamp()
                return 0, mid
            else:
                return 1, None

    def __on_internal_message(self, client, user_data, message) -> None:
        self.__link_log.info("__on_internal_message")
        self.__handler_task.post_message(self.__handler_task_cmd_on_message, (client, user_data, message))
        # self.__worker_thread.async_post_message(message)

    def __handler_task_on_message_callback(self, value) -> None:
        client, user_data, message = value
        self.__on_internal_async_message(message)

    def __on_internal_connect(self, client, user_data, session_flag, rc) -> None:
        self.__link_log.info("__on_internal_connect")
        if rc == 0:
            self.__reset_reconnect_wait()
            # self.__upload_device_interface_info()
            self.__handler_task.post_message(self.__handler_task_cmd_on_connect, (client, user_data, session_flag, rc))

    def __handler_task_on_connect_callback(self, value) -> None:
        client, user_data, session_flag, rc = value
        self.__link_log.info("__on_internal_connect enter")
        self.__link_log.debug("session:%d, return code:%d" % (session_flag["session present"], rc))
        if rc == 0:
            self.__linkkit_state = LinkKit.LinkKitState.CONNECTED
            # self.__worker_thread.start()
        if self.__on_connect is not None:
            try:
                self.__on_connect(session_flag["session present"], rc, self.__user_data)
            except Exception as e:
                self.__link_log.error("on_connect process raise exception:%r" % e)
        if self.__thing_setup_state:
            self.__thing_enable_state = True
            if self.__on_thing_enable:
                self.__on_thing_enable(self.__user_data)

    def __on_internal_disconnect(self, client, user_data, rc) -> None:
        self.__link_log.info("__on_internal_disconnect enter")
        if self.__linkkit_state == LinkKit.LinkKitState.DESTRUCTING:
            self.__linkkit_state = LinkKit.LinkKitState.DESTRUCTED
        elif (
            self.__linkkit_state == LinkKit.LinkKitState.DISCONNECTING
            or self.__linkkit_state == LinkKit.LinkKitState.CONNECTED
        ):
            self.__linkkit_state = LinkKit.LinkKitState.DISCONNECTED
        elif self.__linkkit_state == LinkKit.LinkKitState.DISCONNECTED:
            self.__link_log.error("__on_internal_disconnect enter from wrong state:%r" % self.__linkkit_state)
            return
        else:
            self.__link_log.error("__on_internal_disconnect enter from wrong state:%r" % self.__linkkit_state)

            return
        self.__user_topics.clear()
        self.__user_topics_subscribe_request.clear()
        self.__user_topics_unsubscribe_request.clear()

        self.__user_rrpc_topics.clear()
        self.__user_rrpc_topics_subscribe_request.clear()
        self.__user_rrpc_topics_unsubscribe_request.clear()

        self.__thing_prop_post_mid.clear()
        self.__thing_event_post_mid.clear()
        self.__thing_answer_service_mid.clear()
        self.__thing_raw_down_reply_mid.clear()
        self.__thing_raw_up_mid.clear()
        self.__thing_shadow_mid.clear()
        self.__device_info_mid.clear()
        self.__thing_update_device_info_up_mid.clear()
        self.__thing_delete_device_info_up_mid.clear()
        self.__handler_task.post_message(self.__handler_task_cmd_on_disconnect, (client, user_data, rc))
        if self.__linkkit_state == LinkKit.LinkKitState.DESTRUCTED:
            self.__handler_task.stop()

    def __handler_task_on_disconnect_callback(self, value) -> None:
        self.__link_log.info("__handler_task_on_disconnect_callback enter")
        client, user_data, rc = value
        if self.__thing_setup_state:
            if self.__thing_enable_state:
                self.__thing_enable_state = False
                if self.__on_thing_disable is not None:
                    try:
                        self.__on_thing_disable(self.__user_data)
                    except Exception as e:
                        self.__link_log.error("on_thing_disable process raise exception:%r" % e)
        if self.__on_disconnect is not None:
            try:
                self.__on_disconnect(rc, self.__user_data)
            except Exception as e:
                self.__link_log.error("on_disconnect process raise exception:%r" % e)

    def __on_internal_publish(self, client, user_data, mid) -> None:
        self.__handler_task.post_message(self.__handler_task_cmd_on_publish, (client, user_data, mid))

    def __gateway_add_subdev_topo(self, subdev_array):
        request_params = []
        for subdev in subdev_array:
            ret = self.__validate_subdev_param(subdev, 3)
            if ret != 0:
                return ret, None

            pk = subdev[0]
            dn = subdev[1]
            ds = subdev[2]
            millis = str(self.__timestamp())
            client_id = pk + "." + dn

            sign_content = "clientId%sdeviceName%sproductKey%stimestamp%s" % (client_id, dn, pk, millis)
            sign = hmac.new(ds.encode("utf-8"), sign_content.encode("utf-8"), hashlib.sha256).hexdigest()
            params = {
                "productKey": pk,
                "deviceName": dn,
                "clientId": client_id,
                "timestamp": millis,
                "signmethod": "hmacSha256",
                "sign": sign,
            }
            request_params.append(params)
        request_id = self.__get_thing_request_id()
        if request_id is None:
            return 1, None
        request = {
            "id": request_id,
            "version": "1.0",
            "params": request_params,
        }
        with self.__gateway_add_subdev_topo_mid_lock:
            rc, mid = self.__mqtt_client.publish(self.__gateway_topic_add_subdev_topo, json.dumps(request), 1)
            if rc == mqtt.MQTT_ERR_SUCCESS:
                self.__gateway_add_subdev_topo_mid[mid] = self.__timestamp()
                return 0, request_id
            else:
                return 1, None

    def gateway_add_subdev_topo(self, subdev_array):
        return self.__gateway_add_subdev_topo(subdev_array)

    def __validate_subdev_param(self, subdev, expected_len):
        if subdev is None:
            return LinkKit.ErrorCode.NULL_SUBDEV_ERR.value
        if not isinstance(subdev, list):
            return LinkKit.ErrorCode.SUBDEV_NOT_ARRAY_ERR.value
        if len(subdev) < expected_len:
            self.__link_log.error("input subdev length mismatch")
            return LinkKit.ErrorCode.ARRAY_LENGTH_ERR.value
        else:
            return LinkKit.ErrorCode.SUCCESS.value

    def __gateway_delete_subdev_topo(self, subdev_array):
        request_params = []
        for subdev in subdev_array:
            ret = self.__validate_subdev_param(subdev, 2)
            if ret != 0:
                return ret, None

            pk = subdev[0]
            dn = subdev[1]

            params = {
                "productKey": pk,
                "deviceName": dn,
            }
            request_params.append(params)
        request_id = self.__get_thing_request_id()
        if request_id is None:
            return 1, None
        request = {
            "id": request_id,
            "version": "1.0",
            "params": request_params,
        }
        with self.__gateway_delete_subdev_topo_mid_lock:
            rc, mid = self.__mqtt_client.publish(self.__gateway_topic_delete_subdev_topo, json.dumps(request), 1)
            if rc == mqtt.MQTT_ERR_SUCCESS:
                self.__gateway_delete_subdev_topo_mid[mid] = self.__timestamp()
                return 0, request_id
            else:
                return 1, None

    def gateway_delete_subdev_topo(self, subdev_array):
        return self.__gateway_delete_subdev_topo(subdev_array)

    def __gateway_login_subdev(self, subdev_array):
        device_list = []
        for subdev in subdev_array:
            ret = self.__validate_subdev_param(subdev, 3)
            if ret != 0:
                return ret, None

            pk = subdev[0]
            dn = subdev[1]
            ds = subdev[2]
            millis = str(self.__timestamp())
            client_id = pk + "." + dn + "|lan=Python,_v=2.2.1,_ss=1|"

            sign_content = "clientId%sdeviceName%sproductKey%stimestamp%s" % (client_id, dn, pk, millis)
            sign = hmac.new(ds.encode("utf-8"), sign_content.encode("utf-8"), hashlib.sha256).hexdigest()
            dev_params = {
                "productKey": pk,
                "deviceName": dn,
                "clientId": client_id,
                "timestamp": millis,
                "cleanSession": "false",
                "sign": sign,
            }
            device_list.append(dev_params)
        request_params = {
            "signMethod": "hmacSha256",
            "deviceList": device_list,
        }
        request_id = self.__get_thing_request_id()
        if request_id is None:
            return 1, None
        request = {
            "id": request_id,
            "version": "1.0",
            "params": request_params,
        }
        rc, mid = self.__mqtt_client.publish(self.__gateway_topic_login_subdev, json.dumps(request), 0)
        if rc == mqtt.MQTT_ERR_SUCCESS:
            return 0, request_id
        else:
            return 1, None

    def gateway_login_subdev(self, subdev_array):
        return self.__gateway_login_subdev(subdev_array)

    def gateway_logout_subdev(self, subdev_array):
        return self.__gateway_logout_subdev(subdev_array)

    def __gateway_logout_subdev(self, subdev_array):
        request_params = []
        for subdev in subdev_array:
            ret = self.__validate_subdev_param(subdev, 2)
            if ret != 0:
                return ret, None

            pk = subdev[0]
            dn = subdev[1]

            params = {
                "productKey": pk,
                "deviceName": dn,
            }
            request_params.append(params)
        request_id = self.__get_thing_request_id()
        if request_id is None:
            return 1, None
        request = {
            "id": request_id,
            "version": "1.0",
            "params": request_params,
        }
        rc, mid = self.__mqtt_client.publish(self.__gateway_topic_logout_subdev, json.dumps(request), 0)
        if rc == mqtt.MQTT_ERR_SUCCESS:
            return 0, request_id
        else:
            return 1, None

    def __gateway_register_subdev(self, subdev_array):
        request_params = []
        for subdev in subdev_array:
            ret = self.__validate_subdev_param(subdev, 2)
            if ret != 0:
                return ret, None

            pk = subdev[0]
            dn = subdev[1]

            params = {
                "productKey": pk,
                "deviceName": dn,
            }
            request_params.append(params)
        request_id = self.__get_thing_request_id()
        if request_id is None:
            return 1, None
        request = {
            "id": request_id,
            "version": "1.0",
            "params": request_params,
        }
        rc, mid = self.__mqtt_client.publish(self.__gateway_topic_register_subdev, json.dumps(request), 0)
        if rc == mqtt.MQTT_ERR_SUCCESS:
            return 0, request_id
        else:
            return 1, None

    def gateway_register_subdev(self, subdev_array):
        return self.__gateway_register_subdev(subdev_array)

    def gateway_product_register_subdev(self, subdev_array):
        return self.__gateway_product_register_subdev(subdev_array)

    def __gateway_product_register_subdev(self, subdev_array):
        device_list = []
        for subdev in subdev_array:
            ret = self.__validate_subdev_param(subdev, 3)
            if ret != 0:
                return ret, None

            pk = subdev[0]
            dn = subdev[1]
            ps = subdev[2]
            random_str = self.__generate_random_str(15)

            sign_content = "deviceName%sproductKey%srandom%s" % (dn, pk, random_str)
            sign = hmac.new(ps.encode("utf-8"), sign_content.encode("utf-8"), hashlib.sha256).hexdigest()
            dev_params = {
                "productKey": pk,
                "deviceName": dn,
                "random": random_str,
                "signMethod": "hmacSha256",
                "sign": sign,
            }
            device_list.append(dev_params)
        request_params = {
            "proxieds": device_list,
        }
        request_id = self.__get_thing_request_id()
        if request_id is None:
            return 1, None
        request = {
            "id": request_id,
            "version": "1.0",
            "params": request_params,
        }
        rc, mid = self.__mqtt_client.publish(self.__gateway_topic_product_register_subdev, json.dumps(request), 0)
        if rc == mqtt.MQTT_ERR_SUCCESS:
            self.__link_log.debug("mid for product dynamic register:%d" % mid)
            return 0, request_id
        else:
            return 1, None

    def __handler_task_on_publish_callback(self, value) -> None:
        client, user_data, mid = value
        self.__link_log.debug("__on_internal_publish message:%d" % mid)
        with self.__thing_event_post_mid_lock:
            if mid in self.__thing_event_post_mid:
                self.__thing_event_post_mid.pop(mid)
                self.__link_log.debug("__on_internal_publish event post mid removed")
                return
        with self.__thing_prop_post_mid_lock:
            if mid in self.__thing_prop_post_mid:
                self.__thing_prop_post_mid.pop(mid)
                self.__link_log.debug("__on_internal_publish prop post mid removed")
                return
        with self.__thing_prop_set_reply_mid_lock:
            if mid in self.__thing_prop_set_reply_mid:
                self.__thing_prop_set_reply_mid.pop(mid)
                self.__link_log.debug("__on_internal_publish prop set reply mid removed")
                return
        with self.__thing_answer_service_mid_lock:
            if mid in self.__thing_answer_service_mid:
                self.__thing_answer_service_mid.pop(mid)
                self.__link_log.debug("__thing_answer_service_mid mid removed")
                return
        with self.__thing_raw_up_mid_lock:
            if mid in self.__thing_raw_up_mid:
                self.__thing_raw_up_mid.pop(mid)
                self.__link_log.debug("__thing_raw_up_mid mid removed")
                return
        with self.__thing_raw_down_reply_mid_lock:
            if mid in self.__thing_raw_down_reply_mid:
                self.__thing_raw_down_reply_mid.pop(mid)
                self.__link_log.debug("__thing_raw_down_reply_mid mid removed")
                return
        with self.__device_info_mid_lock:
            if mid in self.__device_info_mid:
                self.__device_info_mid.pop(mid)
                self.__link_log.debug("__device_info_mid mid removed")
                return
        with self.__thing_shadow_mid_lock:
            if mid in self.__thing_shadow_mid:
                self.__thing_shadow_mid.pop(mid)
                self.__link_log.debug("__thing_shadow_mid mid removed")
                return
        with self.__thing_update_device_info_up_mid_lock:
            if mid in self.__thing_update_device_info_up_mid:
                self.__thing_update_device_info_up_mid.pop(mid)
                self.__link_log.debug("__thing_update_device_info_up_mid mid removed")
                return
        with self.__thing_delete_device_info_up_mid_lock:
            if mid in self.__thing_delete_device_info_up_mid:
                self.__thing_delete_device_info_up_mid.pop(mid)
                self.__link_log.debug("__thing_delete_device_info_up_mid mid removed")
                return
        with self.__gateway_add_subdev_topo_mid_lock:
            if mid in self.__gateway_add_subdev_topo_mid:
                self.__gateway_add_subdev_topo_mid.pop(mid)
                self.__link_log.debug("__gateway_add_subdev_topo_mid removed")
                return
        with self.__gateway_delete_subdev_topo_mid_lock:
            if mid in self.__gateway_delete_subdev_topo_mid:
                self.__gateway_delete_subdev_topo_mid.pop(mid)
                self.__link_log.debug("__gateway_delete_subdev_topo_mid removed")
                return
        if self.__on_publish_topic is not None:
            self.__on_publish_topic(mid, self.__user_data)

    def __on_internal_subscribe(self, client, user_data, mid, granted_qos) -> None:
        self.__handler_task.post_message(self.__handler_task_cmd_on_subscribe, (client, user_data, mid, granted_qos))

    def __handler_task_on_subscribe_callback(self, value) -> None:
        client, user_data, mid, granted_qos = value
        self.__link_log.debug(
            "__on_internal_subscribe mid:%d  granted_qos:%s" % (mid, str(",".join("%s" % it for it in granted_qos)))
        )
        # try to read rrpc
        with self.__user_rrpc_topics_subscribe_request_lock:
            if mid in self.__user_rrpc_topics_subscribe_request:
                self.__user_rrpc_topics_subscribe_request.pop(mid)
                if self.__on_subscribe_rrpc_topic:
                    try:
                        self.__on_subscribe_rrpc_topic(mid, granted_qos, self.__user_data)
                    except Exception as err:
                        self.__link_log.error("Caught exception in on_subscribe_topic: %s", err)
                return

        # try to read other topic
        topics_requests = None
        self.__user_topics_request_lock.acquire()
        if mid in self.__user_topics_subscribe_request:
            topics_requests = self.__user_topics_subscribe_request.pop(mid)
        self.__user_topics_request_lock.release()
        if topics_requests is not None:
            return_topics = []
            for index in range(len(topics_requests)):
                if granted_qos[index] < 0 or granted_qos[index] > 1:
                    self.__link_log.error("topics:%s, granted wrong:%d" % (topics_requests[index], granted_qos[index]))
                else:
                    self.__user_topics[topics_requests[index][0]] = granted_qos[index]
                return_topics.append((topics_requests[index], granted_qos[index]))
        if self.__on_subscribe_topic is not None:
            try:
                self.__on_subscribe_topic(mid, granted_qos, self.__user_data)
            except Exception as err:
                self.__link_log.error("Caught exception in on_subscribe_topic: %s", err)

    def __on_internal_unsubscribe(self, client, user_data, mid) -> None:
        self.__handler_task.post_message(self.__handler_task_cmd_on_unsubscribe, (client, user_data, mid))

    def __handler_task_on_unsubscribe_callback(self, value) -> None:
        client, user_data, mid = value
        self.__link_log.debug("__on_internal_unsubscribe mid:%d" % mid)
        unsubscribe_request = None
        # try to read rrpc
        with self.__user_rrpc_topics_unsubscribe_request_lock:
            if mid in self.__user_rrpc_topics_unsubscribe_request:
                self.__user_rrpc_topics_unsubscribe_request.pop(mid)
                if self.__on_unsubscribe_rrpc_topic:
                    try:
                        self.__on_unsubscribe_rrpc_topic(mid, self.__user_data)
                    except Exception as err:
                        self.__link_log.error("Caught exception in on_unsubscribe_rrpc_topic: %s", err)
                return

        with self.__user_topics_unsubscribe_request_lock:
            if mid in self.__user_topics_unsubscribe_request:
                unsubscribe_request = self.__user_topics_unsubscribe_request.pop(mid)
        if unsubscribe_request is not None:
            for t in unsubscribe_request:
                self.__link_log.debug("__user_topics:%s" % str(self.__user_topics))
                try:
                    self.__user_topics.pop(t)
                except Exception as e:
                    self.__link_log.error("__on_internal_unsubscribe e:" + str(e))
                    return
        if self.__on_unsubscribe_topic is not None:
            try:
                self.__on_unsubscribe_topic(mid, self.__user_data)
            except Exception as err:
                self.__link_log.error("Caught exception in on_unsubscribe_topic: %s", err)

    def dump_user_topics(self):
        return self.__user_topics

    def force_reconnect(self) -> None:
        self.__link_log.error("force reconnecting")
        self.__force_reconnect = True

    @staticmethod
    def to_user_topic(topic):
        topic_section = topic.split("/", 3)
        user_topic = topic_section[3]
        return user_topic

    def to_full_topic(self, topic):
        return self.__USER_TOPIC_PREFIX % (self.__product_key, self.__device_name, topic)

    def __is_valid_str(self, user_str) -> bool:
        if user_str is None or user_str == "":
            return False
        return True

    @staticmethod
    def __timestamp():
        return int(time.time() * 1000)
