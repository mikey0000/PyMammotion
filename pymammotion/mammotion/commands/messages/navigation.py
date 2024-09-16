# === sendOrderMsg_Nav ===
import logging
import time
from abc import ABC

from pymammotion.data.model import GenerateRouteInformation
from pymammotion.data.model.plan import Plan
from pymammotion.data.model.region_data import RegionData
from pymammotion.mammotion.commands.abstract_message import AbstractMessage
from pymammotion.proto.luba_msg import LubaMsg, MsgAttr, MsgCmdType, MsgDevice
from pymammotion.proto.mctrl_nav import (
    AppRequestCoverPathsT,
    MctlNav,
    NavGetCommData,
    NavGetHashList,
    NavMapNameMsg,
    NavPlanJobSet,
    NavPlanTaskExecute,
    NavReqCoverPath,
    NavSysParamMsg,
    NavTaskCtrl,
    NavUnableTimeSet,
    NavUploadZigZagResultAck,
    SimulationCmdData,
    WorkReportCmdData,
    WorkReportUpdateCmd,
)
from pymammotion.utility.device_type import DeviceType

logger = logging.getLogger(__name__)


class MessageNavigation(AbstractMessage, ABC):
    def get_msg_device(self, msg_type: MsgCmdType, msg_device: MsgDevice) -> MsgDevice:
        """Changes the rcver name if it's not a luba1."""
        if (
            not DeviceType.is_luba1(self.get_device_name(), self.get_device_product_key())
            and msg_type == MsgCmdType.MSG_CMD_TYPE_NAV
        ):
            return MsgDevice.DEV_NAVIGATION
        return msg_device

    def send_order_msg_nav(self, build) -> bytes:
        luba_msg = LubaMsg(
            msgtype=MsgCmdType.MSG_CMD_TYPE_NAV,
            sender=MsgDevice.DEV_MOBILEAPP,
            rcver=self.get_msg_device(MsgCmdType.MSG_CMD_TYPE_NAV, MsgDevice.DEV_MAINCTL),
            msgattr=MsgAttr.MSG_ATTR_REQ,
            seqs=1,
            version=1,
            subtype=1,
            nav=build,
            timestamp=round(time.time() * 1000),
        )

        return luba_msg.SerializeToString()

    def allpowerfull_rw_adapter_x3(self, id: int, context: int, rw: int) -> bytes:
        build = MctlNav(nav_sys_param_cmd=NavSysParamMsg(id=id, context=context, rw=rw))
        logger.debug(f"Send command--9 general read and write command id={id}, context={context}, rw={rw}")
        return self.send_order_msg_nav(build)

    def along_border(self) -> bytes:
        build = MctlNav(todev_edgecmd=1)
        logger.debug("Send command--along the edge command")
        return self.send_order_msg_nav(build)

    def start_draw_border(self) -> bytes:
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=0, type=0))
        logger.debug("Send command--Start drawing boundary command")
        return self.send_order_msg_nav(build)

    def enter_dumping_status(self) -> bytes:
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=14, type=12))
        logger.debug("Send command--Enter grass collection status")
        return self.send_order_msg_nav(build)

    def add_dump_point(self) -> bytes:
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=0, type=12))
        logger.debug("Send command--Add grass collection point")
        return self.send_order_msg_nav(build)

    def revoke_dump_point(self) -> bytes:
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=6, type=12))
        logger.debug("Send command--Revoke grass collection point")
        return self.send_order_msg_nav(build)

    def exit_dumping_status(self) -> bytes:
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=1, type=12))
        logger.debug("Send command--Exit grass collection setting status")
        return self.send_order_msg_nav(build)

    def out_drop_dumping_add(self) -> bytes:
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=15, type=12))
        logger.debug("Send command--Complete external grass collection point marking operation")
        return self.send_order_msg_nav(build)

    def recover_dumping(self) -> bytes:
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=12, type=12))
        logger.debug("Send command--Recover grass collection operation")
        return self.send_order_msg_nav(build)

    def start_draw_barrier(self) -> bytes:
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=0, type=1))
        logger.debug("Sending command - Draw obstacle command")
        return self.send_order_msg_nav(build)

    def start_erase(self) -> bytes:
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=4, type=0))
        logger.debug("Sending command - Start erase command - Bluetooth")
        return self.send_order_msg_nav(build)

    def end_erase(self) -> bytes:
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=5, type=0))
        logger.debug("Sending command - End erase command")
        return self.send_order_msg_nav(build)

    def cancel_erase(self) -> bytes:
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=7, type=0))
        logger.debug("Sending command - Cancel erase command")
        return self.send_order_msg_nav(build)

    def start_channel_line(self) -> bytes:
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=0, type=2))
        logger.debug("Sending command - Start drawing channel line command")
        return self.send_order_msg_nav(build)

    def save_task(self) -> bytes:
        build = MctlNav(todev_save_task=1)
        logger.debug("Sending command - Save task command")
        return self.send_order_msg_nav(build)

    def set_edit_boundary(self, action: int) -> bytes:
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=action, type=0))
        logger.debug(f"Sending secondary editing command action={action}")
        return self.send_order_msg_nav(build)

    def set_data_synchronization(self, type: int) -> bytes:
        logger.debug(f"Sync data ==================== Sending ============ Restore command: {type}")
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=12, type=type))
        logger.debug("Sync data ==================== Sending ============ Restore command")
        return self.send_order_msg_nav(build)

    def send_plan(self, plan_bean: Plan) -> bytes:
        build = MctlNav(
            todev_planjob_set=NavPlanJobSet(
                pver=plan_bean.pver,
                sub_cmd=plan_bean.sub_cmd,
                area=plan_bean.area,
                work_time=plan_bean.work_time,
                version=plan_bean.version,
                id=plan_bean.id,
                user_id=plan_bean.user_id,
                device_id=plan_bean.device_id,
                plan_id=plan_bean.plan_id,
                task_id=plan_bean.task_id,
                job_id=plan_bean.job_id,
                start_time=plan_bean.start_time,
                end_time=plan_bean.end_time,
                week=plan_bean.week,
                knife_height=plan_bean.knife_height,
                model=plan_bean.model,
                edge_mode=plan_bean.edge_mode,
                required_time=plan_bean.required_time,
                route_angle=plan_bean.route_angle,
                route_model=plan_bean.route_model,
                route_spacing=plan_bean.route_spacing,
                ultrasonic_barrier=plan_bean.ultrasonic_barrier,
                total_plan_num=plan_bean.total_plan_num,
                plan_index=plan_bean.plan_index,
                result=plan_bean.result,
                speed=plan_bean.speed,
                task_name=plan_bean.task_name,
                job_name=plan_bean.job_name,
                zone_hashs=plan_bean.zone_hashs,
                reserved=plan_bean.reserved,
            )
        )
        logger.debug(f"Send read job plan command planBean={plan_bean}")
        return self.send_order_msg_nav(build)

    def send_schedule(self, plan_bean: Plan) -> bytes:
        build = NavPlanJobSet(
            pver=plan_bean.pver,
            sub_cmd=plan_bean.sub_cmd,
            area=plan_bean.area,
            device_id=plan_bean.device_id,
            work_time=plan_bean.work_time,
            version=plan_bean.version,
            id=plan_bean.id,
            user_id=plan_bean.user_id,
            plan_id=plan_bean.plan_id,
            task_id=plan_bean.task_id,
            job_id=plan_bean.job_id,
            start_time=plan_bean.start_time,
            end_time=plan_bean.end_time,
            week=plan_bean.week,
            knife_height=plan_bean.knife_height,
            model=plan_bean.model,
            edge_mode=plan_bean.edge_mode,
            required_time=plan_bean.required_time,
            route_angle=plan_bean.route_angle,
            route_model=plan_bean.route_model,
            route_spacing=plan_bean.route_spacing,
            ultrasonic_barrier=plan_bean.ultrasonic_barrier,
            total_plan_num=plan_bean.total_plan_num,
            plan_index=plan_bean.plan_index,
            result=plan_bean.result,
            speed=plan_bean.speed,
            task_name=plan_bean.task_name,
            job_name=plan_bean.job_name,
            zone_hashs=plan_bean.zone_hashs,
            reserved=plan_bean.reserved,
            weeks=plan_bean.weeks,
            start_date=plan_bean.start_date,
            trigger_type=plan_bean.job_type,
            day=plan_bean.interval_days,
            toward_included_angle=plan_bean.demond_angle,
            toward_mode=0,
        )
        logger.debug(f"Send read job plan command planBean={plan_bean}")
        return self.send_order_msg_nav(MctlNav(todev_planjob_set=build))

    def single_schedule(self, plan_id: str) -> bytes:
        return self.send_order_msg_nav(MctlNav(plan_task_execute=NavPlanTaskExecute(sub_cmd=1, id=plan_id)))

    def read_plan(self, sub_cmd: int, plan_index: int = 0) -> bytes:
        build = MctlNav(todev_planjob_set=NavPlanJobSet(sub_cmd=sub_cmd, plan_index=plan_index))
        logger.debug(f"Send read job plan command cmd={sub_cmd} PlanIndex = {plan_index}")
        return self.send_order_msg_nav(build)

    def delete_plan(self, sub_cmd: int, plan_id: str) -> bytes:
        build = MctlNav(todev_planjob_set=NavPlanJobSet(sub_cmd=sub_cmd, plan_id=plan_id))
        logger.debug(f"Send command--Send delete job plan command cmd={sub_cmd} planId = {plan_id}")
        return self.send_order_msg_nav(build)

    def set_plan_unable_time(self, sub_cmd: int, device_id: str, unable_end_time: str, unable_start_time: str) -> bytes:
        build = NavUnableTimeSet(
            sub_cmd=sub_cmd,
            device_id=device_id,
            unable_end_time=unable_end_time,
            result=0,
            reserved="0",
            unable_start_time=unable_start_time,
        )
        logger.debug(f"{self.get_device_name()} Set forbidden time===={build}")
        return self.send_order_msg_nav(MctlNav(todev_unable_time_set=build))

    def read_plan_unable_time(self, sub_cmd: int) -> bytes:
        build = NavUnableTimeSet(sub_cmd=sub_cmd)
        build2 = MctlNav(todev_unable_time_set=build)
        logger.debug(f"Send command--Read plan time {sub_cmd}")
        return self.send_order_msg_nav(build2)

    def query_job_history(self) -> bytes:
        return self.send_order_msg_nav(MctlNav(todev_work_report_update_cmd=WorkReportUpdateCmd(sub_cmd=1)))

    def request_job_history(self, num: int) -> bytes:
        return self.send_order_msg_nav(MctlNav(todev_work_report_cmd=WorkReportCmdData(sub_cmd=1, get_info_num=num)))

    def leave_dock(self) -> bytes:
        build = MctlNav(todev_one_touch_leave_pile=1)
        logger.debug("Send command--One-click automatic undocking")
        return self.send_order_msg_nav(build)

    def get_area_name_list(self, device_id: str) -> bytes:
        # Build the NavMapNameMsg with the specified parameters
        mctl_nav = MctlNav(
            toapp_map_name_msg=NavMapNameMsg(
                hash=0,
                result=0,
                device_id=device_id,  # iotId or ???
                rw=0,
            )
        )

        # Send the message with the specified ID and acknowledge flag
        logger.debug("Send command--Get area name list")
        return self.send_order_msg_nav(mctl_nav)

    def set_area_name(self, device_id, hash_id: int, name: str) -> bytes:
        # Build the NavMapNameMsg with the specified parameters
        mctl_nav = MctlNav(
            toapp_map_name_msg=NavMapNameMsg(hash=hash_id, name=name, result=0, device_id=device_id, rw=1)
        )

        # Send the message with the specified ID and acknowledge flag
        logger.debug("Send command--Get area name list")
        return self.send_order_msg_nav(mctl_nav)

    def get_all_boundary_hash_list(self, sub_cmd: int) -> bytes:
        build = MctlNav(todev_gethash=NavGetHashList(pver=1, sub_cmd=sub_cmd))
        logger.debug(f"Area loading=====================:Get area hash list++Bluetooth:{sub_cmd}")
        return self.send_order_msg_nav(build)

    def get_hash_response(self, total_frame: int, current_frame: int) -> bytes:
        build = MctlNav(
            todev_gethash=NavGetHashList(pver=1, sub_cmd=2, current_frame=current_frame, total_frame=total_frame)
        )
        logger.debug(
            f"Send command--208 Response hash list command totalFrame={total_frame},currentFrame={current_frame}"
        )
        return self.send_order_msg_nav(build)

    def synchronize_hash_data(self, hash_num: int) -> bytes:
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=8, hash=hash_num, sub_cmd=1))
        logger.debug(f"Send command--209,hash synchronize area data hash:{hash}")
        return self.send_order_msg_nav(build)

    def get_area_to_be_transferred(self) -> bytes:
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=8, sub_cmd=1, type=3))
        logger.debug("Send command--Get transfer area before charging pile")
        return self.send_order_msg_nav(build)

    def get_regional_data(self, regional_data: RegionData) -> bytes:
        build = MctlNav(
            todev_get_commondata=NavGetCommData(
                pver=1,
                action=regional_data.action,
                type=regional_data.type,
                hash=regional_data.hash,
                total_frame=regional_data.total_frame,
                current_frame=regional_data.current_frame,
                sub_cmd=2,
            )
        )
        logger.debug("Area loading=====================:Response area data")
        return self.send_order_msg_nav(build)

    def indoor_simulation(self, flag: int) -> bytes:
        build = MctlNav(simulation_cmd=SimulationCmdData(sub_cmd=flag))
        logger.debug(f"Send command--Send indoor simulation command flag={flag}")
        return self.send_order_msg_nav(build)

    def send_tools_order(self, param_id: int, values: list[int]) -> bytes:
        build = MctlNav(simulation_cmd=SimulationCmdData(sub_cmd=2, param_id=param_id, param_value=values))
        logger.debug(f"Send command--Send tool command id={param_id},values={values}")
        return self.send_order_msg_nav(build)

    def end_draw_border(self, type: int) -> bytes:
        if type == -1:
            return
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=1, type=type))
        logger.debug(f"Send command--End drawing boundary, obstacle, channel command type={type}")
        return self.send_order_msg_nav(build)

    def cancel_current_record(self) -> bytes:
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=7, sub_cmd=0))
        logger.debug("Send command--Cancel current recording (boundary, obstacle)")
        return self.send_order_msg_nav(build)

    def delete_map_elements(self, type: int, hash_num: int) -> bytes:
        if type == -1:
            return
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=6, type=type, hash=hash_num))
        logger.debug(f"Send command--Delete boundary or obstacle or channel command type={type},hash={hash}")
        return self.send_order_msg_nav(build)

    def delete_charge_point(self) -> bytes:
        logger.debug("Delete charging pile")
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=6, type=5))
        logger.debug("Send command--Delete charging pile location and reset")
        return self.send_order_msg_nav(build)

    def confirm_base_station(self) -> bytes:
        logger.debug("Reset base station")
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=2, type=7))
        logger.debug("Send command--Confirm no modification to base station")
        return self.send_order_msg_nav(build)

    def delete_all(self) -> bytes:
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=6, type=6))
        logger.debug("Send command--Clear job data")
        return self.send_order_msg_nav(build)

    def generate_route_information(self, generate_route_information: GenerateRouteInformation) -> bytes:
        logger.debug(f"Generate route data source:{generate_route_information}")

        build = NavReqCoverPath(
            pver=1,
            sub_cmd=0,
            zone_hashs=generate_route_information.one_hashs,
            job_mode=int(generate_route_information.job_mode),
            edge_mode=int(generate_route_information.edge_mode),
            knife_height=int(generate_route_information.blade_height),
            speed=float(generate_route_information.speed),
            ultra_wave=int(generate_route_information.ultra_wave),
            channel_width=int(generate_route_information.channel_width),
            channel_mode=int(generate_route_information.channel_mode),
            toward=int(generate_route_information.toward),
            toward_included_angle=int(generate_route_information.toward_included_angle),  # luba 2 yuka only
            toward_mode=int(generate_route_information.toward_mode),  # luba 2 yuka only
            reserved=generate_route_information.path_order,
        )
        logger.debug(f"{self.get_device_name()}Generate route====={build}")
        logger.debug(f"Send command--Generate route information generateRouteInformation={
        generate_route_information}")
        return self.send_order_msg_nav(MctlNav(bidire_reqconver_path=build))

    def modify_generate_route_information(self, generate_route_information: GenerateRouteInformation) -> bytes:
        logger.debug(f"Generate route data source: {generate_route_information}")
        build = NavReqCoverPath(
            pver=1,
            sub_cmd=3,
            zone_hashs=generate_route_information.one_hashs,
            job_mode=int(generate_route_information.job_mode),
            edge_mode=int(generate_route_information.edge_mode),
            knife_height=int(generate_route_information.blade_height),
            speed=float(generate_route_information.speed),
            ultra_wave=int(generate_route_information.ultra_wave),
            channel_width=int(generate_route_information.channel_width),
            channel_mode=int(generate_route_information.channel_mode),
            toward=int(generate_route_information.toward),
            reserved=generate_route_information.path_order,
        )
        logger.debug(f"{self.get_device_name()} Generate route ===== {build}")
        logger.debug(f"Send command -- Modify route parameters generate_route_information={
        generate_route_information}")
        return self.send_order_msg_nav(MctlNav(bidire_reqconver_path=build))

    def end_generate_route_information(self) -> bytes:
        build = NavReqCoverPath(pver=1, sub_cmd=9)
        logger.debug(f"{self.get_device_name()} Generate route ===== {build}")
        build2 = MctlNav(bidire_reqconver_path=build)
        logger.debug("Send command -- End generating route information generate_route_information=")
        return self.send_order_msg_nav(build2)

    def query_generate_route_information(self) -> bytes:
        build = NavReqCoverPath(pver=1, sub_cmd=2)
        logger.debug(f"{self.get_device_name(
        )} Send command -- Get route configuration information generate_route_information={build}")
        build2 = MctlNav(bidire_reqconver_path=build)
        return self.send_order_msg_nav(build2)

    def get_line_info(self, current_hash: int) -> bytes:
        logger.debug(f"Sending==========Get route command: {current_hash}")
        build = MctlNav(todev_zigzag_ack=NavUploadZigZagResultAck(pver=1, current_hash=current_hash, sub_cmd=0))
        logger.debug(f"Sending command--Get route data corresponding to hash={current_hash}")
        return self.send_order_msg_nav(build)

    def get_line_info_list(self, hash_list: list[int], transaction_id: int) -> bytes:
        logger.debug(f"Sending==========Get route command: {hash_list}")
        build = MctlNav(
            app_request_cover_paths=AppRequestCoverPathsT(
                pver=1, hash_list=hash_list, transaction_id=transaction_id, sub_cmd=0
            )
        )
        logger.debug(f"Sending command--Get route data corresponding to hash={hash_list}")
        return self.send_order_msg_nav(build)

    def start_job(self) -> bytes:
        logger.debug("Sending==========Start job command")
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=1, result=0))
        logger.debug("Sending command--Start job")
        return self.send_order_msg_nav(build)

    def cancel_return_to_dock(self) -> bytes:
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=12, result=0))
        logger.debug("Send command - Cancel return to charge")
        return self.send_order_msg_nav(build)

    def cancel_job(self) -> bytes:
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=4, result=0))
        logger.debug("Send command - End job")
        return self.send_order_msg_nav(build)

    def return_to_dock(self) -> bytes:
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=5, result=0))
        logger.debug("Send command - Return to charge command")
        return self.send_order_msg_nav(build)

    def pause_execute_task(self) -> bytes:
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=2, result=0))
        logger.debug("Send command - Pause command")
        return self.send_order_msg_nav(build)

    def re_charge_test(self) -> bytes:
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=10, result=0))
        logger.debug("Send command - Return to charge test command")
        return self.send_order_msg_nav(build)

    def fast_aotu_test(self, action: int) -> bytes:
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=action, result=0))
        logger.debug("Send command - One-click automation test")
        return self.send_order_msg_nav(build)

    def resume_execute_task(self) -> bytes:
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=3, result=0))
        logger.debug("Send command - Cancel pause command")
        return self.send_order_msg_nav(build)

    def break_point_continue(self) -> bytes:
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=7, result=0))
        logger.debug("Send command - Continue from breakpoint")
        return self.send_order_msg_nav(build)

    def break_point_anywhere_continue(self) -> bytes:
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=9, result=0))
        logger.debug("Send command - Continue from current vehicle position")
        return self.send_order_msg_nav(build)

    def reset_base_station(self) -> bytes:
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=3, action=1, result=0))
        logger.debug("Send command - Reset charging pile, base station position")
        return self.send_order_msg_nav(build)
