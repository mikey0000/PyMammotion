# sends as part of normal messages
# sys -> systemTardStateTunnel





systemTardStateTunnel = b'\x08\xf4\x01\x10\x01\x18\x07(\xbf\x96\x0b0\x01R`\xd2\x01]\n[\x0b\x01d<\x00\x00\xbc\xda\xcf\xf6\xf9\x98\xc2\xa8h\xb3\xe7\xcc\x90\xc3\x8e\x89\xbbm\xe1\x80\x84\x03\x00\x00\xba\xf3\xfe\xf1\xd6\x96\x91\xf2\x15\x81\xb2\xff\xff\xff\xff\xff\xff\xff\x01\xcc\x98\xfc\xff\xff\xff\xff\xff\xff\x01\x00\x00\x00\x89\xaf\xb7\xe7\xf7\x84\xc6\xd3L\x00\xb9\x95\x8c\xf6\xe6\xeb\xc1\xe1Y\xde\xd9\xd2\xfc\xab\xc2\x9b\x903\x00'

single_hash_result = b'\x00\x01\x08\xf0\x01\x10\x01\x18\x07(\xe8\xda\x0c0\x01Z\xf0\x01\x8a\x02\xec\x01\x08\x01 \x08194k\xf0\x00\xf0\xeaIH\x01P\x01`\x90\x01j\n\r\x0cg\x9c\xc1\x15,\x00\x92@j\n\r\x860\x9f\xc1\x15:R\x8b@j\n\r^\xb7\xa0\xc1\x15\x06\xa0z@j\n\r\xf6\xa7\x9e\xc1\x15%\xfe\n@j\n\r\xc0\x06\x96\xc1\x15Jb\xd2\xbfj\n\ry\xd4\x9a\xc1\x15\xcbs\xf3\xbfj\n\r\x1a\xbd\xa3\xc1\x151\x9b\x08\xc0j\n\r\xe5B\xa5\xc1\x15\x88\xc7\xfb\xbfj\n\rR;\xa7\xc1\x15\x96\xce\xb3\xbfj\n\r\\\xa3\xa7\xc1\x15\x9e\x86}\xbfj\n\r\xc3\xaa\xa9\xc1\x15N;\x07\xbfj\n\rb\x91\xad\xc1\x15\xb9\xe6>?j\n\r\xf1\xdc\xb4\xc1\x15\x1e\xba`@j\n\rBZ\xb8\xc1\x15\x17Jl@j\n\rL"\xb9\xc1\x15i\xda\x82@j\n\r\xa5\x06\xa2\xc1\x15%\x96\x99@j\n\r-\x8e\x9d\xc1\x15\x113\x9d@j\n\r\x0cg\x9c\xc1\x15,\x00\x92@'

# working
sys_rapid_state_tunnel = b'\x08\xf4\x01\x10\x01\x18\x07(\xfc\xed\x0e0\x01R&\xca\x01#\n!\x04\x02+\xb4\xbf\x01IL\x1b\xea\xbe\xf6\xff\xff\xff\xff\xff\xff\x01\x9a$\xfe\x96\xda\xff\xff\xff\xff\xff\xff\x01\x05\x00'


# 08f0011001180728c5e61530015a81018a027e08012008280131e135f3771a5184073939346bf000f0ea494801500160406a0a0d59c6a6c1156f5d40406a0a0d5c54a5c115d3101e406a0a0d8bdda7c115db5f02406a0a0d9d34aac1159889fe3f6a0a0d985eadc115ed8315406a0a0d5cc4acc1153b9e2d406a0a0d558ca9c115c6e238406a0a0d59c6a6c1156f5d4040 | xxd -r -p | protoc --decode_raw


# remove these 4d04273f

# 08f0011001180728858d1630015a30122e0dc95864be159920c83d180420c3ffffffffffffffff01282b35000080403d5057f43b456cf7f33b481d50046002

# gets position of Luba

#  echo 08f0011001180728858d1630015a30122e0dc95864be159920c83d180420c3ffffffffffffffff01282b35000080403d5057f43b456cf7f33b481d50046002 | xxd -r -p | protoc --proto_path=/home/michael/git/pymammotion/ --decode LubaMsg pymammotion/proto/luba_msg.proto


b'M\x04\x00\xdf\x08\xf8\x01\x10\x01\x18\x07 \x02(\x010\x018\x80\x80 B\xcb\x01b\xc8\x01\n\x12\x08\x01\x10\x06\x18\x01"\n1.10.5.237\n\x1e\x08\x01\x10\x03\x18\x01"\x161.6.22.2040 (3be066bf)\n\x1c\x08\x02\x10\x03\x18\x01"\x141.1.1.622 (a993d995)\n\x1b\x08\x03\x10\x03\x18\x01"\x132.2.0.150 (2cf62fc)\n\x1b\x08\x04\x10\x03\x18\x01"\x132.2.0.150 (2cf62fc)\n\x0c\x08\x05\x10\x03\x18\x01"\x047361\n\x1e\x08\x06\x10\x03\x18\x01"\x161.6.22.2040 (3be066bf)\n\x0c\x08\x07\x10\x03\x18\x01"\x041.28'

# order of calls

# get device version main
msgtype: MSG_CMD_TYPE_ESP
sender: DEV_MOBILEAPP
msgattr: MSG_ATTR_REQ
seqs: 1
version: 1
subtype: 1
net {
  todev_devinfo_req {
    req_ids {
      id: 1
      type: 6
    }
  }
}

# ???
msgtype: MSG_CMD_TYPE_EMBED_OTA
sender: DEV_MOBILEAPP
rcver: DEV_MAINCTL
msgattr: MSG_ATTR_REQ
seqs: 1
version: 1
subtype: 1
13 {
  1 {
    1: 1 # ota 0 baseInfo which has battery and devStatus woop woop
  }
}


msgtype: MSG_CMD_TYPE_EMBED_SYS
sender: DEV_MOBILEAPP
rcver: DEV_MAINCTL
msgattr: MSG_ATTR_REQ
seqs: 1
version: 1
subtype: 1
sys {
  todev_data_time {
    year: 2023
    month: 2
    date: 5
    week: 1
    hours: 9
    minutes: 14
    seconds: 40
    timezone: 720
    daylight: 60
  }
}


msgtype: MSG_CMD_TYPE_ESP
sender: DEV_MOBILEAPP
msgattr: MSG_ATTR_REQ
seqs: 1
version: 1
subtype: 1
net {
  todev_devinfo_req {
    req_ids {
      id: 1
      type: 6
    }
  }
}

msgtype: MSG_CMD_TYPE_ESP
sender: DEV_MOBILEAPP
msgattr: MSG_ATTR_REQ
seqs: 1
version: 1
subtype: 1
net {
  todev_ble_sync: 2
}

# read_plan
msgtype: MSG_CMD_TYPE_NAV
sender: DEV_MOBILEAPP
rcver: DEV_MAINCTL
msgattr: MSG_ATTR_REQ
seqs: 1
version: 1
subtype: 1
nav {
  todev_planjob_set {
    subCmd: 2
  }
}

# requestMapLocationData
msgtype: MSG_CMD_TYPE_EMBED_SYS
sender: DEV_MOBILEAPP
rcver: DEV_MAINCTL
msgattr: MSG_ATTR_REQ
seqs: 1
version: 1
subtype: 1
sys {
  todev_report_cfg {
    timeout: 10000
    period: 1000
    no_change_period: 2000
    sub: 0
    sub: 2
    sub: 3
    sub: 4
    sub: 1
    sub: 7
    sub: 8
    sub: 9
  }
}

# more update buf data

system_update_buf {
    update_buf_data: 2
    update_buf_data: 23
    update_buf_data: 390610
    update_buf_data: -1005
    update_buf_data: 1715406110
    update_buf_data: -2700
    update_buf_data: 1715406095
    update_buf_data: -323
    update_buf_data: 1715404514
    update_buf_data: -1303
    update_buf_data: 1715404045
    update_buf_data: -1300
    update_buf_data: 1715403959
    update_buf_data: -1005
    update_buf_data: 1715395357
    update_buf_data: -2700
    update_buf_data: 1715395343
    update_buf_data: -1303
    update_buf_data: 1714996794
    update_buf_data: -2801
    update_buf_data: 1714878351
    update_buf_data: -2800
    update_buf_data: 1714878350
  }

msgtype: MSG_CMD_TYPE_EMBED_SYS
sender: DEV_MOBILEAPP
rcver: DEV_MAINCTL
msgattr: MSG_ATTR_REQ
seqs: 1
version: 1
subtype: 1
sys {
  bidire_comm_cmd {
    rw: 1
    id: 5
    context: 3
  }
}


# synchronize_hash_data 3 or get_area_tobe_transferred

msgtype: MSG_CMD_TYPE_NAV
sender: DEV_MOBILEAPP
rcver: DEV_MAINCTL
msgattr: MSG_ATTR_REQ
seqs: 1
version: 1
subtype: 1
nav {
  todev_get_commondata {
    pver: 1
    subCmd: 1
    action: 8
    type: 3
  }
}




# get all the hash data
# getLineInfoList
msgtype: MSG_CMD_TYPE_NAV
sender: DEV_MOBILEAPP
rcver: DEV_MAINCTL
msgattr: MSG_ATTR_REQ
seqs: 1
version: 1
subtype: 1
nav {
  app_request_cover_paths_t {
    pver: 1
    transactionId: 1715508229679
    hashList: 49
    hashList: 13650
    hashList: 90
    hashList: 3800
    hashList: 487
    hashList: 31692476
    hashList: 7
    hashList: 1172515
    hashList: 31
    hashList: 1524214
    hashList: 6807
    hashList: 47
    hashList: 1106636
    hashList: 23
    hashList: 9
    hashList: 40
    hashList: 6026
    hashList: 49
    hashList: 3451
    hashList: 128014
    hashList: 22
    hashList: 126
    hashList: 34
    hashList: 215001602
    hashList: 9192
    hashList: 116
    hashList: 55
    hashList: 2529
    hashList: 13113
    hashList: 78
    hashList: 4139
  }
}


# all powerful rw

msgtype: MSG_CMD_TYPE_EMBED_SYS
sender: DEV_MOBILEAPP
rcver: DEV_MAINCTL
msgattr: MSG_ATTR_REQ
seqs: 1
version: 1
subtype: 1
sys {
  bidire_comm_cmd {
    rw: 1
    id: 5
    context: 3
  }
}

# ??
msgtype: MSG_CMD_TYPE_EMBED_SYS
sender: DEV_MAINCTL
rcver: DEV_MOBILEAPP
seqs: 8167
version: 1
sys {
  system_update_buf {
    update_buf_data: 3
    update_buf_data: 8
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
    update_buf_data: 0
  }
}

# just have to call ble sync and get all this data back :)
toapp_report_data = '\x08\xf4\x01\x10\x01\x18\x07(\xc170\x01R\xb8\x01\xba\x02\xb4\x01\n\x18\x08\x01\x10\xb8\xff\xff\xff\xff\xff\xff\xff\xff\x01\x18\xcf\xff\xff\xff\xff\xff\xff\xff\xff\x01\x12\x0e\x08\x0b\x10\x02\x18d(\x0e0\x95\xaf\xe5\xb1\x06\x1a\x13\x08\x04\x10\x02\x18 @\x80\x80\xb4\xf9\x91\x80\x80\x80\x03P\x980"-\x08\xa0\xab\xf7\xff\xff\xff\xff\xff\xff\x01\x10\xe4\xe0\xfc\xff\xff\xff\xff\xff\xff\x01\x18\xe7\xc8\xf8\xff\xff\xff\xff\xff\xff\x01 \x050\xe5\xa7\xe3\xd2\x93\xd2\xd5\x98**D\x10\xcf\xd6\xfa\xf5\xb5\xc1\xef\x9eC\x18\xd6\x80\xd8\x02 n0\xf0\xe0\x81\xc0\xa4\xe5\x81\xc5G8\x84\xa4\x07@\xfd\xf6\x07`\x99\xf0\x9b\xe0\xce\x88\xe2\x96Gp\xe2\xa5\xde\xf0\xe3\xbc\xaf\x8aQx\xfc\xb5\xf4\xf2\x8d\xa5\x80\xe7q\xa0\x01<'

# how to generate the python proto files
# protoc -I=. --python_out=./ ./pymammotion/proto/luba_msg.proto
# need output from datahash and figure out types for listing zones


