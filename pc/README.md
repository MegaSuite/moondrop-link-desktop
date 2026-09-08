# pc/ — Moondrop EDGE PC 客户端

基于逆向 `ref/moondrop.apk`（MOONDROP Link）得到的 Qualcomm GAIA-over-BLE 协议实现，
含命令行与图形界面。

## 状态（真机验证 · 2026-09-08，Windows + bleak，EDGE 固件 1.4.0）

- ✅ 扫描/连接、电量、固件版本、特性表、ANC 状态读取
- ✅ 降噪三态切换（关闭/降噪/通透，听感确认）
- ✅ 设备双连 multipoint 开关与“当前设备列表”（多设备分页已修）
- 🧪 断开列表中的单台设备（cmd7，需双机场景复核 deviceNum 语义）
- ⏳ 路线图：LDAC 解码器、场景预设、应用内音量

协议要点与字节级结论见 `out/notes/v3-codec.md` 与仓库 `docs/`。

## 启动 GUI（现代深色界面）

Windows 双击 `run_gui.bat`（自动建 venv、装依赖、打开独立窗口）。
Linux/手动：

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-gui.txt
.venv/bin/python -m moondrop_link.gui [--addr 41:42:E8:53:63:E4] [--native] [--port 8765]
```

- 启动自动扫描 → 下拉选 EDGE → “连接”。
- 状态卡 4s 轮询（电量/固件/ANC/双连/特性）。
- 降噪三键、双连开关、断开单台设备按钮均已可用。
- 底部通信日志可看原始帧；地址记住于 `~/.moondrop_link_gui.json`。

## 命令行模式

```bash
.venv/bin/python -m moondrop_link.cli scan --name EDGE --log DEBUG
.venv/bin/python -m moondrop_link.cli status --addr XX:XX:XX:XX:XX:XX
.venv/bin/python -m moondrop_link.cli ac --addr ... --state anc|transparent|off
.venv/bin/python -m moondrop_link.cli ac --addr ...                  # 只读当前 ANC
.venv/bin/python -m moondrop_link.cli multipoint --addr ... --get|--on|--off|--devices
.venv/bin/python -m moondrop_link.cli gatt --addr ...    # 诊断：列 GATT
.venv/bin/python -m moondrop_link.cli probe --addr ...   # 诊断：发候选帧看回包
```

## 模块

- `moondrop_link/gaia/constants.py` — UUID / vendor / feature / 枚举常量
- `moondrop_link/gaia/packet.py` — GAIA 帧编解码（大端，v3 命令字打包）
- `moondrop_link/gaia/transport.py` — bleak BLE 传输（连接/MTU/通知/写有应答）
- `moondrop_link/gaia/session.py` — 会话：版本探测、请求/响应路由、fire-and-forget
- `moondrop_link/gaia/features.py` — BASIC / BATTERY / AudioCuration / OneBringTwo
- `moondrop_link/app.py` — GUI 用设备管理封装（常驻会话）
- `moondrop_link/gui.py` — NiceGUI 界面；`moondrop_link/cli.py` — 命令行

## 真机实测记录（节选）

- GAIA v3 / vendor `0x001D` / 大端；**命令须 write-with-response**（1101 无 WWR）。
- EDGE 特性：BASIC/EARBUD/VOICE_UI/MUSIC_PROCESSING/UPGRADE/**AUDIO_CURATION**/
  DAC_GAIN/CODEC_TYPE/LIGHT_SENSOR/BATTERY/ONEBRINGTWO/BT_ADDRESS（无 ANC_V2）。
- ANC = audio-curation(0x08)：读模式返回索引 0..2；SET payload 位掩码
  `0x01`=关闭降噪 / `0x02`=降噪 / `0x04`=通透。
- OneBringTwo 每包回一台设备 `[num][addr6][name]`，无更多时重复末台 → 以“重复即停”分页。
