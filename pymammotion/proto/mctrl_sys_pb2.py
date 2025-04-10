# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: pymammotion/proto/mctrl_sys.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from pymammotion.proto import dev_net_pb2 as pymammotion_dot_proto_dot_dev__net__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n!pymammotion/proto/mctrl_sys.proto\x1a\x1fpymammotion/proto/dev_net.proto\"\x1a\n\x08SysBatUp\x12\x0e\n\x06\x62\x61tVal\x18\x01 \x01(\x05\"Z\n\x0cSysWorkState\x12\x13\n\x0b\x64\x65viceState\x18\x01 \x01(\x05\x12\x13\n\x0b\x63hargeState\x18\x02 \x01(\x05\x12\x0e\n\x06\x63mHash\x18\x03 \x01(\x03\x12\x10\n\x08pathHash\x18\x04 \x01(\x03\"5\n\x0eSysSetTimeZone\x12\x11\n\ttimeStamp\x18\x01 \x01(\x05\x12\x10\n\x08timeArea\x18\x02 \x01(\x05\"\x9e\x01\n\x0eSysSetDateTime\x12\x0c\n\x04Year\x18\x01 \x01(\x05\x12\r\n\x05Month\x18\x02 \x01(\x05\x12\x0c\n\x04\x44\x61te\x18\x03 \x01(\x05\x12\x0c\n\x04Week\x18\x04 \x01(\x05\x12\r\n\x05Hours\x18\x05 \x01(\x05\x12\x0f\n\x07Minutes\x18\x06 \x01(\x05\x12\x0f\n\x07Seconds\x18\x07 \x01(\x05\x12\x10\n\x08timeZone\x18\x08 \x01(\x05\x12\x10\n\x08\x64\x61ylight\x18\t \x01(\x05\"V\n\nSysJobPlan\x12\r\n\x05jobId\x18\x01 \x01(\x03\x12\x0f\n\x07jobMode\x18\x02 \x01(\x05\x12\x13\n\x0brainTactics\x18\x03 \x01(\x05\x12\x13\n\x0bknifeHeight\x18\x04 \x01(\x05\"\"\n\rSysDevErrCode\x12\x11\n\terrorCode\x18\x01 \x01(\x05\"!\n\x0cSysBoardType\x12\x11\n\tboardType\x18\x01 \x01(\x05\"5\n\x0cSysSwVersion\x12\x11\n\tboardType\x18\x01 \x01(\x05\x12\x12\n\nversionLen\x18\x02 \x01(\x05\"1\n\rSysDelJobPlan\x12\x10\n\x08\x64\x65viceId\x18\x01 \x01(\t\x12\x0e\n\x06planId\x18\x02 \x01(\t\"\xec\x01\n\x0eSysJobPlanTime\x12\x0e\n\x06planId\x18\x01 \x01(\x03\x12\x16\n\x0estart_job_time\x18\x02 \x01(\x05\x12\x14\n\x0c\x65nd_job_time\x18\x03 \x01(\x05\x12\x13\n\x0btime_in_day\x18\x04 \x01(\x05\x12\x15\n\rjob_plan_mode\x18\x05 \x01(\x05\x12\x17\n\x0fjob_plan_enable\x18\x06 \x01(\x05\x12\x0f\n\x07weekDay\x18\x07 \x03(\x05\x12\x15\n\rtimeInWeekDay\x18\x08 \x03(\x05\x12\x10\n\x08\x65veryDay\x18\t \x01(\x05\x12\x1d\n\x08job_plan\x18\n \x01(\x0b\x32\x0b.SysJobPlan\"m\n\nSysMowInfo\x12\x13\n\x0b\x64\x65viceState\x18\x01 \x01(\x05\x12\x0e\n\x06\x62\x61tVal\x18\x02 \x01(\x05\x12\x13\n\x0bknifeHeight\x18\x03 \x01(\x05\x12\x12\n\nrtk_status\x18\x04 \x01(\x05\x12\x11\n\trtk_stars\x18\x05 \x01(\x05\";\n\x0eSysOptiLineAck\x12\x13\n\x0bresponesCmd\x18\x01 \x01(\x05\x12\x14\n\x0c\x63urrentFrame\x18\x02 \x01(\x05\"5\n\nSysCommCmd\x12\n\n\x02rw\x18\x01 \x01(\x05\x12\n\n\x02id\x18\x02 \x01(\x05\x12\x0f\n\x07\x63ontext\x18\x03 \x01(\x05\"H\n\x15SysUploadFileProgress\x12\r\n\x05\x62izId\x18\x01 \x01(\t\x12\x0e\n\x06result\x18\x02 \x01(\x05\x12\x10\n\x08progress\x18\x03 \x01(\x05\"\x1f\n\x0cSysErrorCode\x12\x0f\n\x07\x63ode_no\x18\x01 \x01(\x05\"\x1e\n\tSysBorder\x12\x11\n\tborderval\x18\x01 \x01(\x05\"*\n\x10SysPlanJobStatus\x12\x16\n\x0eplanjob_status\x18\x01 \x01(\x05\"=\n\x0fSysKnifeControl\x12\x14\n\x0cknife_status\x18\x01 \x01(\x05\x12\x14\n\x0cknife_height\x18\x02 \x01(\x05\"+\n\x14SysResetSystemStatus\x12\x13\n\x0breset_staus\x18\x01 \x01(\x05\"\x8a\x01\n\rTimeCtrlLight\x12\x0f\n\x07operate\x18\x01 \x01(\x05\x12\x0e\n\x06\x65nable\x18\x02 \x01(\x05\x12\x12\n\nstart_hour\x18\x03 \x01(\x05\x12\x11\n\tstart_min\x18\x04 \x01(\x05\x12\x10\n\x08\x65nd_hour\x18\x05 \x01(\x05\x12\x0f\n\x07\x65nd_min\x18\x06 \x01(\x05\x12\x0e\n\x06\x61\x63tion\x18\x07 \x01(\x05\"3\n\x10vision_point_msg\x12\t\n\x01x\x18\x01 \x01(\x02\x12\t\n\x01y\x18\x02 \x01(\x02\x12\t\n\x01z\x18\x03 \x01(\x02\"\\\n\x15vision_point_info_msg\x12\r\n\x05label\x18\x01 \x01(\x05\x12\x0b\n\x03num\x18\x02 \x01(\x05\x12\'\n\x0cvision_point\x18\x03 \x03(\x0b\x32\x11.vision_point_msg\"\x9a\x01\n\x13vio_to_app_info_msg\x12\t\n\x01x\x18\x01 \x01(\x01\x12\t\n\x01y\x18\x02 \x01(\x01\x12\x0f\n\x07heading\x18\x03 \x01(\x01\x12\x11\n\tvio_state\x18\x04 \x01(\x05\x12\x12\n\nbrightness\x18\x05 \x01(\x05\x12\x1a\n\x12\x64\x65tect_feature_num\x18\x06 \x01(\x05\x12\x19\n\x11track_feature_num\x18\x07 \x01(\x05\"1\n\x14vision_statistic_msg\x12\x0c\n\x04mean\x18\x01 \x01(\x02\x12\x0b\n\x03var\x18\x02 \x01(\x02\"m\n\x19vision_statistic_info_msg\x12\x11\n\ttimestamp\x18\x01 \x01(\x01\x12\x0b\n\x03num\x18\x02 \x01(\x05\x12\x30\n\x11vision_statistics\x18\x03 \x03(\x0b\x32\x15.vision_statistic_msg\"\xd3\x01\n\x1asystemRapidStateTunnel_msg\x12\x18\n\x10rapid_state_data\x18\x01 \x03(\x03\x12\x31\n\x11vision_point_info\x18\x02 \x03(\x0b\x32\x16.vision_point_info_msg\x12-\n\x0fvio_to_app_info\x18\x03 \x01(\x0b\x32\x14.vio_to_app_info_msg\x12\x39\n\x15vision_statistic_info\x18\x04 \x01(\x0b\x32\x1a.vision_statistic_info_msg\"4\n\x19systemTardStateTunnel_msg\x12\x17\n\x0ftard_state_data\x18\x01 \x03(\x03\".\n\x13systemUpdateBuf_msg\x12\x17\n\x0fupdate_buf_data\x18\x01 \x03(\x03\"\x9e\x01\n\x0fSysOffChipFlash\x12\x16\n\x02op\x18\x01 \x01(\x0e\x32\n.Operation\x12\x16\n\x02id\x18\x02 \x01(\x0e\x32\n.OffPartId\x12\x12\n\nstart_addr\x18\x03 \x01(\r\x12\x0e\n\x06offset\x18\x04 \x01(\r\x12\x0e\n\x06length\x18\x05 \x01(\x05\x12\x0c\n\x04\x64\x61ta\x18\x06 \x01(\x0c\x12\x0c\n\x04\x63ode\x18\x07 \x01(\x05\x12\x0b\n\x03msg\x18\x08 \x01(\t\"-\n\x14systemTmpCycleTx_msg\x12\x15\n\rcycle_tx_data\x18\x01 \x03(\x03\"%\n\nLoraCfgReq\x12\n\n\x02op\x18\x01 \x01(\x05\x12\x0b\n\x03\x63\x66g\x18\x02 \x01(\t\"F\n\nLoraCfgRsp\x12\x0e\n\x06result\x18\x01 \x01(\x05\x12\n\n\x02op\x18\x02 \x01(\x05\x12\x0b\n\x03\x63\x66g\x18\x03 \x01(\t\x12\x0f\n\x07\x66\x61\x63_cfg\x18\x04 \x01(\x0c\">\n\x0bmod_fw_info\x12\x0c\n\x04type\x18\x01 \x01(\x05\x12\x10\n\x08identify\x18\x02 \x01(\t\x12\x0f\n\x07version\x18\x03 \x01(\t\"L\n\x0e\x64\x65vice_fw_info\x12\x0e\n\x06result\x18\x01 \x01(\x05\x12\x0f\n\x07version\x18\x02 \x01(\t\x12\x19\n\x03mod\x18\x03 \x03(\x0b\x32\x0c.mod_fw_info\"@\n\x11mow_to_app_info_t\x12\x0c\n\x04type\x18\x01 \x01(\x05\x12\x0b\n\x03\x63md\x18\x02 \x01(\x05\x12\x10\n\x08mow_data\x18\x03 \x03(\x05\"a\n\x1a\x64\x65vice_product_type_info_t\x12\x0e\n\x06result\x18\x01 \x01(\x05\x12\x19\n\x11main_product_type\x18\x02 \x01(\t\x12\x18\n\x10sub_product_type\x18\x03 \x01(\t\"P\n\x0fQCAppTestExcept\x12\x13\n\x0b\x65xcept_type\x18\x01 \x01(\t\x12(\n\nconditions\x18\x02 \x03(\x0b\x32\x14.QCAppTestConditions\"t\n\x13QCAppTestConditions\x12\x11\n\tcond_type\x18\x01 \x01(\t\x12\x0f\n\x07int_val\x18\x02 \x01(\x05\x12\x11\n\tfloat_val\x18\x03 \x01(\x02\x12\x12\n\ndouble_val\x18\x04 \x01(\x01\x12\x12\n\nstring_val\x18\x05 \x01(\t\"\x99\x01\n\x19mow_to_app_qctools_info_t\x12\x1a\n\x04type\x18\x01 \x01(\x0e\x32\x0c.QCAppTestId\x12\x16\n\x0etimeOfDuration\x18\x02 \x01(\x05\x12\x0e\n\x06result\x18\x03 \x01(\x05\x12\x16\n\x0eresult_details\x18\x04 \x01(\t\x12 \n\x06\x65xcept\x18\x05 \x03(\x0b\x32\x10.QCAppTestExcept\"O\n\x16mCtrlSimulationCmdData\x12\x0e\n\x06subCmd\x18\x01 \x01(\x05\x12\x10\n\x08param_id\x18\x02 \x01(\x05\x12\x13\n\x0bparam_value\x18\x03 \x03(\x05\"\x8f\x01\n\x08rpt_lora\x12\x16\n\x0epair_code_scan\x18\x01 \x01(\x05\x12\x19\n\x11pair_code_channel\x18\x02 \x01(\x05\x12\x17\n\x0fpair_code_locid\x18\x03 \x01(\x05\x12\x17\n\x0fpair_code_netid\x18\x04 \x01(\x05\x12\x1e\n\x16lora_connection_status\x18\x05 \x01(\x05\"Q\n\x10mqtt_rtk_connect\x12\x12\n\nrtk_switch\x18\x01 \x01(\x05\x12\x13\n\x0brtk_channel\x18\x02 \x01(\x05\x12\x14\n\x0crtk_base_num\x18\x03 \x01(\t\"\x9b\x02\n\x07rpt_rtk\x12\x0e\n\x06status\x18\x01 \x01(\x05\x12\x11\n\tpos_level\x18\x02 \x01(\x05\x12\x11\n\tgps_stars\x18\x03 \x01(\x05\x12\x0b\n\x03\x61ge\x18\x04 \x01(\x05\x12\x0f\n\x07lat_std\x18\x05 \x01(\x05\x12\x0f\n\x07lon_std\x18\x06 \x01(\x05\x12\x10\n\x08l2_stars\x18\x07 \x01(\x05\x12\x12\n\ndis_status\x18\x08 \x01(\x03\x12\x17\n\x0ftop4_total_mean\x18\t \x01(\x03\x12\x15\n\rco_view_stars\x18\n \x01(\x05\x12\r\n\x05reset\x18\x0b \x01(\x05\x12\x1c\n\tlora_info\x18\x0c \x01(\x0b\x32\t.rpt_lora\x12(\n\rmqtt_rtk_info\x18\r \x01(\x0b\x32\x11.mqtt_rtk_connect\"\x86\x01\n\x10rpt_dev_location\x12\x12\n\nreal_pos_x\x18\x01 \x01(\x05\x12\x12\n\nreal_pos_y\x18\x02 \x01(\x05\x12\x13\n\x0breal_toward\x18\x03 \x01(\x05\x12\x10\n\x08pos_type\x18\x04 \x01(\x05\x12\x11\n\tzone_hash\x18\x05 \x01(\x03\x12\x10\n\x08\x62ol_hash\x18\x06 \x01(\x03\"4\n\x13vio_survival_info_t\x12\x1d\n\x15vio_survival_distance\x18\x01 \x01(\x02\";\n\x12\x63ollector_status_t\x12%\n\x1d\x63ollector_installation_status\x18\x01 \x01(\x05\"\"\n\x0clock_state_t\x12\x12\n\nlock_state\x18\x01 \x01(\r\"\x8b\x03\n\x0erpt_dev_status\x12\x12\n\nsys_status\x18\x01 \x01(\x05\x12\x14\n\x0c\x63harge_state\x18\x02 \x01(\x05\x12\x13\n\x0b\x62\x61ttery_val\x18\x03 \x01(\x05\x12\x15\n\rsensor_status\x18\x04 \x01(\x05\x12\x13\n\x0blast_status\x18\x05 \x01(\x05\x12\x16\n\x0esys_time_stamp\x18\x06 \x01(\x03\x12\x14\n\x0cvslam_status\x18\x07 \x01(\x05\x12\x1c\n\tmnet_info\x18\x08 \x01(\x0b\x32\t.MnetInfo\x12/\n\x11vio_survival_info\x18\t \x01(\x0b\x32\x14.vio_survival_info_t\x12-\n\x10\x63ollector_status\x18\n \x01(\x0b\x32\x13.collector_status_t\x12!\n\nlock_state\x18\x0b \x01(\x0b\x32\r.lock_state_t\x12\x19\n\x11self_check_status\x18\x0c \x01(\r\x12$\n\x08\x66pv_info\x18\r \x01(\x0b\x32\x12.fpv_to_app_info_t\"\xc6\x01\n\x12rpt_connect_status\x12\x14\n\x0c\x63onnect_type\x18\x01 \x01(\x05\x12\x10\n\x08\x62le_rssi\x18\x02 \x01(\x05\x12\x11\n\twifi_rssi\x18\x03 \x01(\x05\x12\x11\n\tlink_type\x18\x04 \x01(\x05\x12\x11\n\tmnet_rssi\x18\x05 \x01(\x05\x12\x11\n\tmnet_inet\x18\x06 \x01(\x05\x12 \n\x08used_net\x18\x07 \x01(\x0e\x32\x0e.net_used_type\x12\x1a\n\x08mnet_cfg\x18\x08 \x01(\x0b\x32\x08.MnetCfg\",\n\x13nav_heading_state_t\x12\x15\n\rheading_state\x18\x01 \x01(\x05\"\xd1\x03\n\x08rpt_work\x12\x0c\n\x04plan\x18\x01 \x01(\x05\x12\x11\n\tpath_hash\x18\x02 \x01(\x03\x12\x10\n\x08progress\x18\x03 \x01(\x05\x12\x0c\n\x04\x61rea\x18\x04 \x01(\x05\x12\x0f\n\x07\x62p_info\x18\x05 \x01(\x05\x12\x0f\n\x07\x62p_hash\x18\x06 \x01(\x03\x12\x10\n\x08\x62p_pos_x\x18\x07 \x01(\x05\x12\x10\n\x08\x62p_pos_y\x18\x08 \x01(\x05\x12\x15\n\rreal_path_num\x18\t \x01(\x03\x12\x12\n\npath_pos_x\x18\n \x01(\x05\x12\x12\n\npath_pos_y\x18\x0b \x01(\x05\x12\x14\n\x0cub_zone_hash\x18\x0c \x01(\x03\x12\x14\n\x0cub_path_hash\x18\r \x01(\x03\x12\x15\n\rinit_cfg_hash\x18\x0e \x01(\x03\x12\x15\n\rub_ecode_hash\x18\x0f \x01(\x03\x12\x14\n\x0cnav_run_mode\x18\x10 \x01(\x05\x12\x18\n\x10test_mode_status\x18\x11 \x01(\x03\x12\x15\n\rman_run_speed\x18\x12 \x01(\x05\x12\x17\n\x0fnav_edit_status\x18\x13 \x01(\x05\x12\x14\n\x0cknife_height\x18\x14 \x01(\x05\x12/\n\x11nav_heading_state\x18\x15 \x01(\x0b\x32\x14.nav_heading_state_t\"C\n\nblade_used\x12\x17\n\x0f\x62lade_used_time\x18\x01 \x01(\x05\x12\x1c\n\x14\x62lade_used_warn_time\x18\x02 \x01(\x05\"=\n\x1duser_set_blade_used_warn_time\x12\x1c\n\x14\x62lade_used_warn_time\x18\x01 \x01(\x05\"l\n\x0crpt_maintain\x12\x0f\n\x07mileage\x18\x01 \x01(\x03\x12\x11\n\twork_time\x18\x02 \x01(\x05\x12\x12\n\nbat_cycles\x18\x03 \x01(\x05\x12$\n\x0f\x62lade_used_time\x18\x04 \x01(\x0b\x32\x0b.blade_used\"[\n\x11\x66pv_to_app_info_t\x12\x10\n\x08\x66pv_flag\x18\x01 \x01(\x05\x12\x16\n\x0ewifi_available\x18\x02 \x01(\x05\x12\x1c\n\x14mobile_net_available\x18\x03 \x01(\x05\"\xa4\x01\n\x14rpt_basestation_info\x12\x11\n\tver_major\x18\x01 \x01(\r\x12\x11\n\tver_minor\x18\x02 \x01(\r\x12\x11\n\tver_patch\x18\x03 \x01(\r\x12\x11\n\tver_build\x18\x04 \x01(\r\x12\x1a\n\x12\x62\x61sestation_status\x18\x05 \x01(\r\x12$\n\x1c\x63onnect_status_since_poweron\x18\x06 \x01(\r\"\x8f\x01\n\x0freport_info_cfg\x12\x15\n\x03\x61\x63t\x18\x01 \x01(\x0e\x32\x08.rpt_act\x12\x0f\n\x07timeout\x18\x02 \x01(\x05\x12\x0e\n\x06period\x18\x03 \x01(\x05\x12\x18\n\x10no_change_period\x18\x04 \x01(\x05\x12\r\n\x05\x63ount\x18\x05 \x01(\x05\x12\x1b\n\x03sub\x18\x06 \x03(\x0e\x32\x0e.rpt_info_type\"\xbd\x03\n\x10report_info_data\x12$\n\x07\x63onnect\x18\x01 \x01(\x0b\x32\x13.rpt_connect_status\x12\x1c\n\x03\x64\x65v\x18\x02 \x01(\x0b\x32\x0f.rpt_dev_status\x12\x15\n\x03rtk\x18\x03 \x01(\x0b\x32\x08.rpt_rtk\x12$\n\tlocations\x18\x04 \x03(\x0b\x32\x11.rpt_dev_location\x12\x17\n\x04work\x18\x05 \x01(\x0b\x32\t.rpt_work\x12 \n\x07\x66w_info\x18\x06 \x01(\x0b\x32\x0f.device_fw_info\x12\x1f\n\x08maintain\x18\x07 \x01(\x0b\x32\r.rpt_maintain\x12\x31\n\x11vision_point_info\x18\x08 \x03(\x0b\x32\x16.vision_point_info_msg\x12-\n\x0fvio_to_app_info\x18\t \x01(\x0b\x32\x14.vio_to_app_info_msg\x12\x39\n\x15vision_statistic_info\x18\n \x01(\x0b\x32\x1a.vision_statistic_info_msg\x12/\n\x10\x62\x61sestation_info\x18\x0b \x01(\x0b\x32\x15.rpt_basestation_info\"\x9c\x0c\n\x07MctlSys\x12\"\n\rtoapp_batinfo\x18\x01 \x01(\x0b\x32\t.SysBatUpH\x00\x12)\n\x10toapp_work_state\x18\x02 \x01(\x0b\x32\r.SysWorkStateH\x00\x12*\n\x0ftodev_time_zone\x18\x03 \x01(\x0b\x32\x0f.SysSetTimeZoneH\x00\x12*\n\x0ftodev_data_time\x18\x04 \x01(\x0b\x32\x0f.SysSetDateTimeH\x00\x12\x1f\n\x08job_plan\x18\x06 \x01(\x0b\x32\x0b.SysJobPlanH\x00\x12(\n\x0etoapp_err_code\x18\x07 \x01(\x0b\x32\x0e.SysDevErrCodeH\x00\x12.\n\x13todev_job_plan_time\x18\n \x01(\x0b\x32\x0f.SysJobPlanTimeH\x00\x12%\n\x0etoapp_mow_info\x18\x0b \x01(\x0b\x32\x0b.SysMowInfoH\x00\x12&\n\x0f\x62idire_comm_cmd\x18\x0c \x01(\x0b\x32\x0b.SysCommCmdH\x00\x12\x16\n\x0cplan_job_del\x18\x0e \x01(\x03H\x00\x12\x1c\n\x06\x62order\x18\x0f \x01(\x0b\x32\n.SysBorderH\x00\x12.\n\x11toapp_plan_status\x18\x12 \x01(\x0b\x32\x11.SysPlanJobStatusH\x00\x12\x34\n\x12toapp_ul_fprogress\x18\x13 \x01(\x0b\x32\x16.SysUploadFileProgressH\x00\x12*\n\x10todev_deljobplan\x18\x14 \x01(\x0b\x32\x0e.SysDelJobPlanH\x00\x12\x1b\n\x11todev_mow_info_up\x18\x15 \x01(\x05H\x00\x12,\n\x10todev_knife_ctrl\x18\x16 \x01(\x0b\x32\x10.SysKnifeControlH\x00\x12\x1c\n\x12todev_reset_system\x18\x17 \x01(\x05H\x00\x12:\n\x19todev_reset_system_status\x18\x18 \x01(\x0b\x32\x15.SysResetSystemStatusH\x00\x12=\n\x16systemRapidStateTunnel\x18\x19 \x01(\x0b\x32\x1b.systemRapidStateTunnel_msgH\x00\x12;\n\x15systemTardStateTunnel\x18\x1a \x01(\x0b\x32\x1a.systemTardStateTunnel_msgH\x00\x12/\n\x0fsystemUpdateBuf\x18\x1b \x01(\x0b\x32\x14.systemUpdateBuf_msgH\x00\x12/\n\x15todev_time_ctrl_light\x18\x1c \x01(\x0b\x32\x0e.TimeCtrlLightH\x00\x12\x31\n\x10systemTmpCycleTx\x18\x1d \x01(\x0b\x32\x15.systemTmpCycleTx_msgH\x00\x12\x30\n\x14todev_off_chip_flash\x18\x1e \x01(\x0b\x32\x10.SysOffChipFlashH\x00\x12\x1f\n\x15todev_get_dev_fw_info\x18\x1f \x01(\x05H\x00\x12,\n\x11toapp_dev_fw_info\x18  \x01(\x0b\x32\x0f.device_fw_infoH\x00\x12)\n\x12todev_lora_cfg_req\x18! \x01(\x0b\x32\x0b.LoraCfgReqH\x00\x12)\n\x12toapp_lora_cfg_rsp\x18\" \x01(\x0b\x32\x0b.LoraCfgRspH\x00\x12-\n\x0fmow_to_app_info\x18# \x01(\x0b\x32\x12.mow_to_app_info_tH\x00\x12?\n\x18\x64\x65vice_product_type_info\x18$ \x01(\x0b\x32\x1b.device_product_type_info_tH\x00\x12=\n\x17mow_to_app_qctools_info\x18% \x01(\x0b\x32\x1a.mow_to_app_qctools_info_tH\x00\x12,\n\x10todev_report_cfg\x18& \x01(\x0b\x32\x10.report_info_cfgH\x00\x12.\n\x11toapp_report_data\x18\' \x01(\x0b\x32\x11.report_info_dataH\x00\x12\x31\n\x0esimulation_cmd\x18* \x01(\x0b\x32\x17.mCtrlSimulationCmdDataH\x00\x42\x0b\n\tSubSysMsg*+\n\tOperation\x12\t\n\x05WRITE\x10\x00\x12\x08\n\x04READ\x10\x01\x12\t\n\x05\x45RASE\x10\x02*\x8d\x02\n\tOffPartId\x12\x13\n\x0fOFF_PART_DL_IMG\x10\x00\x12\x19\n\x15OFF_PART_UPDINFO_BACK\x10\x01\x12\x14\n\x10OFF_PART_UPDINFO\x10\x02\x12\x13\n\x0fOFF_PART_NAKEDB\x10\x03\x12\x14\n\x10OFF_PART_FLASHDB\x10\x04\x12\x18\n\x14OFF_PART_UPD_APP_IMG\x10\x05\x12\x18\n\x14OFF_PART_UPD_BMS_IMG\x10\x06\x12\x18\n\x14OFF_PART_UPD_TMP_IMG\x10\x07\x12\x15\n\x11OFF_PART_DEV_INFO\x10\x08\x12\x18\n\x14OFF_PART_NAKEDB_BACK\x10\t\x12\x10\n\x0cOFF_PART_MAX\x10\n*\x95\x07\n\x0bQCAppTestId\x12!\n\x1dQC_APP_ITEM_ON_CHARGESATSTION\x10\x00\x12\x1a\n\x16QC_APP_TEST_X3_SPEAKER\x10\x01\x12)\n%QC_APP_TEST_STATIC_OBSTACLE_DETECTION\x10\x02\x12\"\n\x1eQC_APP_TEST_CHARGESTATION_TEMP\x10\x03\x12\x13\n\x0fQC_APP_ITEM_KEY\x10\x04\x12 \n\x1cQC_APP_TEST_BUMPER_FRONTLEFT\x10\x05\x12!\n\x1dQC_APP_TEST_BUMPER_FRONTRIGHT\x10\x06\x12\x14\n\x10QC_APP_TEST_STOP\x10\x07\x12\x16\n\x12QC_APP_TEST_UNLOCK\x10\x08\x12\x14\n\x10QC_APP_TEST_BUZZ\x10\t\x12\x14\n\x10QC_APP_TEST_LIFT\x10\n\x12\x16\n\x12QC_APP_ITEM_SENEOR\x10\x0b\x12\x19\n\x15QC_APP_TEST_ROLL_LEFT\x10\x0c\x12\x1a\n\x16QC_APP_TEST_ROLL_RIGHT\x10\r\x12\x1d\n\x19QC_APP_TEST_ULTRA_UNCOVER\x10\x0e\x12\x1c\n\x18QC_APP_TEST_ULTRA0_COVER\x10\x0f\x12\x1c\n\x18QC_APP_TEST_ULTRA1_COVER\x10\x10\x12\x1c\n\x18QC_APP_TEST_ULTRA2_COVER\x10\x11\x12\x14\n\x10QC_APP_TEST_RAIN\x10\x12\x12\x12\n\x0eQC_APP_ITEM_SQ\x10\x13\x12\x18\n\x14QC_APP_TEST_BLE_RSSI\x10\x14\x12 \n\x1cQC_APP_TEST_SATELLITES_ROVER\x10\x15\x12)\n%QC_APP_TEST_SATELLITES_REF_STATION_L1\x10\x16\x12)\n%QC_APP_TEST_SATELLITES_REF_STATION_L2\x10\x17\x12&\n\"QC_APP_TEST_SATELLITES_COMMON_VIEW\x10\x18\x12\x19\n\x15QC_APP_TEST_CNO_ROVER\x10\x19\x12\x1f\n\x1bQC_APP_TEST_CNO_REF_STATION\x10\x1a\x12\'\n#QC_APP_TEST_REF_STATION_LINK_STATUS\x10\x1b\x12\x1e\n\x1aQC_APP_TEST_LOCATION_STATE\x10\x1c\x12\x13\n\x0fQC_APP_TEST_MAX\x10\x1d*W\n\rnet_used_type\x12\x16\n\x12NET_USED_TYPE_NONE\x10\x00\x12\x16\n\x12NET_USED_TYPE_WIFI\x10\x01\x12\x16\n\x12NET_USED_TYPE_MNET\x10\x02*\xd9\x01\n\rrpt_info_type\x12\x0f\n\x0bRIT_CONNECT\x10\x00\x12\x0f\n\x0bRIT_DEV_STA\x10\x01\x12\x0b\n\x07RIT_RTK\x10\x02\x12\x11\n\rRIT_DEV_LOCAL\x10\x03\x12\x0c\n\x08RIT_WORK\x10\x04\x12\x0f\n\x0bRIT_FW_INFO\x10\x05\x12\x10\n\x0cRIT_MAINTAIN\x10\x06\x12\x14\n\x10RIT_VISION_POINT\x10\x07\x12\x0b\n\x07RIT_VIO\x10\x08\x12\x18\n\x14RIT_VISION_STATISTIC\x10\t\x12\x18\n\x14RIT_BASESTATION_INFO\x10\n*4\n\x07rpt_act\x12\r\n\tRPT_START\x10\x00\x12\x0c\n\x08RPT_STOP\x10\x01\x12\x0c\n\x08RPT_KEEP\x10\x02\x62\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'pymammotion.proto.mctrl_sys_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  _OPERATION._serialized_start=7993
  _OPERATION._serialized_end=8036
  _OFFPARTID._serialized_start=8039
  _OFFPARTID._serialized_end=8308
  _QCAPPTESTID._serialized_start=8311
  _QCAPPTESTID._serialized_end=9228
  _NET_USED_TYPE._serialized_start=9230
  _NET_USED_TYPE._serialized_end=9317
  _RPT_INFO_TYPE._serialized_start=9320
  _RPT_INFO_TYPE._serialized_end=9537
  _RPT_ACT._serialized_start=9539
  _RPT_ACT._serialized_end=9591
  _SYSBATUP._serialized_start=70
  _SYSBATUP._serialized_end=96
  _SYSWORKSTATE._serialized_start=98
  _SYSWORKSTATE._serialized_end=188
  _SYSSETTIMEZONE._serialized_start=190
  _SYSSETTIMEZONE._serialized_end=243
  _SYSSETDATETIME._serialized_start=246
  _SYSSETDATETIME._serialized_end=404
  _SYSJOBPLAN._serialized_start=406
  _SYSJOBPLAN._serialized_end=492
  _SYSDEVERRCODE._serialized_start=494
  _SYSDEVERRCODE._serialized_end=528
  _SYSBOARDTYPE._serialized_start=530
  _SYSBOARDTYPE._serialized_end=563
  _SYSSWVERSION._serialized_start=565
  _SYSSWVERSION._serialized_end=618
  _SYSDELJOBPLAN._serialized_start=620
  _SYSDELJOBPLAN._serialized_end=669
  _SYSJOBPLANTIME._serialized_start=672
  _SYSJOBPLANTIME._serialized_end=908
  _SYSMOWINFO._serialized_start=910
  _SYSMOWINFO._serialized_end=1019
  _SYSOPTILINEACK._serialized_start=1021
  _SYSOPTILINEACK._serialized_end=1080
  _SYSCOMMCMD._serialized_start=1082
  _SYSCOMMCMD._serialized_end=1135
  _SYSUPLOADFILEPROGRESS._serialized_start=1137
  _SYSUPLOADFILEPROGRESS._serialized_end=1209
  _SYSERRORCODE._serialized_start=1211
  _SYSERRORCODE._serialized_end=1242
  _SYSBORDER._serialized_start=1244
  _SYSBORDER._serialized_end=1274
  _SYSPLANJOBSTATUS._serialized_start=1276
  _SYSPLANJOBSTATUS._serialized_end=1318
  _SYSKNIFECONTROL._serialized_start=1320
  _SYSKNIFECONTROL._serialized_end=1381
  _SYSRESETSYSTEMSTATUS._serialized_start=1383
  _SYSRESETSYSTEMSTATUS._serialized_end=1426
  _TIMECTRLLIGHT._serialized_start=1429
  _TIMECTRLLIGHT._serialized_end=1567
  _VISION_POINT_MSG._serialized_start=1569
  _VISION_POINT_MSG._serialized_end=1620
  _VISION_POINT_INFO_MSG._serialized_start=1622
  _VISION_POINT_INFO_MSG._serialized_end=1714
  _VIO_TO_APP_INFO_MSG._serialized_start=1717
  _VIO_TO_APP_INFO_MSG._serialized_end=1871
  _VISION_STATISTIC_MSG._serialized_start=1873
  _VISION_STATISTIC_MSG._serialized_end=1922
  _VISION_STATISTIC_INFO_MSG._serialized_start=1924
  _VISION_STATISTIC_INFO_MSG._serialized_end=2033
  _SYSTEMRAPIDSTATETUNNEL_MSG._serialized_start=2036
  _SYSTEMRAPIDSTATETUNNEL_MSG._serialized_end=2247
  _SYSTEMTARDSTATETUNNEL_MSG._serialized_start=2249
  _SYSTEMTARDSTATETUNNEL_MSG._serialized_end=2301
  _SYSTEMUPDATEBUF_MSG._serialized_start=2303
  _SYSTEMUPDATEBUF_MSG._serialized_end=2349
  _SYSOFFCHIPFLASH._serialized_start=2352
  _SYSOFFCHIPFLASH._serialized_end=2510
  _SYSTEMTMPCYCLETX_MSG._serialized_start=2512
  _SYSTEMTMPCYCLETX_MSG._serialized_end=2557
  _LORACFGREQ._serialized_start=2559
  _LORACFGREQ._serialized_end=2596
  _LORACFGRSP._serialized_start=2598
  _LORACFGRSP._serialized_end=2668
  _MOD_FW_INFO._serialized_start=2670
  _MOD_FW_INFO._serialized_end=2732
  _DEVICE_FW_INFO._serialized_start=2734
  _DEVICE_FW_INFO._serialized_end=2810
  _MOW_TO_APP_INFO_T._serialized_start=2812
  _MOW_TO_APP_INFO_T._serialized_end=2876
  _DEVICE_PRODUCT_TYPE_INFO_T._serialized_start=2878
  _DEVICE_PRODUCT_TYPE_INFO_T._serialized_end=2975
  _QCAPPTESTEXCEPT._serialized_start=2977
  _QCAPPTESTEXCEPT._serialized_end=3057
  _QCAPPTESTCONDITIONS._serialized_start=3059
  _QCAPPTESTCONDITIONS._serialized_end=3175
  _MOW_TO_APP_QCTOOLS_INFO_T._serialized_start=3178
  _MOW_TO_APP_QCTOOLS_INFO_T._serialized_end=3331
  _MCTRLSIMULATIONCMDDATA._serialized_start=3333
  _MCTRLSIMULATIONCMDDATA._serialized_end=3412
  _RPT_LORA._serialized_start=3415
  _RPT_LORA._serialized_end=3558
  _MQTT_RTK_CONNECT._serialized_start=3560
  _MQTT_RTK_CONNECT._serialized_end=3641
  _RPT_RTK._serialized_start=3644
  _RPT_RTK._serialized_end=3927
  _RPT_DEV_LOCATION._serialized_start=3930
  _RPT_DEV_LOCATION._serialized_end=4064
  _VIO_SURVIVAL_INFO_T._serialized_start=4066
  _VIO_SURVIVAL_INFO_T._serialized_end=4118
  _COLLECTOR_STATUS_T._serialized_start=4120
  _COLLECTOR_STATUS_T._serialized_end=4179
  _LOCK_STATE_T._serialized_start=4181
  _LOCK_STATE_T._serialized_end=4215
  _RPT_DEV_STATUS._serialized_start=4218
  _RPT_DEV_STATUS._serialized_end=4613
  _RPT_CONNECT_STATUS._serialized_start=4616
  _RPT_CONNECT_STATUS._serialized_end=4814
  _NAV_HEADING_STATE_T._serialized_start=4816
  _NAV_HEADING_STATE_T._serialized_end=4860
  _RPT_WORK._serialized_start=4863
  _RPT_WORK._serialized_end=5328
  _BLADE_USED._serialized_start=5330
  _BLADE_USED._serialized_end=5397
  _USER_SET_BLADE_USED_WARN_TIME._serialized_start=5399
  _USER_SET_BLADE_USED_WARN_TIME._serialized_end=5460
  _RPT_MAINTAIN._serialized_start=5462
  _RPT_MAINTAIN._serialized_end=5570
  _FPV_TO_APP_INFO_T._serialized_start=5572
  _FPV_TO_APP_INFO_T._serialized_end=5663
  _RPT_BASESTATION_INFO._serialized_start=5666
  _RPT_BASESTATION_INFO._serialized_end=5830
  _REPORT_INFO_CFG._serialized_start=5833
  _REPORT_INFO_CFG._serialized_end=5976
  _REPORT_INFO_DATA._serialized_start=5979
  _REPORT_INFO_DATA._serialized_end=6424
  _MCTLSYS._serialized_start=6427
  _MCTLSYS._serialized_end=7991
# @@protoc_insertion_point(module_scope)
