# -*- coding: utf-8 -*-
# Generated by the protocol buffer compiler.  DO NOT EDIT!
# source: pymammotion/proto/mctrl_nav.proto
"""Generated protocol buffer code."""
from google.protobuf.internal import builder as _builder
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
# @@protoc_insertion_point(imports)

_sym_db = _symbol_database.Default()


from pymammotion.proto import common_pb2 as pymammotion_dot_proto_dot_common__pb2


DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n!pymammotion/proto/mctrl_nav.proto\x1a\x1epymammotion/proto/common.proto\"\'\n\x0bNavLatLonUp\x12\x0b\n\x03lat\x18\x01 \x01(\x01\x12\x0b\n\x03lon\x18\x02 \x01(\x01\"!\n\x0eNavBorderState\x12\x0f\n\x07\x62\x64state\x18\x01 \x01(\x05\"\xc9\x01\n\x08NavPosUp\x12\t\n\x01x\x18\x01 \x01(\x02\x12\t\n\x01y\x18\x02 \x01(\x02\x12\x0e\n\x06status\x18\x03 \x01(\x05\x12\x0e\n\x06toward\x18\x04 \x01(\x05\x12\r\n\x05stars\x18\x05 \x01(\x05\x12\x0b\n\x03\x61ge\x18\x06 \x01(\x02\x12\x11\n\tlatStddev\x18\x07 \x01(\x02\x12\x11\n\tlonStddev\x18\x08 \x01(\x02\x12\x11\n\tl2dfStars\x18\t \x01(\x05\x12\x0f\n\x07posType\x18\n \x01(\x05\x12\x0f\n\x07\x63HashId\x18\x0b \x01(\x03\x12\x10\n\x08posLevel\x18\x0c \x01(\x05\":\n\x13NavBorderDataGetAck\x12\r\n\x05jobId\x18\x01 \x01(\x05\x12\x14\n\x0c\x63urrentFrame\x18\x02 \x01(\x05\"Z\n\x15NavObstiBorderDataGet\x12\x15\n\robstacleIndex\x18\x01 \x01(\x05\x12\x14\n\x0c\x63urrentFrame\x18\x02 \x01(\x05\x12\x14\n\x0cobstaclesLen\x18\x03 \x01(\x05\"G\n\x18NavObstiBorderDataGetAck\x12\x15\n\robstacleIndex\x18\x01 \x01(\x05\x12\x14\n\x0c\x63urrentFrame\x18\x02 \x01(\x05\"d\n\x0eNavCHlLineData\x12\x12\n\nstartJobRI\x18\x01 \x01(\x05\x12\x10\n\x08\x65ndJobRI\x18\x02 \x01(\x05\x12\x14\n\x0c\x63urrentFrame\x18\x03 \x01(\x05\x12\x16\n\x0e\x63hannelLineLen\x18\x04 \x01(\x05\"O\n\x11NavCHlLineDataAck\x12\x12\n\nstartJobRI\x18\x01 \x01(\x05\x12\x10\n\x08\x65ndJobRI\x18\x02 \x01(\x05\x12\x14\n\x0c\x63urrentFrame\x18\x03 \x01(\x05\"\x7f\n\x0bNavTaskInfo\x12\x0c\n\x04\x61rea\x18\x01 \x01(\x05\x12\x0c\n\x04time\x18\x02 \x01(\x05\x12\x10\n\x08\x61llFrame\x18\x03 \x01(\x05\x12\x14\n\x0c\x63urrentFrame\x18\x04 \x01(\x05\x12\x0f\n\x07pathlen\x18\x05 \x01(\x05\x12\x1b\n\x02\x64\x63\x18\x06 \x03(\x0b\x32\x0f.CommDataCouple\"J\n\x10NavBorderDataGet\x12\r\n\x05jobId\x18\x01 \x01(\x05\x12\x14\n\x0c\x63urrentFrame\x18\x02 \x01(\x05\x12\x11\n\tborderLen\x18\x03 \x01(\x05\"\x91\x01\n\x0cNavOptLineUp\x12\x12\n\nstartJobRI\x18\x01 \x01(\x05\x12\x10\n\x08\x65ndJobRI\x18\x02 \x01(\x05\x12\x10\n\x08\x61llFrame\x18\x03 \x01(\x05\x12\x14\n\x0c\x63urrentFrame\x18\x04 \x01(\x05\x12\x16\n\x0e\x63hannelDataLen\x18\x05 \x01(\x05\x12\x1b\n\x02\x64\x63\x18\x06 \x03(\x0b\x32\x0f.CommDataCouple\"~\n\x11NavOptiBorderInfo\x12\r\n\x05jobId\x18\x01 \x01(\x05\x12\x10\n\x08\x61llFrame\x18\x02 \x01(\x05\x12\x14\n\x0c\x63urrentFrame\x18\x03 \x01(\x05\x12\x15\n\rborderDataLen\x18\x04 \x01(\x05\x12\x1b\n\x02\x64\x63\x18\x05 \x03(\x0b\x32\x0f.CommDataCouple\"\x81\x01\n\rNavOptObsInfo\x12\x12\n\nobstacleId\x18\x01 \x01(\x05\x12\x10\n\x08\x61llFrame\x18\x02 \x01(\x05\x12\x14\n\x0c\x63urrentFrame\x18\x03 \x01(\x05\x12\x17\n\x0fobstacleDataLen\x18\x04 \x01(\x05\x12\x1b\n\x02\x64\x63\x18\x05 \x03(\x0b\x32\x0f.CommDataCouple\"\xb4\x01\n\x0bNavStartJob\x12\r\n\x05jobId\x18\x01 \x01(\x03\x12\x0e\n\x06jobVer\x18\x02 \x01(\x05\x12\x0f\n\x07jobMode\x18\x03 \x01(\x05\x12\x13\n\x0brainTactics\x18\x04 \x01(\x05\x12\x13\n\x0bknifeHeight\x18\x05 \x01(\x05\x12\r\n\x05speed\x18\x06 \x01(\x02\x12\x14\n\x0c\x63hannelWidth\x18\x07 \x01(\x05\x12\x11\n\tUltraWave\x18\x08 \x01(\x05\x12\x13\n\x0b\x63hannelMode\x18\t \x01(\x05\"\'\n\x0fNavTaskProgress\x12\x14\n\x0ctaskProgress\x18\x01 \x01(\x05\"\x1e\n\x0bNavResFrame\x12\x0f\n\x07\x66rameid\x18\x01 \x01(\x05\"|\n\x0eNavGetHashList\x12\x0c\n\x04pver\x18\x01 \x01(\x05\x12\x0e\n\x06subCmd\x18\x02 \x01(\x05\x12\x12\n\ntotalFrame\x18\x03 \x01(\x05\x12\x14\n\x0c\x63urrentFrame\x18\x04 \x01(\x05\x12\x10\n\x08\x64\x61taHash\x18\x05 \x01(\x06\x12\x10\n\x08reserved\x18\x06 \x01(\t\"\xb4\x01\n\x11NavGetHashListAck\x12\x0c\n\x04pver\x18\x01 \x01(\x05\x12\x0e\n\x06subCmd\x18\x02 \x01(\x05\x12\x12\n\ntotalFrame\x18\x03 \x01(\x05\x12\x14\n\x0c\x63urrentFrame\x18\x04 \x01(\x05\x12\x10\n\x08\x64\x61taHash\x18\x05 \x01(\x06\x12\x0f\n\x07hashLen\x18\x06 \x01(\x05\x12\x10\n\x08reserved\x18\x07 \x01(\t\x12\x0e\n\x06result\x18\x08 \x01(\x05\x12\x12\n\ndataCouple\x18\r \x03(\x03\"\xd6\x01\n\x0eNavGetCommData\x12\x0c\n\x04pver\x18\x01 \x01(\x05\x12\x0e\n\x06subCmd\x18\x02 \x01(\x05\x12\x0e\n\x06\x61\x63tion\x18\x03 \x01(\x05\x12\x0c\n\x04type\x18\x04 \x01(\x05\x12\x0c\n\x04Hash\x18\x05 \x01(\x03\x12\x15\n\rpaternalHashA\x18\x06 \x01(\x03\x12\x15\n\rpaternalHashB\x18\x07 \x01(\x03\x12\x12\n\ntotalFrame\x18\x08 \x01(\x05\x12\x14\n\x0c\x63urrentFrame\x18\t \x01(\x05\x12\x10\n\x08\x64\x61taHash\x18\n \x01(\x06\x12\x10\n\x08reserved\x18\x0b \x01(\t\"\x9f\x02\n\x11NavGetCommDataAck\x12\x0c\n\x04pver\x18\x01 \x01(\x05\x12\x0e\n\x06subCmd\x18\x02 \x01(\x05\x12\x0e\n\x06result\x18\x03 \x01(\x05\x12\x0e\n\x06\x61\x63tion\x18\x04 \x01(\x05\x12\x0c\n\x04type\x18\x05 \x01(\x05\x12\x0c\n\x04Hash\x18\x06 \x01(\x06\x12\x15\n\rpaternalHashA\x18\x07 \x01(\x06\x12\x15\n\rpaternalHashB\x18\x08 \x01(\x06\x12\x12\n\ntotalFrame\x18\t \x01(\x05\x12\x14\n\x0c\x63urrentFrame\x18\n \x01(\x05\x12\x10\n\x08\x64\x61taHash\x18\x0b \x01(\x06\x12\x0f\n\x07\x64\x61taLen\x18\x0c \x01(\x05\x12#\n\ndataCouple\x18\r \x03(\x0b\x32\x0f.CommDataCouple\x12\x10\n\x08reserved\x18\x0e \x01(\t\"\xde\x02\n\x0fNavReqCoverPath\x12\x0c\n\x04pver\x18\x01 \x01(\x05\x12\r\n\x05jobId\x18\x02 \x01(\x03\x12\x0e\n\x06jobVer\x18\x03 \x01(\x05\x12\x0f\n\x07jobMode\x18\x04 \x01(\x05\x12\x0e\n\x06subCmd\x18\x05 \x01(\x05\x12\x10\n\x08\x65\x64geMode\x18\x06 \x01(\x05\x12\x13\n\x0bknifeHeight\x18\x07 \x01(\x05\x12\x14\n\x0c\x63hannelWidth\x18\x08 \x01(\x05\x12\x11\n\tUltraWave\x18\t \x01(\x05\x12\x13\n\x0b\x63hannelMode\x18\n \x01(\x05\x12\x0e\n\x06toward\x18\x0b \x01(\x05\x12\r\n\x05speed\x18\x0c \x01(\x02\x12\x11\n\tzoneHashs\x18\r \x03(\x06\x12\x10\n\x08pathHash\x18\x0e \x01(\x06\x12\x10\n\x08reserved\x18\x0f \x01(\t\x12\x0e\n\x06result\x18\x10 \x01(\x05\x12\x13\n\x0btoward_mode\x18\x11 \x01(\x05\x12\x1d\n\x15toward_included_angle\x18\x12 \x01(\x05\"\xa7\x03\n\x15NavUploadZigZagResult\x12\x0c\n\x04pver\x18\x01 \x01(\x05\x12\r\n\x05jobId\x18\x02 \x01(\x03\x12\x0e\n\x06jobVer\x18\x03 \x01(\x05\x12\x0e\n\x06result\x18\x04 \x01(\x05\x12\x0c\n\x04\x61rea\x18\x05 \x01(\x05\x12\x0c\n\x04time\x18\x06 \x01(\x05\x12\x14\n\x0ctotalZoneNum\x18\x07 \x01(\x05\x12\x1a\n\x12\x63urrentZonePathNum\x18\x08 \x01(\x05\x12\x19\n\x11\x63urrentZonePathId\x18\t \x01(\x05\x12\x13\n\x0b\x63urrentZone\x18\n \x01(\x05\x12\x13\n\x0b\x63urrentHash\x18\x0b \x01(\x06\x12\x12\n\ntotalFrame\x18\x0c \x01(\x05\x12\x14\n\x0c\x63urrentFrame\x18\r \x01(\x05\x12\x13\n\x0b\x63hannelMode\x18\x0e \x01(\x05\x12\x15\n\rchannelModeId\x18\x0f \x01(\x05\x12\x10\n\x08\x64\x61taHash\x18\x10 \x01(\x06\x12\x0f\n\x07\x64\x61taLen\x18\x11 \x01(\x05\x12\x10\n\x08reserved\x18\x12 \x01(\t\x12#\n\ndataCouple\x18\x13 \x03(\x0b\x32\x0f.CommDataCouple\x12\x0e\n\x06subCmd\x18\x14 \x01(\x05\"\xb0\x01\n\x18NavUploadZigZagResultAck\x12\x0c\n\x04pver\x18\x01 \x01(\x05\x12\x13\n\x0b\x63urrentZone\x18\x02 \x01(\x05\x12\x13\n\x0b\x63urrentHash\x18\x03 \x01(\x06\x12\x12\n\ntotalFrame\x18\x04 \x01(\x05\x12\x14\n\x0c\x63urrentFrame\x18\x05 \x01(\x05\x12\x10\n\x08\x64\x61taHash\x18\x06 \x01(\x06\x12\x10\n\x08reserved\x18\x07 \x01(\t\x12\x0e\n\x06subCmd\x18\x08 \x01(\x05\"M\n\x0bNavTaskCtrl\x12\x0c\n\x04type\x18\x01 \x01(\x05\x12\x0e\n\x06\x61\x63tion\x18\x02 \x01(\x05\x12\x0e\n\x06result\x18\x03 \x01(\x05\x12\x10\n\x08reserved\x18\x04 \x01(\t\"o\n\x0bNavTaskIdRw\x12\x0c\n\x04pver\x18\x01 \x01(\x05\x12\x0e\n\x06subCmd\x18\x02 \x01(\x05\x12\x10\n\x08taskName\x18\x03 \x01(\t\x12\x0e\n\x06taskId\x18\x04 \x01(\t\x12\x0e\n\x06result\x18\x05 \x01(\x05\x12\x10\n\x08reserved\x18\x06 \x01(\t\"J\n\x12NavSysHashOverview\x12\x1a\n\x12\x63ommonhashOverview\x18\x01 \x01(\x06\x12\x18\n\x10pathHashOverview\x18\x02 \x01(\x06\"i\n\x11NavTaskBreakPoint\x12\t\n\x01x\x18\x01 \x01(\x02\x12\t\n\x01y\x18\x02 \x01(\x02\x12\x0e\n\x06toward\x18\x03 \x01(\x05\x12\x0c\n\x04\x66lag\x18\x04 \x01(\x05\x12\x0e\n\x06\x61\x63tion\x18\x05 \x01(\x05\x12\x10\n\x08zoneHash\x18\x06 \x01(\x06\"\xc2\x05\n\rNavPlanJobSet\x12\x0c\n\x04pver\x18\x01 \x01(\x05\x12\x0e\n\x06subCmd\x18\x02 \x01(\x05\x12\x0c\n\x04\x61rea\x18\x03 \x01(\x05\x12\x10\n\x08workTime\x18\x04 \x01(\x05\x12\x0f\n\x07version\x18\x05 \x01(\t\x12\n\n\x02id\x18\x06 \x01(\t\x12\x0e\n\x06userId\x18\x07 \x01(\t\x12\x10\n\x08\x64\x65viceId\x18\x08 \x01(\t\x12\x0e\n\x06planId\x18\t \x01(\t\x12\x0e\n\x06taskId\x18\n \x01(\t\x12\r\n\x05jobId\x18\x0b \x01(\t\x12\x11\n\tstartTime\x18\x0c \x01(\t\x12\x0f\n\x07\x65ndTime\x18\r \x01(\t\x12\x0c\n\x04week\x18\x0e \x01(\x05\x12\x13\n\x0bknifeHeight\x18\x0f \x01(\x05\x12\r\n\x05model\x18\x10 \x01(\x05\x12\x10\n\x08\x65\x64geMode\x18\x11 \x01(\x05\x12\x14\n\x0crequiredTime\x18\x12 \x01(\x05\x12\x12\n\nrouteAngle\x18\x13 \x01(\x05\x12\x12\n\nrouteModel\x18\x14 \x01(\x05\x12\x14\n\x0crouteSpacing\x18\x15 \x01(\x05\x12\x19\n\x11ultrasonicBarrier\x18\x16 \x01(\x05\x12\x14\n\x0ctotalPlanNum\x18\x17 \x01(\x05\x12\x11\n\tPlanIndex\x18\x18 \x01(\x05\x12\x0e\n\x06result\x18\x19 \x01(\x05\x12\r\n\x05speed\x18\x1a \x01(\x02\x12\x10\n\x08taskName\x18\x1b \x01(\t\x12\x0f\n\x07jobName\x18\x1c \x01(\t\x12\x11\n\tzoneHashs\x18\x1d \x03(\x06\x12\x10\n\x08reserved\x18\x1e \x01(\t\x12\x11\n\tstartDate\x18\x1f \x01(\t\x12\x0f\n\x07\x65ndDate\x18  \x01(\t\x12\x13\n\x0btriggerType\x18! \x01(\x05\x12\x0b\n\x03\x64\x61y\x18\" \x01(\x05\x12\r\n\x05weeks\x18# \x03(\x07\x12\x18\n\x10remained_seconds\x18$ \x01(\x03\x12\x12\n\ntowardMode\x18% \x01(\x05\x12\x1b\n\x13towardIncludedAngle\x18& \x01(\x05\"\x86\x01\n\x10NavUnableTimeSet\x12\x0e\n\x06subCmd\x18\x01 \x01(\x05\x12\x10\n\x08\x64\x65viceId\x18\x02 \x01(\t\x12\x17\n\x0funableStartTime\x18\x03 \x01(\t\x12\x15\n\runableEndTime\x18\x04 \x01(\t\x12\x0e\n\x06result\x18\x05 \x01(\x05\x12\x10\n\x08reserved\x18\x06 \x01(\t\"6\n\x0e\x63hargePileType\x12\x0e\n\x06toward\x18\x01 \x01(\x05\x12\t\n\x01x\x18\x02 \x01(\x02\x12\t\n\x01y\x18\x03 \x01(\x02\"J\n\x11SimulationCmdData\x12\x0e\n\x06subCmd\x18\x01 \x01(\x05\x12\x10\n\x08param_id\x18\x02 \x01(\x05\x12\x13\n\x0bparam_value\x18\x03 \x03(\x05\"%\n\x13WorkReportUpdateCmd\x12\x0e\n\x06subCmd\x18\x01 \x01(\x05\"<\n\x13WorkReportUpdateAck\x12\x13\n\x0bupdate_flag\x18\x01 \x01(\x08\x12\x10\n\x08info_num\x18\x02 \x01(\x05\"7\n\x11WorkReportCmdData\x12\x0e\n\x06subCmd\x18\x01 \x01(\x05\x12\x12\n\ngetInfoNum\x18\x02 \x01(\x05\"\x8e\x02\n\x11WorkReportInfoAck\x12\x16\n\x0einterrupt_flag\x18\x01 \x01(\x08\x12\x17\n\x0fstart_work_time\x18\x02 \x01(\x03\x12\x15\n\rend_work_time\x18\x03 \x01(\x03\x12\x16\n\x0ework_time_used\x18\x04 \x01(\x05\x12\x11\n\twork_ares\x18\x05 \x01(\x01\x12\x15\n\rwork_progress\x18\x06 \x01(\x05\x12\x17\n\x0fheight_of_knife\x18\x07 \x01(\x05\x12\x11\n\twork_type\x18\x08 \x01(\x05\x12\x13\n\x0bwork_result\x18\t \x01(\x05\x12\x15\n\rtotal_ack_num\x18\n \x01(\x05\x12\x17\n\x0f\x63urrent_ack_num\x18\x0b \x01(\x05\"\xb2\x01\n\x19\x61pp_request_cover_paths_t\x12\x0c\n\x04pver\x18\x01 \x01(\x05\x12\x0e\n\x06subCmd\x18\x02 \x01(\x05\x12\x12\n\ntotalFrame\x18\x03 \x01(\x05\x12\x14\n\x0c\x63urrentFrame\x18\x04 \x01(\x05\x12\x10\n\x08\x64\x61taHash\x18\x05 \x01(\x06\x12\x16\n\x0etransaction_id\x18\x06 \x01(\x03\x12\x10\n\x08reserved\x18\x07 \x03(\x03\x12\x11\n\thash_list\x18\x08 \x03(\x06\"\x99\x01\n\x13\x63over_path_packet_t\x12\x11\n\tpath_hash\x18\x01 \x01(\x06\x12\x11\n\tpath_type\x18\x02 \x01(\x05\x12\x12\n\npath_total\x18\x03 \x01(\x05\x12\x10\n\x08path_cur\x18\x04 \x01(\x05\x12\x11\n\tzone_hash\x18\x05 \x01(\x06\x12#\n\ndataCouple\x18\x06 \x03(\x0b\x32\x0f.CommDataCouple\"\xb2\x02\n\x13\x63over_path_upload_t\x12\x0c\n\x04pver\x18\x01 \x01(\x05\x12\x0e\n\x06result\x18\x02 \x01(\x05\x12\x0e\n\x06subCmd\x18\x03 \x01(\x05\x12\x0c\n\x04\x61rea\x18\x04 \x01(\x05\x12\x0c\n\x04time\x18\x05 \x01(\x05\x12\x12\n\ntotalFrame\x18\x06 \x01(\x05\x12\x14\n\x0c\x63urrentFrame\x18\x07 \x01(\x05\x12\x16\n\x0etotal_path_num\x18\x08 \x01(\x05\x12\x16\n\x0evaild_path_num\x18\t \x01(\x05\x12\x10\n\x08\x64\x61taHash\x18\n \x01(\x06\x12\x16\n\x0etransaction_id\x18\x0b \x01(\x03\x12\x10\n\x08reserved\x18\x0c \x03(\x03\x12\x0f\n\x07\x64\x61taLen\x18\r \x01(\x05\x12*\n\x0cpath_packets\x18\x0e \x03(\x0b\x32\x14.cover_path_packet_t\"M\n\x14zone_start_precent_t\x12\x10\n\x08\x64\x61taHash\x18\x01 \x01(\x06\x12\t\n\x01x\x18\x02 \x01(\x02\x12\t\n\x01y\x18\x03 \x01(\x02\x12\r\n\x05index\x18\x04 \x01(\x05\",\n\x0fvision_ctrl_msg\x12\x0c\n\x04type\x18\x01 \x01(\x05\x12\x0b\n\x03\x63md\x18\x02 \x01(\x05\"<\n\x11nav_sys_param_msg\x12\n\n\x02rw\x18\x01 \x01(\x05\x12\n\n\x02id\x18\x02 \x01(\x05\x12\x0f\n\x07\x63ontext\x18\x03 \x01(\x05\"Q\n\x15nav_plan_task_execute\x12\x0e\n\x06subCmd\x18\x01 \x01(\x05\x12\n\n\x02id\x18\x02 \x01(\t\x12\x0c\n\x04name\x18\x03 \x01(\t\x12\x0e\n\x06result\x18\x04 \x01(\x05\"y\n\tcostmap_t\x12\r\n\x05width\x18\x01 \x01(\x05\x12\x0e\n\x06height\x18\x02 \x01(\x05\x12\x10\n\x08\x63\x65nter_x\x18\x03 \x01(\x02\x12\x10\n\x08\x63\x65nter_y\x18\x04 \x01(\x02\x12\x0b\n\x03yaw\x18\x05 \x01(\x02\x12\x0b\n\x03res\x18\x06 \x01(\x02\x12\x0f\n\x07\x63ostmap\x18\x07 \x03(\x05\"/\n\x13plan_task_name_id_t\x12\n\n\x02id\x18\x01 \x01(\t\x12\x0c\n\x04name\x18\x02 \x01(\t\"<\n\x15nav_get_all_plan_task\x12#\n\x05tasks\x18\x01 \x03(\x0b\x32\x14.plan_task_name_id_t\"c\n\x0eNavTaskCtrlAck\x12\x0c\n\x04type\x18\x01 \x01(\x05\x12\x0e\n\x06\x61\x63tion\x18\x02 \x01(\x05\x12\x0e\n\x06result\x18\x03 \x01(\x05\x12\x11\n\tnav_state\x18\x04 \x01(\x05\x12\x10\n\x08reserved\x18\x05 \x01(\t\"Z\n\rNavMapNameMsg\x12\n\n\x02rw\x18\x01 \x01(\x05\x12\x0c\n\x04hash\x18\x02 \x01(\x03\x12\x0c\n\x04name\x18\x03 \x01(\t\x12\x0e\n\x06result\x18\x04 \x01(\x05\x12\x11\n\tdevice_id\x18\x05 \x01(\t\"\x94\x02\n\rsvg_message_t\x12\x0e\n\x06x_move\x18\x01 \x01(\x01\x12\x0e\n\x06y_move\x18\x02 \x01(\x01\x12\r\n\x05scale\x18\x03 \x01(\x01\x12\x0e\n\x06rotate\x18\x04 \x01(\x01\x12\x14\n\x0c\x62\x61se_width_m\x18\x05 \x01(\x01\x12\x16\n\x0e\x62\x61se_width_pix\x18\x07 \x01(\x05\x12\x15\n\rbase_height_m\x18\x06 \x01(\x01\x12\x17\n\x0f\x62\x61se_height_pix\x18\x08 \x01(\x05\x12\x12\n\ndata_count\x18\x0c \x01(\x05\x12\x10\n\x08hide_svg\x18\r \x01(\x08\x12\x12\n\nname_count\x18\x0b \x01(\x05\x12\x15\n\rsvg_file_name\x18\t \x01(\t\x12\x15\n\rsvg_file_data\x18\n \x01(\t\"\xca\x01\n\x0eSvgMessageAckT\x12\x0c\n\x04pver\x18\x01 \x01(\x05\x12\x0f\n\x07sub_cmd\x18\x02 \x01(\x05\x12\x13\n\x0btotal_frame\x18\x03 \x01(\x05\x12\x15\n\rcurrent_frame\x18\x04 \x01(\x05\x12\x11\n\tdata_hash\x18\x05 \x01(\x03\x12\x17\n\x0fpaternal_hash_a\x18\x06 \x01(\x03\x12\x0c\n\x04type\x18\x07 \x01(\x05\x12\x0e\n\x06result\x18\x08 \x01(\x05\x12#\n\x0bsvg_message\x18\t \x01(\x0b\x32\x0e.svg_message_t\"*\n\x0c\x41reaHashName\x12\x0c\n\x04name\x18\x01 \x01(\t\x12\x0c\n\x04hash\x18\x02 \x01(\x03\"L\n\x15\x41ppGetAllAreaHashName\x12\x11\n\tdevice_id\x18\x01 \x01(\t\x12 \n\thashnames\x18\x02 \x03(\x0b\x32\r.AreaHashName\"\xe3\x14\n\x07MctlNav\x12$\n\x0ctoapp_lat_up\x18\x01 \x01(\x0b\x32\x0c.NavLatLonUpH\x00\x12!\n\x0ctoapp_pos_up\x18\x02 \x01(\x0b\x32\t.NavPosUpH\x00\x12.\n\x13todev_chl_line_data\x18\x03 \x01(\x0b\x32\x0f.NavCHlLineDataH\x00\x12\'\n\x0ftoapp_task_info\x18\x04 \x01(\x0b\x32\x0c.NavTaskInfoH\x00\x12*\n\x11toapp_opt_line_up\x18\x05 \x01(\x0b\x32\r.NavOptLineUpH\x00\x12\x33\n\x15toapp_opt_border_info\x18\x06 \x01(\x0b\x32\x12.NavOptiBorderInfoH\x00\x12,\n\x12toapp_opt_obs_info\x18\x07 \x01(\x0b\x32\x0e.NavOptObsInfoH\x00\x12+\n\x13todev_task_info_ack\x18\x08 \x01(\x0b\x32\x0c.NavResFrameH\x00\x12\x31\n\x19todev_opt_border_info_ack\x18\t \x01(\x0b\x32\x0c.NavResFrameH\x00\x12.\n\x16todev_opt_obs_info_ack\x18\n \x01(\x0b\x32\x0c.NavResFrameH\x00\x12-\n\x15todev_opt_line_up_ack\x18\x0b \x01(\x0b\x32\x0c.NavResFrameH\x00\x12*\n\x0ftoapp_chgpileto\x18\x0c \x01(\x0b\x32\x0f.chargePileTypeH\x00\x12\x17\n\rtodev_sustask\x18\r \x01(\x05H\x00\x12\x18\n\x0etodev_rechgcmd\x18\x0e \x01(\x05H\x00\x12\x17\n\rtodev_edgecmd\x18\x0f \x01(\x05H\x00\x12\x1b\n\x11todev_draw_border\x18\x10 \x01(\x05H\x00\x12\x1f\n\x15todev_draw_border_end\x18\x11 \x01(\x05H\x00\x12\x18\n\x0etodev_draw_obs\x18\x12 \x01(\x05H\x00\x12\x1c\n\x12todev_draw_obs_end\x18\x13 \x01(\x05H\x00\x12\x18\n\x0etodev_chl_line\x18\x14 \x01(\x05H\x00\x12\x1c\n\x12todev_chl_line_end\x18\x15 \x01(\x05H\x00\x12\x19\n\x0ftodev_save_task\x18\x16 \x01(\x05H\x00\x12\x1d\n\x13todev_cancel_suscmd\x18\x17 \x01(\x05H\x00\x12\x1e\n\x14todev_reset_chg_pile\x18\x18 \x01(\x05H\x00\x12\x1f\n\x15todev_cancel_draw_cmd\x18\x19 \x01(\x05H\x00\x12$\n\x1atodev_one_touch_leave_pile\x18\x1a \x01(\x05H\x00\x12&\n\x0etodev_mow_task\x18\x1b \x01(\x0b\x32\x0c.NavStartJobH\x00\x12\'\n\x0ctoapp_bstate\x18\x1c \x01(\x0b\x32\x0f.NavBorderStateH\x00\x12\x1a\n\x10todev_lat_up_ack\x18\x1d \x01(\x05H\x00\x12(\n\rtodev_gethash\x18\x1e \x01(\x0b\x32\x0f.NavGetHashListH\x00\x12/\n\x11toapp_gethash_ack\x18\x1f \x01(\x0b\x32\x12.NavGetHashListAckH\x00\x12/\n\x14todev_get_commondata\x18  \x01(\x0b\x32\x0f.NavGetCommDataH\x00\x12\x36\n\x18toapp_get_commondata_ack\x18! \x01(\x0b\x32\x12.NavGetCommDataAckH\x00\x12\x31\n\x15\x62idire_reqconver_path\x18\" \x01(\x0b\x32\x10.NavReqCoverPathH\x00\x12.\n\x0ctoapp_zigzag\x18# \x01(\x0b\x32\x16.NavUploadZigZagResultH\x00\x12\x35\n\x10todev_zigzag_ack\x18$ \x01(\x0b\x32\x19.NavUploadZigZagResultAckH\x00\x12&\n\x0etodev_taskctrl\x18% \x01(\x0b\x32\x0c.NavTaskCtrlH\x00\x12%\n\rbidire_taskid\x18& \x01(\x0b\x32\x0c.NavTaskIdRwH\x00\x12&\n\x08toapp_bp\x18\' \x01(\x0b\x32\x12.NavTaskBreakPointH\x00\x12+\n\x11todev_planjob_set\x18( \x01(\x0b\x32\x0e.NavPlanJobSetH\x00\x12\x32\n\x15todev_unable_time_set\x18) \x01(\x0b\x32\x11.NavUnableTimeSetH\x00\x12,\n\x0esimulation_cmd\x18* \x01(\x0b\x32\x12.SimulationCmdDataH\x00\x12<\n\x1ctodev_work_report_update_cmd\x18+ \x01(\x0b\x32\x14.WorkReportUpdateCmdH\x00\x12<\n\x1ctoapp_work_report_update_ack\x18, \x01(\x0b\x32\x14.WorkReportUpdateAckH\x00\x12\x33\n\x15todev_work_report_cmd\x18- \x01(\x0b\x32\x12.WorkReportCmdDataH\x00\x12\x33\n\x15toapp_work_report_ack\x18. \x01(\x0b\x32\x12.WorkReportInfoAckH\x00\x12\x36\n\x18toapp_work_report_upload\x18/ \x01(\x0b\x32\x12.WorkReportInfoAckH\x00\x12=\n\x17\x61pp_request_cover_paths\x18\x30 \x01(\x0b\x32\x1a.app_request_cover_paths_tH\x00\x12\x31\n\x11\x63over_path_upload\x18\x31 \x01(\x0b\x32\x14.cover_path_upload_tH\x00\x12\x33\n\x12zone_start_precent\x18\x32 \x01(\x0b\x32\x15.zone_start_precent_tH\x00\x12\'\n\x0bvision_ctrl\x18\x33 \x01(\x0b\x32\x10.vision_ctrl_msgH\x00\x12/\n\x11nav_sys_param_cmd\x18\x34 \x01(\x0b\x32\x12.nav_sys_param_msgH\x00\x12\x33\n\x11plan_task_execute\x18\x35 \x01(\x0b\x32\x16.nav_plan_task_executeH\x00\x12#\n\rtoapp_costmap\x18\x36 \x01(\x0b\x32\n.costmap_tH\x00\x12\x31\n\x11plan_task_name_id\x18\x37 \x01(\x0b\x32\x14.plan_task_name_id_tH\x00\x12/\n\rall_plan_task\x18\x38 \x01(\x0b\x32\x16.nav_get_all_plan_taskH\x00\x12-\n\x12todev_taskctrl_ack\x18\x39 \x01(\x0b\x32\x0f.NavTaskCtrlAckH\x00\x12,\n\x12toapp_map_name_msg\x18: \x01(\x0b\x32\x0e.NavMapNameMsgH\x00\x12(\n\rtodev_svg_msg\x18; \x01(\x0b\x32\x0f.SvgMessageAckTH\x00\x12(\n\rtoapp_svg_msg\x18< \x01(\x0b\x32\x0f.SvgMessageAckTH\x00\x12\x35\n\x13toapp_all_hash_name\x18= \x01(\x0b\x32\x16.AppGetAllAreaHashNameH\x00\x42\x0b\n\tSubNavMsgb\x06proto3')

_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, globals())
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'pymammotion.proto.mctrl_nav_pb2', globals())
if _descriptor._USE_C_DESCRIPTORS == False:

  DESCRIPTOR._options = None
  _NAVLATLONUP._serialized_start=69
  _NAVLATLONUP._serialized_end=108
  _NAVBORDERSTATE._serialized_start=110
  _NAVBORDERSTATE._serialized_end=143
  _NAVPOSUP._serialized_start=146
  _NAVPOSUP._serialized_end=347
  _NAVBORDERDATAGETACK._serialized_start=349
  _NAVBORDERDATAGETACK._serialized_end=407
  _NAVOBSTIBORDERDATAGET._serialized_start=409
  _NAVOBSTIBORDERDATAGET._serialized_end=499
  _NAVOBSTIBORDERDATAGETACK._serialized_start=501
  _NAVOBSTIBORDERDATAGETACK._serialized_end=572
  _NAVCHLLINEDATA._serialized_start=574
  _NAVCHLLINEDATA._serialized_end=674
  _NAVCHLLINEDATAACK._serialized_start=676
  _NAVCHLLINEDATAACK._serialized_end=755
  _NAVTASKINFO._serialized_start=757
  _NAVTASKINFO._serialized_end=884
  _NAVBORDERDATAGET._serialized_start=886
  _NAVBORDERDATAGET._serialized_end=960
  _NAVOPTLINEUP._serialized_start=963
  _NAVOPTLINEUP._serialized_end=1108
  _NAVOPTIBORDERINFO._serialized_start=1110
  _NAVOPTIBORDERINFO._serialized_end=1236
  _NAVOPTOBSINFO._serialized_start=1239
  _NAVOPTOBSINFO._serialized_end=1368
  _NAVSTARTJOB._serialized_start=1371
  _NAVSTARTJOB._serialized_end=1551
  _NAVTASKPROGRESS._serialized_start=1553
  _NAVTASKPROGRESS._serialized_end=1592
  _NAVRESFRAME._serialized_start=1594
  _NAVRESFRAME._serialized_end=1624
  _NAVGETHASHLIST._serialized_start=1626
  _NAVGETHASHLIST._serialized_end=1750
  _NAVGETHASHLISTACK._serialized_start=1753
  _NAVGETHASHLISTACK._serialized_end=1933
  _NAVGETCOMMDATA._serialized_start=1936
  _NAVGETCOMMDATA._serialized_end=2150
  _NAVGETCOMMDATAACK._serialized_start=2153
  _NAVGETCOMMDATAACK._serialized_end=2440
  _NAVREQCOVERPATH._serialized_start=2443
  _NAVREQCOVERPATH._serialized_end=2793
  _NAVUPLOADZIGZAGRESULT._serialized_start=2796
  _NAVUPLOADZIGZAGRESULT._serialized_end=3219
  _NAVUPLOADZIGZAGRESULTACK._serialized_start=3222
  _NAVUPLOADZIGZAGRESULTACK._serialized_end=3398
  _NAVTASKCTRL._serialized_start=3400
  _NAVTASKCTRL._serialized_end=3477
  _NAVTASKIDRW._serialized_start=3479
  _NAVTASKIDRW._serialized_end=3590
  _NAVSYSHASHOVERVIEW._serialized_start=3592
  _NAVSYSHASHOVERVIEW._serialized_end=3666
  _NAVTASKBREAKPOINT._serialized_start=3668
  _NAVTASKBREAKPOINT._serialized_end=3773
  _NAVPLANJOBSET._serialized_start=3776
  _NAVPLANJOBSET._serialized_end=4482
  _NAVUNABLETIMESET._serialized_start=4485
  _NAVUNABLETIMESET._serialized_end=4619
  _CHARGEPILETYPE._serialized_start=4621
  _CHARGEPILETYPE._serialized_end=4675
  _SIMULATIONCMDDATA._serialized_start=4677
  _SIMULATIONCMDDATA._serialized_end=4751
  _WORKREPORTUPDATECMD._serialized_start=4753
  _WORKREPORTUPDATECMD._serialized_end=4790
  _WORKREPORTUPDATEACK._serialized_start=4792
  _WORKREPORTUPDATEACK._serialized_end=4852
  _WORKREPORTCMDDATA._serialized_start=4854
  _WORKREPORTCMDDATA._serialized_end=4909
  _WORKREPORTINFOACK._serialized_start=4912
  _WORKREPORTINFOACK._serialized_end=5182
  _APP_REQUEST_COVER_PATHS_T._serialized_start=5185
  _APP_REQUEST_COVER_PATHS_T._serialized_end=5363
  _COVER_PATH_PACKET_T._serialized_start=5366
  _COVER_PATH_PACKET_T._serialized_end=5519
  _COVER_PATH_UPLOAD_T._serialized_start=5522
  _COVER_PATH_UPLOAD_T._serialized_end=5828
  _ZONE_START_PRECENT_T._serialized_start=5830
  _ZONE_START_PRECENT_T._serialized_end=5907
  _VISION_CTRL_MSG._serialized_start=5909
  _VISION_CTRL_MSG._serialized_end=5953
  _NAV_SYS_PARAM_MSG._serialized_start=5955
  _NAV_SYS_PARAM_MSG._serialized_end=6015
  _NAV_PLAN_TASK_EXECUTE._serialized_start=6017
  _NAV_PLAN_TASK_EXECUTE._serialized_end=6098
  _COSTMAP_T._serialized_start=6100
  _COSTMAP_T._serialized_end=6221
  _PLAN_TASK_NAME_ID_T._serialized_start=6223
  _PLAN_TASK_NAME_ID_T._serialized_end=6270
  _NAV_GET_ALL_PLAN_TASK._serialized_start=6272
  _NAV_GET_ALL_PLAN_TASK._serialized_end=6332
  _NAVTASKCTRLACK._serialized_start=6334
  _NAVTASKCTRLACK._serialized_end=6433
  _NAVMAPNAMEMSG._serialized_start=6435
  _NAVMAPNAMEMSG._serialized_end=6525
  _SVG_MESSAGE_T._serialized_start=6528
  _SVG_MESSAGE_T._serialized_end=6804
  _SVGMESSAGEACKT._serialized_start=6807
  _SVGMESSAGEACKT._serialized_end=7009
  _AREAHASHNAME._serialized_start=7011
  _AREAHASHNAME._serialized_end=7053
  _APPGETALLAREAHASHNAME._serialized_start=7055
  _APPGETALLAREAHASHNAME._serialized_end=7131
  _MCTLNAV._serialized_start=7134
  _MCTLNAV._serialized_end=9793
# @@protoc_insertion_point(module_scope)
