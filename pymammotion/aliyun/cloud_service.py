import base64

from aliyunsdkcore import client
from aliyunsdkiot.request.v20180120.GetDeviceStatusRequest import GetDeviceStatusRequest
from aliyunsdkiot.request.v20180120.InvokeThingServiceRequest import (
    InvokeThingServiceRequest,
)


class CloudService:
    # com.aliyun.iot.aep.sdk
    # https://domestic.mammotion.com/privacy/ - lists all aliyun packages
    def __init__(self) -> None:
        self.selectDeviceIOTID = ""
        accessKeyId = "<your accessKey>"
        accessKeySecret = "<your accessSecret>"
        self.clt = client.AcsClient(accessKeyId, accessKeySecret, "ap-southeast")

    """
    String printBase64Binary = DatatypeConverter.printBase64Binary(byteArray);
        JSONObject jSONObject = new JSONObject();
        JSONObject jSONObject2 = new JSONObject();
        try {
            jSONObject2.put("content", printBase64Binary);
            jSONObject.put("args", jSONObject2);
            jSONObject.put("iotId", this.selectDeviceIOTID);
            jSONObject.put("identifier", "device_protobuf_sync_service");
        } catch (JSONException e) {
            e.printStackTrace();
        }
    
    """

    def invoke_thing_service(self, data: bytearray) -> None:
        base64_encoded = base64.b64encode(data).decode("utf-8")

        # Create a dictionary structure
        data = {
            "args": {"content": base64_encoded},
            "DEVICE_IOTID": self.selectDeviceIOTID,
            "identifier": "device_protobuf_sync_service",
        }

        request = InvokeThingServiceRequest()
        request.set_accept_format("json")

        request.set_Args("Args")
        request.set_Identifier("Identifier")
        request.set_IotId("IotId")
        request.set_ProductKey("ProductKey")

        response = self.clt.do_action_with_exception(request)
        # python2:  print(response)
        print(response)

    def get_device_status(self) -> None:
        request = GetDeviceStatusRequest()
        request.set_accept_format("json")

        request.set_IotId("IotId")
        request.set_ProductKey("ProductKey")
        request.set_DeviceName("DeviceName")

        response = self.clt.do_action_with_exception(request)
        print(response)
