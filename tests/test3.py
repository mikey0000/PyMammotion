from pyluba.mammotion.commands.proto import LubaCommandProtoBLE
from pyluba.proto.luba_msg import LubaMsg
from pyluba.utility.constant.device_constant import WorkMode, device_mode

print(WorkMode.MODE_READY)

print(device_mode(3))

print(LubaCommandProtoBLE().resume_execute_task())
print(LubaMsg().parse(LubaCommandProtoBLE().resume_execute_task()).nav.todev_taskctrl)
