# MOONDROP App 逆向分析 — 架构总览（初稿，持续更新）

> 分析对象：`ref/moondrop.apk` — MOONDROP v2.24.2c-260728ai (versionCode 102033)
> 分析方式：apktool 解码 manifest/res；jadx 反编译 classes.dex(/2)（10k+ Java 文件）；
> Dart Flutter 侧为 AOT `libapp.so`（字符串/符号分析，可后续用 blutter 深度逆向）。

## 1. 应用本体

- package：`com.moondroplab.moondrop.moondrop_app`，Android 28+，Flutter 前端 + 大量原生(Kotlin/Java)协议栈。
- Application：`GaiaClientApplication` —— 名字来自 Qualcomm 参考应用（GAIA Client），内部嵌入
  `com.qualcomm.qti.gaiaclient`（Qualcomm GAIA 客户端 SDK 完整源码），通过 repository/liveData 承载
  BT 连接、扫描、设备信息、feature 发现、ANC 等能力。
- Dart 与原生以 MethodChannel `com.moondroplab.moondrop.MethodChannel` 通信，宿主 `FlutterNative`，
  内部把调用分发给一系列 `MethodHandler`。
- 原生侧同时内置多套"芯片协议栈"，供不同 Moondrop 产品选择：
  - Qualcomm GAIA 客户端（`com.qualcomm.qti.gaiaclient`）→ QCC 芯片产品（BLE GAIA / RFCOMM GAIA）
  - Airoha SDK（`com.airoha.sdk`，`defpackage.bb` 等）→ Airoha 芯片产品
  - Bluetrum（`defpackage.qy` bluetooth manager）+ `BleSourceSwitch*`/`ble/source` 协议 → 蓝牙源切换等
  - Conexant USB Type-C（`com.conexant.libcnxtservice`、`libCxAudioHidLib.so`、`UsbDeviceHandler`）→ USB 产品
  - Jieli FOTA（`libjl_ota_auth.so`，`JieliFotaHandler`）
- 产品页面在 Dart 侧也明显分"无线设备"(`pages/device`)与"USB 设备"(`pages/device_usb`，内含
  comture / jiu / spv / synopsys 产品 tab)。

## 2. 需要重点回答的问题（逆向主线）

1. **EDGE 走哪条链路**：GAIA-over-BLE？GAIA-over-SPP？其它厂商栈？路由逻辑在 Dart(`ChipType`)还是原生。
2. GAIA 传输细节：GATT service/characteristic UUID、读写/通知端点、RWCP、MTU。
3. 状态/电量上报：标准 BLE Battery Service(0x180F) vs GAIA 命令 vs Android 广播。
4. ANC：QTIL ANC_V2（audio curation, ACOrders/ACActions）还是老 ANCPlugin。
5. 双连（multipoint）：具体功能与命令。

## 3. 现状证据

- Manifest 内置 `GaiaClientApplication`；蓝牙权限全套（BLE scan/connect + 位置）。
- 原生 handlers 中 `AncV2Handler` 使用
  `gaiaclient.core.gaia.qtil.plugins.v3.V3AncV2Plugin`、`AudioCurationPlugin`、`QTILFeature.ANC_V2`、
  `ACOrders.ON_OFF_TP`、`ACActions.DISABLED` —— 说明 ANC 走 QCC QTIL GAIA。
- `BluetoothConnectionHandler` 走 `GaiaClientApplication.connectionRepository / discoveryRepository`
  连接/扫描；BLE 扫描结果用 GAIA 的 `FoundDevice`（BTLE）模型。
- GAIA 内核含 v1v2/v3 两套 packet：v3 command 16bit = feature(7bit)<<9 | type(2bit)<<7 | command(7bit)。

## 4. 输出

- 本目录：结论汇总
- `analysis/`：深入笔记
- `../pc/`：PC 端实现
