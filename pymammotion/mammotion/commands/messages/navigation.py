# === sendOrderMsg_Nav ===
from abc import ABC
import logging
import time

from pymammotion.data.model import GenerateRouteInformation
from pymammotion.data.model.hash_list import Plan, SvgMessage
from pymammotion.data.model.region_data import RegionData
from pymammotion.mammotion.commands.abstract_message import AbstractMessage
from pymammotion.proto import (
    AppRequestCoverPathsT,
    LubaMsg,
    ManualElementMessage,
    MctlNav,
    MsgAttr,
    MsgCmdType,
    MsgDevice,
    NavEdgePointsAck,
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
    SvgMessageAckT,
    SvgMessageT,
    VisionCtrlMsg,
    WorkReportCmdData,
    WorkReportUpdateCmd,
)

logger = logging.getLogger(__name__)


class MessageNavigation(AbstractMessage, ABC):
    def send_order_msg_nav(self, build: MctlNav) -> bytes:
        """Wrap a navigation command in a LubaMsg envelope and serialise it to bytes."""
        luba_msg = LubaMsg(
            msgtype=MsgCmdType.NAV,
            sender=MsgDevice.DEV_MOBILEAPP,
            rcver=self.get_msg_device(MsgCmdType.NAV, MsgDevice.DEV_MAINCTL),
            msgattr=MsgAttr.REQ,
            seqs=self.seqs.increment_and_get() & 255,
            version=1,
            subtype=self.user_account,
            nav=build,
            timestamp=round(time.time() * 1000),
        )

        logger.debug(f"Send command--{self.get_device_name()}")

        return luba_msg.SerializeToString()

    def allpowerfull_rw_adapter_x3(self, rw_id: int, context: int, rw: int) -> bytes:
        """Send a generic read/write system parameter command via the x3 adapter."""
        build = MctlNav(nav_sys_param_cmd=NavSysParamMsg(id=rw_id, context=context, rw=rw))
        logger.debug(f"Send command--x3 general read and write command id={rw_id}, context={context}, rw={rw}")
        return self.send_order_msg_nav(build)

    def along_border(self) -> bytes:
        """Send command to drive the mower along the boundary edge."""
        build = MctlNav(todev_edgecmd=1)
        logger.debug("Send command--along the edge command")
        return self.send_order_msg_nav(build)

    def start_draw_border(self) -> bytes:
        """Start recording the outer boundary of the mowing area."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=0, type=0))
        logger.debug("Send command--Start drawing boundary command")
        return self.send_order_msg_nav(build)

    def enter_dumping_status(self) -> bytes:
        """Enter grass-collection (dumping) configuration mode on the device."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=14, type=12))
        logger.debug("Send command--Enter grass collection status")
        return self.send_order_msg_nav(build)

    def add_dump_point(self) -> bytes:
        """Add a grass-collection dump point at the current device position."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=0, type=12))
        logger.debug("Send command--Add grass collection point")
        return self.send_order_msg_nav(build)

    def revoke_dump_point(self) -> bytes:
        """Revoke (undo) the last grass-collection dump point."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=6, type=12))
        logger.debug("Send command--Revoke grass collection point")
        return self.send_order_msg_nav(build)

    def exit_dumping_status(self) -> bytes:
        """Exit grass-collection configuration mode and save the dump points."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=1, type=12))
        logger.debug("Send command--Exit grass collection setting status")
        return self.send_order_msg_nav(build)

    def out_drop_dumping_add(self) -> bytes:
        """Complete external grass-collection point marking outside the main boundary."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=15, type=12))
        logger.debug("Send command--Complete external grass collection point marking operation")
        return self.send_order_msg_nav(build)

    def recover_dumping(self) -> bytes:
        """Recover a previously deleted grass-collection dump operation."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=12, type=12))
        logger.debug("Send command--Recover grass collection operation")
        return self.send_order_msg_nav(build)

    def start_draw_barrier(self) -> bytes:
        """Start recording an obstacle (barrier) on the map."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=0, type=1))
        logger.debug("Sending command - Draw obstacle command")
        return self.send_order_msg_nav(build)

    def start_erase(self) -> bytes:
        """Start erasing part of a recorded boundary or obstacle."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=4, type=0))
        logger.debug("Sending command - Start erase command - Bluetooth")
        return self.send_order_msg_nav(build)

    def end_erase(self) -> bytes:
        """Finish and commit the current erase operation."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=5, type=0))
        logger.debug("Sending command - End erase command")
        return self.send_order_msg_nav(build)

    def cancel_erase(self) -> bytes:
        """Cancel the current erase operation without applying changes."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=7, type=0))
        logger.debug("Sending command - Cancel erase command")
        return self.send_order_msg_nav(build)

    def start_channel_line(self) -> bytes:
        """Start recording a channel (passage) line on the map."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=0, type=2))
        logger.debug("Sending command - Start drawing channel line command")
        return self.send_order_msg_nav(build)

    def save_task(self) -> bytes:
        """Save the current mapping task to the device."""
        build = MctlNav(todev_save_task=1)
        logger.debug("Sending command - Save task command")
        return self.send_order_msg_nav(build)

    def set_edit_boundary(self, action: int) -> bytes:
        """Send a secondary boundary-editing action command to the device."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=action, type=0))
        logger.debug(f"Sending secondary editing command action={action}")
        return self.send_order_msg_nav(build)

    def set_data_synchronization(self, type: int) -> bytes:
        """Trigger a data-synchronisation (restore) operation for the given data type."""
        logger.debug(f"Sync data ==================== Sending ============ Restore command: {type}")
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=12, type=type))
        logger.debug("Sync data ==================== Sending ============ Restore command")
        return self.send_order_msg_nav(build)

    def send_plan(self, plan_bean: Plan) -> bytes:
        """Send a mowing plan job configuration to the device."""
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
        """Send a scheduled mowing plan (including recurrence fields) to the device."""
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
            trigger_type=plan_bean.trigger_type,
            day=plan_bean.day,
            toward_included_angle=plan_bean.toward_included_angle,
            toward_mode=0,
        )
        logger.debug(f"Send read job plan command planBean={plan_bean}")
        return self.send_order_msg_nav(MctlNav(todev_planjob_set=build))

    def single_schedule(self, plan_id: str) -> bytes:
        """Execute a single-run schedule task identified by plan_id."""
        return self.send_order_msg_nav(MctlNav(plan_task_execute=NavPlanTaskExecute(sub_cmd=1, id=plan_id)))

    def read_plan(self, sub_cmd: int, plan_index: int = 0) -> bytes:
        """Read a stored mowing plan by sub-command and optional plan index."""
        build = MctlNav(todev_planjob_set=NavPlanJobSet(sub_cmd=sub_cmd, plan_index=plan_index))
        logger.debug(f"Send read job plan command cmd={sub_cmd} PlanIndex = {plan_index}")
        return self.send_order_msg_nav(build)

    def delete_plan(self, sub_cmd: int, plan_id: str) -> bytes:
        """Delete a stored mowing plan identified by plan_id."""
        build = MctlNav(todev_planjob_set=NavPlanJobSet(sub_cmd=sub_cmd, plan_id=plan_id))
        logger.debug(f"Send command--Send delete job plan command cmd={sub_cmd} planId = {plan_id}")
        return self.send_order_msg_nav(build)

    def set_plan_unable_time(self, sub_cmd: int, device_id: str, unable_end_time: str, unable_start_time: str) -> bytes:
        """Set a scheduled unavailability (blackout) time window for a mowing plan."""
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
        """Read the configured unavailability time window for a mowing plan."""
        build = NavUnableTimeSet(sub_cmd=sub_cmd)
        build2 = MctlNav(todev_unable_time_set=build)
        logger.debug(f"Send command--Read plan time {sub_cmd}")
        return self.send_order_msg_nav(build2)

    def read_job_not_not_disturb(self) -> bytes:
        """Read the do-not-disturb schedule currently configured on the device."""
        build = NavUnableTimeSet(sub_cmd=2)
        build2 = MctlNav(todev_unable_time_set=build)
        logger.debug(f"Send command--Read job dnd {2}")
        return self.send_order_msg_nav(build2)

    def job_animal_protect_read(self) -> bytes:
        """Read animal protection settings."""
        build = NavUnableTimeSet(sub_cmd=2, trigger=99)
        build2 = MctlNav(todev_unable_time_set=build)
        logger.debug(f"Send command - Read job do not disturb time subCmd2 {build}")
        return self.send_order_msg_nav(build2)

    def job_do_not_disturb(self, unable_start_time: str, unable_end_time: str) -> bytes:
        """Set do not disturb time period."""
        build = MctlNav(
            todev_unable_time_set=NavUnableTimeSet(
                sub_cmd=1, trigger=1, unable_start_time=unable_start_time, unable_end_time=unable_end_time
            )
        )
        logger.debug(f"Send command - Set job do not disturb time: {unable_start_time} - {unable_end_time}")
        return self.send_order_msg_nav(build)

    def job_do_not_disturb_del(self) -> bytes:
        """Delete do not disturb settings."""
        build = MctlNav(todev_unable_time_set=NavUnableTimeSet(sub_cmd=1, trigger=0))
        logger.debug("Send command - Turn off do not disturb time")
        return self.send_order_msg_nav(build)

    def query_job_history(self) -> bytes:
        """Request an update summary of historical mowing job records from the device."""
        return self.send_order_msg_nav(MctlNav(todev_work_report_update_cmd=WorkReportUpdateCmd(sub_cmd=1)))

    def request_job_history(self, num: int) -> bytes:
        """Fetch up to num historical mowing job records from the device."""
        return self.send_order_msg_nav(MctlNav(todev_work_report_cmd=WorkReportCmdData(sub_cmd=1, get_info_num=num)))

    def leave_dock(self) -> bytes:
        """Send one-touch command to automatically undock the mower from the charging station."""
        build = MctlNav(todev_one_touch_leave_pile=1)
        logger.debug("Send command--One-click automatic undocking")
        return self.send_order_msg_nav(build)

    def get_area_name_list(self, device_id: str) -> bytes:
        """Retrieve the list of named map areas stored on the device."""
        # Build the NavMapNameMsg with the specified parameters
        mctl_nav = MctlNav(
            toapp_map_name_msg=NavMapNameMsg(
                hash=0,
                result=0,
                device_id=device_id,  # iot_id
                rw=0,
            )
        )

        # Send the message with the specified ID and acknowledge flag
        logger.debug("Send command--Get area name list")
        return self.send_order_msg_nav(mctl_nav)

    def set_area_name(self, device_id: str, hash_id: int, name: str) -> bytes:
        """Set or update the display name for a map area identified by its hash."""
        # Build the NavMapNameMsg with the specified parameters
        mctl_nav = MctlNav(
            toapp_map_name_msg=NavMapNameMsg(hash=hash_id, name=name, result=0, device_id=device_id, rw=1)
        )

        # Send the message with the specified ID and acknowledge flag
        logger.debug("Send command--Get area name list")
        return self.send_order_msg_nav(mctl_nav)

    def get_all_boundary_hash_list(self, sub_cmd: int) -> bytes:
        """Request the full list of boundary/area hashes stored on the device."""
        build = MctlNav(todev_gethash=NavGetHashList(pver=1, sub_cmd=sub_cmd))
        logger.debug(f"Area loading=====================:Get area hash list:{sub_cmd}")
        return self.send_order_msg_nav(build)

    def get_hash_response(self, total_frame: int, current_frame: int) -> bytes:
        """Acknowledge receipt of a hash-list frame and request the next one."""
        build = MctlNav(
            todev_gethash=NavGetHashList(pver=1, sub_cmd=2, current_frame=current_frame, total_frame=total_frame)
        )
        logger.debug(
            f"Send command--208 Response hash list command totalFrame={total_frame},currentFrame={current_frame}"
        )
        return self.send_order_msg_nav(build)

    def synchronize_hash_data(self, hash_num: int) -> bytes:
        """Synchronise the map data for the area identified by the given hash."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=8, hash=hash_num, sub_cmd=1))
        logger.debug(f"Send command--209,hash synchronize area data hash:{hash_num}")
        return self.send_order_msg_nav(build)

    def get_area_to_be_transferred(self) -> bytes:
        """Request the area data that needs to be transferred before the mower returns to its charging pile."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=8, sub_cmd=1, type=3))
        logger.debug("Send command--Get transfer area before charging pile")
        return self.send_order_msg_nav(build)

    def get_common_data(self, *, action: int, type: int, sub_cmd: int = 1, hash_num: int = 0) -> bytes:
        """Generic NavGetCommData request used by CommonDataSaga.

        Sends a ``todev_get_commondata`` message with the given ``action`` and
        ``type``.  An optional ``hash_num`` is included when the request targets
        a specific stored hash (e.g. ``synchronize_hash_data`` uses action=8 with
        a hash; dynamics line uses action=8, type=18 with no hash).

        Args:
            action:   NavGetCommData action field (e.g. 8 = fetch/sync).
            type:     PathType value identifying the data to fetch (see PathType
                      enum and docs/common_data_types.md for the full table).
            hash_num: Optional hash ID.  Pass 0 (default) when the request is
                      not hash-specific (e.g. dynamics line, area transfer).

        """
        build = MctlNav(
            todev_get_commondata=NavGetCommData(pver=1, action=action, sub_cmd=sub_cmd, type=type, hash=hash_num)
        )
        logger.debug("Send command--get_common_data action=%d type=%d hash=%d", action, type, hash_num)
        return self.send_order_msg_nav(build)

    def get_regional_data(self, regional_data: RegionData) -> bytes:
        """Request a specific frame of regional map data (boundary, obstacle, or channel)."""
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
        """Start or stop an indoor simulation run on the device."""
        build = MctlNav(simulation_cmd=SimulationCmdData(sub_cmd=flag))
        logger.debug(f"Send command--Send indoor simulation command flag={flag}")
        return self.send_order_msg_nav(build)

    def send_tools_order(self, param_id: int, values: list[int]) -> bytes:
        """Send a simulation tool command with the specified parameter ID and values."""
        build = MctlNav(simulation_cmd=SimulationCmdData(sub_cmd=2, param_id=param_id, param_value=values))
        logger.debug(f"Send command--Send tool command id={param_id},values={values}")
        return self.send_order_msg_nav(build)

    def end_draw_border(self, type: int) -> bytes | None:
        """Finish recording a boundary, obstacle, or channel of the given type; returns None for type -1."""
        if type == -1:
            return None
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=1, type=type))
        logger.debug(f"Send command--End drawing boundary, obstacle, channel command type={type}")
        return self.send_order_msg_nav(build)

    def cancel_current_record(self) -> bytes:
        """Cancel the current recording session (boundary or obstacle) without saving."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=7, sub_cmd=0))
        logger.debug("Send command--Cancel current recording (boundary, obstacle)")
        return self.send_order_msg_nav(build)

    def delete_map_elements(self, type: int, hash_num: int) -> bytes | None:
        """Delete a map element (boundary, obstacle, or channel) by type and hash; returns None for type -1."""
        if type == -1:
            return None
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=6, type=type, hash=hash_num))
        logger.debug(f"Send command--Delete boundary or obstacle or channel command type={type},hash={hash}")
        return self.send_order_msg_nav(build)

    def delete_charge_point(self) -> bytes:
        """Delete the stored charging-pile location and reset the docking position."""
        logger.debug("Delete charging pile")
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=6, type=5))
        logger.debug("Send command--Delete charging pile location and reset")
        return self.send_order_msg_nav(build)

    def confirm_base_station(self) -> bytes:
        """Confirm the current base-station position without making modifications."""
        logger.debug("Reset base station")
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=2, type=7))
        logger.debug("Send command--Confirm no modification to base station")
        return self.send_order_msg_nav(build)

    def delete_all(self) -> bytes:
        """Clear all stored job and map data from the device."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=6, type=6))
        logger.debug("Send command--Clear job data")
        return self.send_order_msg_nav(build)

    def generate_route_information(self, generate_route_information: GenerateRouteInformation) -> bytes:
        """Generate a mow-path route plan on the device from the given route parameters."""
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
        logger.debug(f"Send command--Generate route information generateRouteInformation={generate_route_information}")
        return self.send_order_msg_nav(MctlNav(bidire_reqconver_path=build))

    def modify_route_information(self, generate_route_information: GenerateRouteInformation) -> bytes:
        """Modify an existing mow-path route with updated parameters without regenerating from scratch."""
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
        logger.debug(f"Send command -- Modify route parameters generate_route_information={generate_route_information}")
        return self.send_order_msg_nav(MctlNav(bidire_reqconver_path=build))

    def end_generate_route_information(self) -> bytes:
        """Signal the device that route-generation is complete and it should finalise the path."""
        build = NavReqCoverPath(pver=1, sub_cmd=9)
        logger.debug(f"{self.get_device_name()} Generate route ===== {build}")
        build2 = MctlNav(bidire_reqconver_path=build)
        logger.debug("Send command -- End generating route information generate_route_information=")
        return self.send_order_msg_nav(build2)

    def query_generate_route_information(self) -> bytes:
        """Query the current route-generation configuration from the device."""
        build = NavReqCoverPath(pver=1, sub_cmd=2)
        logger.debug(
            f"{self.get_device_name()} Send command -- Get route configuration information generate_route_information={
                build
            }"
        )
        build2 = MctlNav(bidire_reqconver_path=build)
        return self.send_order_msg_nav(build2)

    def get_line_info(self, current_hash: int) -> bytes:
        """Request the mow-path route data corresponding to the given hash."""
        logger.debug(f"Sending==========Get route command: {current_hash}")
        build = MctlNav(todev_zigzag_ack=NavUploadZigZagResultAck(pver=1, current_hash=current_hash, sub_cmd=0))
        logger.debug(f"Sending command--Get route data corresponding to hash={current_hash}")
        return self.send_order_msg_nav(build)

    def get_line_info_list(self, hash_list: list[int], transaction_id: int) -> bytes:
        """Get route information (mow path) corresponding to the specified hash list based on time.
        e.g transaction_id = int(time.time() * 1000)
        """
        logger.debug(f"Sending==========Get route command: {hash_list}")

        build = MctlNav(
            app_request_cover_paths=AppRequestCoverPathsT(
                pver=1, hash_list=hash_list, transaction_id=transaction_id, sub_cmd=0
            )
        )
        logger.debug(f"Sending command--Get route data corresponding to hash={hash_list}")
        return self.send_order_msg_nav(build)

    def start_job(self) -> bytes:
        """Send command to start the mowing job on the device."""
        logger.debug("Sending==========Start job command")
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=1, result=0))
        logger.debug("Sending command--Start job")
        return self.send_order_msg_nav(build)

    def cancel_return_to_dock(self) -> bytes:
        """Cancel an in-progress return-to-dock (return-to-charge) command."""
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=12, result=0))
        logger.debug("Send command - Cancel return to charge")
        return self.send_order_msg_nav(build)

    def cancel_job(self) -> bytes:
        """Send command to cancel (end) the current mowing job."""
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=4, result=0))
        logger.debug("Send command - End job")
        return self.send_order_msg_nav(build)

    def return_to_dock(self) -> bytes:
        """Send command to return the mower to its charging station."""
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=5, result=0))
        logger.debug("Send command - Return to charge command")
        return self.send_order_msg_nav(build)

    def pause_execute_task(self) -> bytes:
        """Pause the currently executing mowing task."""
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=2, result=0))
        logger.debug("Send command - Pause command")
        return self.send_order_msg_nav(build)

    def re_charge_test(self) -> bytes:
        """Send a return-to-charge test command to verify docking behaviour."""
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=10, result=0))
        logger.debug("Send command - Return to charge test command")
        return self.send_order_msg_nav(build)

    def fast_aotu_test(self, action: int) -> bytes:
        """Send a one-click automation test command with the specified action code."""
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=action, result=0))
        logger.debug("Send command - One-click automation test")
        return self.send_order_msg_nav(build)

    def resume_execute_task(self) -> bytes:
        """Resume a previously paused mowing task."""
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=3, result=0))
        logger.debug("Send command - Cancel pause command")
        return self.send_order_msg_nav(build)

    def break_point_continue(self) -> bytes:
        """Resume mowing from the last saved breakpoint position."""
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=7, result=0))
        logger.debug("Send command - Continue from breakpoint")
        return self.send_order_msg_nav(build)

    def break_point_anywhere_continue(self) -> bytes:
        """Resume mowing from the current vehicle position rather than the last breakpoint."""
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=9, result=0))
        logger.debug("Send command - Continue from current vehicle position")
        return self.send_order_msg_nav(build)

    def reset_base_station(self) -> bytes:
        """Reset the charging-pile and base-station position on the device."""
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=3, action=1, result=0))
        logger.debug("Send command - Reset charging pile, base station position")
        return self.send_order_msg_nav(build)

    def send_svg_data(self, svg_message: SvgMessage) -> bytes:
        """Send SVG data to the device."""
        build = MctlNav(
            todev_svg_msg=SvgMessageAckT(
                pver=1,
                sub_cmd=svg_message.sub_cmd,
                total_frame=svg_message.total_frame,
                current_frame=svg_message.current_frame,
                data_hash=svg_message.data_hash,
                paternal_hash_a=svg_message.paternal_hash_a,
                result=svg_message.result,
                svg_message=SvgMessageT(
                    hide_svg=svg_message.svg_message.hide_svg,
                    svg_file_data=svg_message.svg_message.svg_file_data,
                    svg_file_name=svg_message.svg_message.svg_file_name,
                    data_count=svg_message.svg_message.data_count,
                    name_count=svg_message.svg_message.name_count,
                    base_height_m=svg_message.svg_message.base_height_m,
                    base_width_m=svg_message.svg_message.base_width_m,
                    base_width_pix=svg_message.svg_message.base_width_pix,
                    base_height_pix=svg_message.svg_message.base_height_pix,
                    x_move=svg_message.svg_message.x_move,
                    y_move=svg_message.svg_message.y_move,
                    scale=svg_message.svg_message.scale,
                    rotate=svg_message.svg_message.rotate,
                ),
            )
        )

        return self.send_order_msg_nav(build)

    # === Corridor recording (MN231) ===

    def start_draw_corridor(self) -> bytes:
        """Start corridor recording (MN231)."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=0, type=19))
        logger.debug("Send command - Start corridor recording")
        return self.send_order_msg_nav(build)

    def add_draw_corridor_point(self) -> bytes:
        """Add a corridor point during corridor recording (MN231)."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=0, type=20))
        logger.debug("Send command - Add corridor point")
        return self.send_order_msg_nav(build)

    def end_draw_corridor(self) -> bytes:
        """End corridor recording (MN231)."""
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=17, result=0))
        logger.debug("Send command - End corridor recording")
        return self.send_order_msg_nav(build)

    def give_up_draw_corridor(self) -> bytes:
        """Abandon corridor recording without saving (MN231)."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=7, type=19))
        logger.debug("Send command - Give up corridor recording")
        return self.send_order_msg_nav(build)

    def recover_draw_corridor_line(self) -> bytes:
        """Recover (undo last delete of) corridor line (MN231)."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=12, type=19))
        logger.debug("Send command - Recover corridor line")
        return self.send_order_msg_nav(build)

    def recover_draw_corridor_point(self) -> bytes:
        """Recover (undo last delete of) corridor point (MN231)."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=12, type=20))
        logger.debug("Send command - Recover corridor point")
        return self.send_order_msg_nav(build)

    def stop_and_not_save_task(self) -> bytes:
        """Abort mapping mid-way without saving (MN231 exit during states 45/46)."""
        build = MctlNav(todev_taskctrl=NavTaskCtrl(type=1, action=18, result=0))
        logger.debug("Send command - Stop and do not save task")
        return self.send_order_msg_nav(build)

    # === Firmware 4.3.1+ border drawing variants ===

    def start_draw_border_431(self) -> bytes:
        """Start border drawing for firmware 4.3.1+ devices."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=19, type=0))
        logger.debug("Send command - Start border drawing (4.3.1+)")
        return self.send_order_msg_nav(build)

    def start_positioning_431_all(self) -> bytes:
        """Start lidar positioning for firmware 4.3.1+ devices."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=21, type=17))
        logger.debug("Send command - Start lidar positioning (4.3.1+)")
        return self.send_order_msg_nav(build)

    # === Lidar charge point ===

    def delete_ld_charge_point(self) -> bytes:
        """Delete lidar charging pile position and reset."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=0, type=5))
        logger.debug("Send command - Delete lidar charging pile position and reset")
        return self.send_order_msg_nav(build)

    # === Pattern visibility ===

    def set_pattern_hide_or_show(self, type: int, hash_num: int) -> bytes:
        """Show or hide a map pattern (obstacle/area overlay) by type and hash."""
        build = MctlNav(todev_get_commondata=NavGetCommData(pver=1, action=16, type=type, hash=hash_num))
        logger.debug(f"Send command - Set pattern hide/show type={type}, hash={hash_num}")
        return self.send_order_msg_nav(build)

    # === Visual safety zones (manual elements) ===

    def add_manual_element(
        self,
        shape: int,
        type: int,
        center_x: float,
        center_y: float,
        width_x: float,
        height_y: float,
        sub_cmd: int,
        rotate_radius: float,
    ) -> bytes:
        """Add a visual safety zone (obstacle avoidance element) to the map."""
        build = MctlNav(
            toapp_manual_element=ManualElementMessage(
                pver=1,
                shape=shape,
                type=type,
                point1_center_x=center_x,
                point1_center_y=center_y,
                point2_width_x=width_x,
                point2_height_y=height_y,
                sub_cmd=sub_cmd,
                rotate_radius=rotate_radius,
            )
        )
        logger.debug(f"Send command - Add manual element shape={shape}, type={type}")
        return self.send_order_msg_nav(build)

    def delete_manual_element(self, hash_num: int, type: int, shape: int, permanent: bool = False) -> bytes:
        """Delete a visual safety zone by hash. permanent=True deletes all instances."""
        sub_cmd = 2 if permanent else 1
        build = MctlNav(
            toapp_manual_element=ManualElementMessage(
                pver=1,
                type=type,
                shape=shape,
                data_hash=hash_num,
                sub_cmd=sub_cmd,
            )
        )
        logger.debug(f"Send command - Delete manual element hash={hash_num}, type={type}, permanent={permanent}")
        return self.send_order_msg_nav(build)

    # === Edgewise mapping response ===

    def response_edgewise_mapping(
        self, action: int, hash_num: int, result: int, type: int, total_frame: int, current_frame: int
    ) -> bytes:
        """Acknowledge edgewise mapping data received from device."""
        build = MctlNav(
            toapp_edge_points_ack=NavEdgePointsAck(
                action=action,
                hash=hash_num,
                result=result,
                type=type,
                total_frame=total_frame,
                current_frame=current_frame,
            )
        )
        logger.debug(f"Send command - Response edgewise mapping action={action}, hash={hash_num}")
        return self.send_order_msg_nav(build)

    # === Radar test ===

    def radar_test_send(self, cmd: int) -> bytes:
        """Send radar static test command. Sends to DEV_PERCEPTION instead of DEV_MAINCTL."""
        import time as _time

        luba_msg = LubaMsg(
            msgtype=MsgCmdType.NAV,
            sender=MsgDevice.DEV_MOBILEAPP,
            rcver=MsgDevice.DEV_PERCEPTION,
            msgattr=MsgAttr.REQ,
            seqs=self.seqs.increment_and_get() & 255,
            version=1,
            subtype=self.user_account,
            nav=MctlNav(vision_ctrl=VisionCtrlMsg(type=1, cmd=cmd)),
            timestamp=round(_time.time() * 1000),
        )
        logger.debug(f"Send command - Radar test cmd={cmd}")
        return luba_msg.SerializeToString()
