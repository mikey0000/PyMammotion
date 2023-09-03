import base64
import json

class CloudService():
    
    
    def __init__(self):
        self.selectDeviceIOTID = ""
        
    
    def payload(self, data: bytearray):
        
        base64_encoded = base64.b64encode(data).decode('utf-8')

        # Create a dictionary structure
        data = {
            "args": {
                "content": base64_encoded
            },
            "DEVICE_IOTID": self.selectDeviceIOTID,
            "identifier": "device_protobuf_sync_service"
        }
        
        
    def send_payload(self):
        pass
