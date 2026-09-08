# 真机验证手册（无耳机/无蓝牙环境时给使用者执行）

本逆向在容器内完成，无真实 EDGE 耳机与蓝牙适配器。以下步骤由你在
**电脑（Windows 10/11 或 Linux + 蓝牙适配器）**与 **EDGE 耳机**上执行，
验证并校准本文档的协议字段。

## A. 第一步：确认 EDGE 走哪条 BLE 链路

1. Windows：用 nRF Connect（微软商店）或 python `pc` 里的扫描工具。
   或 Linux：`pc/.venv/bin/python -m moondrop_link.cli scan`（基于 bleak）。
2. 让 EDGE 进入配对模式，观察扫描结果：
   - 名称（应含 EDGE / MOONDROP）。
   - 广告是否含 Service UUID：
     - `00001100-d102-11e1-9b23-00025b00a5a5` → **GAIA over BLE**（本项目主线）
     - `9eca0000-7f3a-4f32-9a38-a91b2c6e0100` → 专有 BleSourceSwitch（改路线）
     - 其它 → 对照 `docs/summary.md` 另选
3. 连接后在 GATT 服务列表中确认 1100/1101/1102/1103 特征。

## B. 抓取手机 app 的真实协议样本（校准字节）

用一台安卓手机 + EDGE：
1. 开发者选项 → 开启 **Bluetooth HCI snoop log**。
2. 打开 MOONDROP app，连接 EDGE，执行：查电量、切换 ANC、开关双连。
3. 关闭日志，抓取 `btsnoop_hci.log`（各品牌路径不同：
   `/sdcard/MIUI/debug_log/bluetooth/`、`/sdcard/btsnoop_hci.log` 等）。
4. Wireshark 打开，过滤 EDGE 的 BD_ADDR 与 GATT write/notify：
   - 记录 1101 特征写入的每一帧 hex。
   - 记录 1102 通知回的每一帧 hex。
5. 与 `out/notes/v3-codec.md` 与 `pc/moondrop_link/gaia/features.py` 对照，
   修正任何不一致的字节/字节序。

> 也可用 nRF Connect 直接发命令对比（需自行拼命令）。

## C. 跑 PC 客户端并输出日志

```bash
cd pc
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m moondrop_link.cli scan                  # 找设备
.venv/bin/python -m moondrop_link.cli status --addr XX:XX  # 电量/版本/ANC
.venv/bin/python -m moondrop_link.cli anc --addr XX:XX --mode on
```

开启 debug 日志：`--log debug`。把日志与 B 步的 btsnoop 对照。

## D. 常见问题

- 写命令无响应：可能未正确启用 1102 通知/CCCD；或该设备需先配对（app 在连接时会
  读 1103 触发配对诱导）。
- 命令无反应但能收通知：feature id/编码错误，对照抓包修正。
- ANC 切换无效：确认用 ANC_V2(0x20) 还是 AUDIO_CURATION(0x08)；模式字节范围。
- 无 BLE：EDGE 可能走 SPP/CLASSIC GAIA → 需 Linux BlueZ RFCOMM（另行实现）。
