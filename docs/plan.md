# 逆向/开发路线图

## 里程碑

- [x] M0 摸底：APK 解包、manifest、整体架构识别（Flutter + GAIA + 多芯片栈）
- [x] M1 确认 EDGE 的连接链路（GAIA-over-BLE 候选）
- [x] M2 输出 GAIA 传输细节（GATT UUID、端点、帧格式）
- [x] M3(ANC/电量/版本/双连状态) 输出 EDGE 状态/电量/ANC/双连 对应的命令
- [x] M4 (PC 原型：scan/status/ac/multipoint) PC 端原型：扫描/连接/读状态/切 ANC（Python + bleak 首选）
- [~] M5 部分完成：ANC/电量/版本真机验证；双连写入待双机测试 真机验证闭环（需要真实 EDGE + 带 BLE 的电脑）

## 验证手段（无硬件环境时）

1. 静态：本文档逆向（GATT UUID、字节码、命令值）。
2. 准备 Python `pc/` 原型 + 命令行工具，输出"扫描日志"供真机调试。
3. Android 真机抓包建议（写入手册）：
   - 打开开发者选项里的蓝牙 HCI snoop log；跑 MOONDROP app 操作后拉取
     `/sdcard/MIUI/debug_log/…`（或 `btsnoop_hci.log`），用 Wireshark 过滤 EDGE 的 BD_ADDR
     与 GATT/GAIA 命令，与本文档字段对照。
   - 或使用 nRF Connect 连接 EDGE 查看 GATT 服务列表（验证 UUID）。

## 风险

- EDGE 若走 GAIA-over-BLE：PC 实现 = BLE GATT 客户端，较易（bleak 可在 Windows/Linux）。
- 若走 RFCOMM SPP：Windows 支持差，建议 Linux/BlueZ 实现。
- 若为厂商私有 BLE（如 BleSourceSwitch / Airoha）：需改实现该套协议，复杂度上升。
- 无线状态/ANC 可能有 GAIA v1v2/v3 两套编码，需按设备能力协商。

## 当前阶段：GUI 已完成（初步开发收官）

- NiceGUI 深色界面：连接/状态轮询/降噪三键/双连开关/断开单台/通信日志（`pc/moondrop_link/gui.py`、`pc/run_gui.bat`）。
- 真机可用功能：状态读取 + 降噪切换 + 双连读取（真机验证）。

## 后续计划（用户确认，按序）

1. 可选择性地切断双设备连接中的某一台（断开命令已有雏形，需双机场景复核 deviceNum/命令语义）。
2. 切换解码器（LDAC 等，EDGE 有 CODEC feature 0x10，待实现 V3CodecPlugin 编解码）。
3. 切换场景预设（EQ/音乐处理 feature 0x05，待实现 music-processing preset）。
4. 应用内音量调节（待定位 GAIA/系统音量通道；可能走 A2DP absolute volume）。

## 不做

- 固件升级（OTA，EDGE 带 UPGRADE feature 0x06，但风险高，明确排除）。
