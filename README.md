# moondrop-link-desktop

对水月雨 (Moondrop) **EDGE 头戴式蓝牙耳机**的 PC 端控制适配（逆向 `ref/moondrop.apk`，即 MOONDROP Link）。

> ✅ 2026-09-08：已在 **Windows + bleak** 真机验证 EDGE（BLE GAIA v3）。见下。
> 协议为逆向/实测所得，命令与字节均已对照设备行为校准。

## 范围与状态

| 功能 | 状态 |
|------|------|
| 桌面 GUI（NiceGUI 深色界面） | ✅ 已提供，待真机体验 |
| 扫描/连接 | ✅ 真机验证 |
| 电量 / 固件版本 / 特性 / ANC 状态 | ✅ 真机验证 |
| 降噪切换（关闭/主动降噪/通透） | ✅ 真机验证（听感确认） |
| 设备双连（multipoint）开关 / 当前设备列表 | ✅ 读取+开关验证；断开单台待双机实测 |
| 路线图：断开指定设备 / LDAC / 场景预设 / 音量 | ⏳ 后续 |
| 固件升级 OTA | ❌ 明确不做（有损坏风险） |

## 核心结论

- EDGE 是 Qualcomm QCC 芯片，走 **GAIA over BLE (GATT)**：
  Service `00001100-d102-11e1-9b23-00025b00a5a5`；
  Command `...1101`（**必须 write-with-response**）、Response `...1102`、Data `...1103`。
- 帧 = `[vendor:16][command:16][payload]` 大端裸帧；GAIA **v3**，vendor=`0x001D`；
  版本探测 v1v2 vendor=`0x000A` cmd=`0x0300`。
- ANC 走 **audio-curation(0x08)**（无 ANC_V2）；`SET_MODE` payload=位掩码：
  `0x01`=关闭降噪、`0x02`=ANC、`0x04`=通透（读回索引 0/1/2）。
- 电量走 BATTERY(0x0D)；双连走 ONEBRINGTWO(0x14)。

## 快速开始（Windows/Linux + BLE 适配器）

GUI（现代深色，Windows 双击 `pc/run_gui.bat`，Linux `pc/run_gui.sh`）：

```bash
cd pc && python -m pip install -r requirements-gui.txt
.venv/bin/python -m moondrop_link.gui --addr 41:42:E8:53:63:E4 [--native]
```

命令行（需 BLE 适配器）：

```bash
.venv/bin/python -m moondrop_link.cli status --addr 41:42:E8:53:63:E4
.venv/bin/python -m moondrop_link.cli ac --addr ... --state anc|transparent|off
.venv/bin/python -m moondrop_link.cli multipoint --addr ... --get|--on|--off|--devices
```

## 目录

```
ref/moondrop.apk     原始 APK（v2.24.2c-260728ai）
out/                 分析产物（不入库）：apktool/ jadx/ notes/*.md
docs/                汇总文档：architecture, summary, plan, verification
pc/                  PC 客户端（Python + bleak，moondrop_link 包）
tools/               分析工具（jadx/apktool）
```

详见 `docs/` 与 `pc/README.md`。
