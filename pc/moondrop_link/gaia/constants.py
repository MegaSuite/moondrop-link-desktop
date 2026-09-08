# MOONDROP EDGE - GAIA-over-BLE constants (reverse-engineered from moondrop.apk)
#
# GATT/UUID data and GAIA packet layout derived from the embedded Qualcomm
# `com.qualcomm.qti.gaiaclient` stack. Frame payload details per feature are in
# `features.py`; full byte-level reference lives in the repo `out/notes/v3-codec.md`.
#
# Wire format: GAIA frames over BLE are transmitted raw (identity formatter, no
# SOF/checksum/sequence bytes): `[vendor:u16 BE][command:u16 BE][payload...]`.
# Multi-byte fields are BIG-ENDIAN (confirmed from the native `BytesUtils` in
# `libutils-lib.so`: a 16-bit field is built as `byte[0]<<8 | byte[1]`).

# ---- BLE GAIA GATT service (Qualcomm) -------------------------------------
# Built as prefix "00001100" + QUALCOMM base "-d102-11e1-9b23-00025b00a5a5"
GAIA_SERVICE_UUID = "00001100-d102-11e1-9b23-00025b00a5a5"
GAIA_CMD_UUID = "00001101-d102-11e1-9b23-00025b00a5a5"      # write commands (no response)
GAIA_RSP_UUID = "00001102-d102-11e1-9b23-00025b00a5a5"      # notifications: responses
GAIA_DATA_UUID = "00001103-d102-11e1-9b23-00025b00a5a5"     # RWCP data / pairing induce
CCCD_UUID = "00002902-0000-1000-8000-00805f9b34fb"

# legacy GAIA/SPP (classic transport, not used by this BLE client)
GAIA_LEGACY_SPP_UUID = "00001107-d102-11e1-9b23-00025b00a5a5"

# ---- GAIA vendor ids --------------------------------------------------------
VENDOR_CSR_V1V2 = 0x000A  # QTIL V1/V2 (version probe + legacy commands)
VENDOR_QTI_V3 = 0x001D    # QTIL V3 (the modern feature commands)

# ---- GAIA version probe -----------------------------------------------------
CMD_GET_API_VERSION = 0x0300  # V1/V2 packet on vendor 0x000A

# ---- BLE behaviour ----------------------------------------------------------
# Writes to the command characteristic are Write-Without-Response.
MTU_TARGET = 512

# ---- QTIL (Qualcomm Test Interface Layer) feature ids ----------------------
FEATURE_BASIC = 0x00
FEATURE_EARBUD = 0x01
FEATURE_ANC = 0x02
FEATURE_AUDIO_CURATION = 0x08
FEATURE_BATTERY = 0x0D
FEATURE_ONEBRINGTWO = 0x14
FEATURE_DYBASS = 0x1B
FEATURE_AUDIO_FILE_STORAGE = 0x1D
FEATURE_LR_CHANNEL = 0x1E
FEATURE_ANC_V2 = 0x20

# ---- GAIA v3 packet type (2 bits at position 7 of the 16-bit command word) --
T_COMMAND = 0
T_NOTIFICATION = 1
T_RESPONSE = 2
T_ERROR = 3

# V3 error status values (payload[0] of ERROR packets)
V3E_FEATURE_NOT_SUPPORTED = 0
V3E_COMMAND_NOT_SUPPORTED = 1
V3E_NOT_AUTHENTICATED = 2
V3E_INSUFFICIENT_RESOURCES = 3
V3E_AUTHENTICATING = 4
V3E_INVALID_PARAMETER = 5
V3E_INCORRECT_STATE = 6
V3E_IN_PROGRESS = 7

# ---- battery types ----------------------------------------------------------
BAT_SINGLE_DEVICE = 0
BAT_LEFT_DEVICE = 1
BAT_RIGHT_DEVICE = 2
BAT_CHARGER_CASE = 3
BAT_LEVEL_UNKNOWN = 255
BATTERY_NAMES = {
    BAT_SINGLE_DEVICE: "device",
    BAT_LEFT_DEVICE: "left",
    BAT_RIGHT_DEVICE: "right",
    BAT_CHARGER_CASE: "case",
}

# ---- ANC modes (Dart UI / AncV2Handler) -------------------------------------
ANC_MODE_OFF = 0
ANC_MODE_ANC_ON = 1
ANC_MODE_TRANSPARENT = 2
ANC_MODE_ANTI_WIND = 3
ANC_MODE_ADAPTIVE = 4
ANC_MODE_LIVE = 5
ANC_MODE_NAMES = {
    ANC_MODE_OFF: "off",
    ANC_MODE_ANC_ON: "anc",
    ANC_MODE_TRANSPARENT: "transparent",
    ANC_MODE_ANTI_WIND: "anti-wind",
    ANC_MODE_ADAPTIVE: "adaptive",
    ANC_MODE_LIVE: "live",
}

# audio-curation feature (0x08) mode states (EDGE): read-back index 0..2
AC_STATE_OFF = 0          # 关闭降噪
AC_STATE_ANC = 1          # 主动降噪
AC_STATE_TRANSPARENT = 2  # 通透
AC_STATE_NAMES = {
    AC_STATE_OFF: "off",
    AC_STATE_ANC: "anc",
    AC_STATE_TRANSPARENT: "transparent",
}
# EDGE's SET_MODE payload is a BIT MASK: 1 << state_index
AC_SET_PAYLOAD = {0: 1, 1: 2, 2: 4}

# ANC switch-conf 5-byte payload (setAncV2SwitchConf / setANCAction):
#   [STATE][ANC_ON][ANC_OFF][TRANSPARENT][ORDER]
#   byte0..3: ACActions DISABLED=0 / ENABLED=1
#   byte4:    ACOrders cycle order
AC_ACTION_DISABLED = 0
AC_ACTION_ENABLED = 1
AC_ORDER_ON_OFF_TP = 0  # ON_OFF_TP
AC_ORDER_OFF_ON_TP = 1  # OFF_ON_TP
AC_ORDER_TP_ON_OFF = 2  # TP_ON_OFF
AC_ORDER_ON_TP_OFF = 3  # ON_TP_OFF
AC_ORDER_OFF_TP_ON = 4  # OFF_TP_ON
AC_ORDER_TP_OFF_ON = 5  # TP_OFF_ON
AC_ORDER_NAMES = {
    AC_ORDER_ON_OFF_TP: "ON_OFF_TP",
    AC_ORDER_OFF_ON_TP: "OFF_ON_TP",
    AC_ORDER_TP_ON_OFF: "TP_ON_OFF",
    AC_ORDER_ON_TP_OFF: "ON_TP_OFF",
    AC_ORDER_OFF_TP_ON: "OFF_TP_ON",
    AC_ORDER_TP_OFF_ON: "TP_OFF_ON",
}
