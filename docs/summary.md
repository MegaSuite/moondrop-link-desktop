# EDGE → PC 适配：逆向结论汇总

> 证据来源见 `../out/notes/*.md`（专项笔记）与 `../docs/architecture.md`。
> 本文件是给实现者看的**协议目录**；字节级编解码详情在 `../out/notes/v3-codec.md`。

## 结论速览

| 项 | 结论 | 状态 |
|----|------|------|
| 传输 | GAIA over BLE（GATT）；命令必须 write-with-response | ✅ 真机验证 |
| 芯片 | Qualcomm QCC，GAIA v3 / vendor 0x001D（探测 vendor 0x000A cmd 0x0300） | ✅ |
| GATT | Service `00001100-d102-…`；Command `...1101`(写) / Response `...1102`(通知) / Data `...1103` | ✅ |
| 电量 | GAIA BATTERY(0x0D)：GetSupported=0 / GetLevels=1（单设备 type0） | ✅（60% 实测） |
| ANC | **audio-curation(0x08)**：读模式=索引 0..2；SET payload=位掩码 0x01关/0x02降噪/0x04通透 | ✅ 听感验证 |
| 设备双连 | GAIA ONEBRINGTWO(0x14)：状态读取/current devices | 读取 ✅；写入待双机 |
| OTA/升级 | 设备带 UPGRADE(0x06)；**本项目不做** | — |

## GATT/UUID（BLE GAIA）

- Service：`00001100-d102-11e1-9b23-00025b00a5a5`
- Command（写，无应答）：`00001101-d102-11e1-9b23-00025b00a5a5`
- Response（通知，强制）：`00001102-d102-11e1-9b23-00025b00a5a5`
- Data（通知/写，RWCP、配对诱导读）：`00001103-d102-11e1-9b23-00025b00a5a5`
- CCCD：`00002902-...`，对 1102 与 1103 写 `0x0001`

## 帧格式

BLE GAIA 帧 = 无 SOF/CRC 裸数据：
`[vendor:16 BE][command:16 BE][payload…]`，多字节字段大端
（由 app 原生 `BytesUtils`（libutils-lib.so）反汇编证实）。

- 版本探测 GetApiVersion 走 **V1/V2 包，vendor=0x000A，cmd=0x0300** → TX `00 0A 03 00`。
- 之后若设备 GAIA 版本为 3，功能命令走 **V3 包，vendor=0x001D**（注意不是 0x000A）。
- v3 command word = `feature(7b)<<9 | type(2b)<<7 | cmd(7b)`。
  type：0=COMMAND 1=NOTIFICATION 2=RESPONSE 3=ERROR。
- 帧匹配无序列号：按 (vendor, feature, command) 对请求/响应；ERROR 帧 payload[0]=错误码。

## 命令目录（先 probe 版本/取 features 再操作；完整字节表见 `out/notes/v3-codec.md`）

| 操作 | TX（示例） |
|------|-----------|
| 版本探测 | `00 0A 03 00` |
| 应用版本 BASIC(0) cmd5 | `00 1D 00 05` → RX payload=版本串(UTF-8) |
| 注册通知 BASIC cmd7+feature | ANC_V2：`00 1D 00 07 20` |
| 电量支持 BATTERY(0D) cmd0 | `00 1D 1A 00` |
| 电量值 cmd1 + 类型字节 | `00 1D 1A 01 01 02 03` → RX `[type][level]` 对 |
| ANC_V2(20) 读模式 cmd3 | `00 1D 40 03` → mode=payload[0] |
| ANC_V2 设模式 cmd4 | `00 1D 40 04 <mode>` mode:0 off/1 anc/2 通透/3 抗风/4 自适应/5 live |
| ANC_V2 读开关配置 cmd41 | `00 1D 40 29` → 5B |
| ANC_V2 写开关配置 cmd42 | `00 1D 40 2A` + [STATE][ANC_ON][ANC_OFF][TP][ORDER] |
| OneBringTwo(14) 读/写状态 | `00 1D 28 01` / `00 1D 28 02 01` |
| OneBringTwo 当前设备 | `00 1D 28 05`(+`06` 翻页)、断开 `00 1D 28 07`+dev |

## 剩余不确定性（真机验证项）

1. EDGE 广播是否携带 GAIA service/名称，transportType = LOW_ENERGY？
2. EDGE 固件 GAIA 版本 = v3？（决定 v3 vs v1v2 编码）
3. ANC 走 ANC_V2 还是 AUDIO_CURATION feature？
4. OneBringTwo/双连 的具体命令码（待 v3-codec.md 补齐）
5. 厂商(0x000A)外的自定义 vendor（EDGE 若定制则不同）

## 验证流程（真机）

见 `verification.md`。
