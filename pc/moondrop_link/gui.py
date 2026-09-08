"""Modern desktop GUI for the Moondrop EDGE (NiceGUI backend).

Run:
    python -m moondrop_link.gui [--addr 41:42:E8:53:63:E4] [--native] [--port 8765]

--native opens a desktop window via pywebview (pip install pywebview) instead
of the default browser tab. State is persisted in ~/.moondrop_link_gui.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Optional

from nicegui import ui

from .app import EdgeClient, EdgeError, find_devices
from .gaia import constants as C

CONFIG_FILE = os.path.join(os.path.expanduser("~"), ".moondrop_link_gui.json")
STATE_OPTIONS = {"off": "关闭（无降噪）", "anc": "降噪", "transparent": "通透"}
FEAT_NAMES = {
    0x00: "BASIC", 0x01: "EARBUD", 0x03: "VOICE_UI", 0x05: "MUSIC",
    0x06: "UPGRADE", 0x08: "AUDIO_CURATION", 0x0D: "BATTERY",
    0x0F: "DAC_GAIN", 0x10: "CODEC", 0x11: "LIGHT_SENSOR",
    0x14: "ONEBRINGTWO", 0x15: "BT_ADDR",
}

client: Optional[EdgeClient] = None
config: dict = {}

# page widgets (assigned in build()) ---------------------------------------
addr_select: ui.select
addr_input: ui.input
state_dot: ui.html
state_label: ui.label
ver_label: ui.label
batt_label: ui.label
anc_label: ui.label
mp_label: ui.label
feats_label: ui.label
devices_col: ui.column
logs_text: ui.textarea
scan_btn: ui.button


def _log(msg: str) -> None:
    logs_text.value = logs_text.value + msg + "\n"


async def _err(e: Exception) -> None:
    ui.notify(str(e), type="negative", close_button=True)
    _log(f"ERROR: {e}")


# ---- actions ---------------------------------------------------------------

async def do_connect(*_args) -> None:
    global client
    address = (addr_input.value or "").strip()
    if not address:
        address = addr_select.value
    if not address:
        ui.notify("请扫描选择，或直接在地址栏输入 EDGE 的 MAC", type="warning")
        return
    try:
        if client:
            await client.close()
        client = EdgeClient(str(address))
        await client.connect()
    except Exception as e:  # noqa: BLE001
        await _err(e)
        return
    config["address"] = address
    save_config()
    addr_input.value = address
    state_dot.style("background:#22c55e")
    state_label.text = f"已连接 · {address}"
    _log(f"connected: {address}")
    await refresh()


async def do_disconnect(*_args) -> None:
    global client
    if client:
        await client.close()
    client = None
    state_dot.style("background:#ef4444")
    state_label.text = "未连接"
    for w in (ver_label, batt_label, anc_label, mp_label, feats_label):
        w.text = "—"
    devices_col.clear()
    _log("disconnected")


async def refresh() -> None:
    if not client or not client.connected:
        return
    try:
        st = await client.read_status()
    except EdgeError as e:
        await _err(e)
        return
    ver_label.text = st["version"] or "—"
    batt_label.text = fmt_battery(st["battery"])
    anc_label.text = STATE_OPTIONS.get(st["anc_name"] or "", "—")
    mp_label.text = "开" if st["multipoint"] else "关"
    feats_label.text = ", ".join(
        f"{FEAT_NAMES.get(f, f'0x{f:02x}')} v{fv}" for f, fv in (st["features"] or [])
    ) or "—"
    devices_col.clear()
    for d in st["devices"] or []:
        with devices_col:
            with ui.row().classes("items-center gap-2"):
                ui.icon("bluetooth").props("size=18px")
                ui.label(f"{d['name']}").classes("text-sm")
                ui.label(d["address"]).classes("text-xs text-gray-500")
                ui.button(icon="link_off",
                          on_click=lambda d=d: disconnect_one(d)) \
                    .props("flat round dense color=red size=sm") \
                    .tooltip(f"断开 {d['name']}")
    if not st["devices"]:
        with devices_col:
            ui.label("（无当前连接设备）").classes("text-gray-500 text-sm")


def fmt_battery(batt) -> str:
    if not batt:
        return "—"
    parts = []
    for typ in sorted(batt):
        lvl = batt[typ]
        name = C.BATTERY_NAMES.get(typ, f"type{typ}")
        val = "n/a" if lvl == C.BAT_LEVEL_UNKNOWN else f"{lvl}%"
        parts.append(f"{name}: {val}")
    return "  ".join(parts)


async def set_anc(name: str) -> None:
    if not client or not client.connected:
        ui.notify("未连接", type="warning")
        return
    try:
        res = await client.set_anc(name)
        ui.notify(f"降噪 → {STATE_OPTIONS.get(res['now'] or '', res['now'])}",
                  type="positive")
        await refresh()
    except Exception as e:  # noqa: BLE001
        await _err(e)


async def set_multipoint(enabled: bool) -> None:
    if not client or not client.connected:
        ui.notify("未连接", type="warning")
        return
    try:
        res = await client.set_multipoint(enabled)
        ui.notify("设备双连已" + ("开启" if res["now"] else "关闭"), type="positive")
        await refresh()
    except Exception as e:  # noqa: BLE001
        await _err(e)


async def disconnect_one(entry: dict) -> None:
    if not client or not client.connected:
        return
    try:
        await client.disconnect_linked(entry.get("num", 0), entry["address"],
                                       entry["name"])
        ui.notify(f"已请求断开 {entry['name']}", type="positive")
        await asyncio.sleep(1.2)
        await refresh()
    except Exception as e:  # noqa: BLE001
        await _err(e)


async def rescan(*_args) -> None:
    scan_btn.disable(); scan_btn.text = "扫描中…"
    try:
        devs = await find_devices(name_substr="", timeout=4)
        # include unnamed devices: the headset often stops advertising its name
        # once it is streaming audio, so fall back to the address as label
        opts = {d["address"]: f"{d['name']}  ·  {d['address']}"
                for d in devs}
        addr_select.options = opts
        saved = config.get("address")
        if saved in opts:
            addr_select.value = saved
        elif addr_select.value not in opts:
            addr_select.value = None
        addr_select.update()   # nicegui 3.x: must push options to the frontend
        ui.notify(f"扫到 {len(devs)} 台（下拉列出 {len(opts)} 台）", type="info")
    except Exception as e:  # noqa: BLE001
        await _err(e)
    finally:
        scan_btn.enable(); scan_btn.text = "重新扫描"


def load_config() -> dict:
    try:
        with open(CONFIG_FILE, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:  # noqa: BLE001
        return {}


def save_config() -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as fh:
            json.dump(config, fh)
    except Exception:  # noqa: BLE001
        pass


# ---- page ------------------------------------------------------------------

def build() -> None:
    global addr_select, addr_input, state_dot, state_label, ver_label, \
        batt_label, anc_label, mp_label, feats_label, devices_col, \
        logs_text, scan_btn

    ui.colors(primary="#6db3ff", secondary="#48b0a1", accent="#a78bfa")
    ui.dark_mode().enable()

    with ui.header().classes("items-center justify-between"):
        with ui.row().classes("items-center gap-3"):
            ui.icon("headphones").props("size=28px")
            ui.label("MOONDROP EDGE · PC").classes("text-xl font-bold")
        with ui.row().classes("items-center gap-2"):
            ui.label("连接状态:").classes("text-sm")
            state_dot = ui.html(
                '<div style="width:12px;height:12px;border-radius:50%;'
                'background:#ef4444;display:inline-block"></div>')
            state_label = ui.label("未连接").classes("text-sm")

    with ui.column().classes("w-full max-w-4xl mx-auto p-4 gap-4"):
        # connection
        with ui.card().classes("w-full"):
            with ui.row().classes("items-center gap-3").classes("w-full"):
                scan_btn = ui.button("重新扫描", icon="radar")
                # NB: do NOT pass value here - options are empty until a scan;
                # nicegui raises on a value not present in options.
                addr_select = ui.select({}, label="设备（扫描后选择）") \
                    .props("outlined style='min-width:24em'")
                ui.button("连接", icon="link", on_click=do_connect) \
                    .props("color=primary")
                ui.button("断开", icon="link_off", on_click=do_disconnect) \
                    .props("flat")
            with ui.row().classes("items-center gap-3").classes("w-full mt-1"):
                addr_input = ui.input("地址直连（可选）",
                                      value=config.get("address") or "",
                                      placeholder="AA:BB:CC:DD:EE:FF") \
                    .props("outlined dense style='min-width:24em'")
                ui.label("若扫描不到（耳机在放歌时常不发广播名），直接填地址连") \
                    .classes("text-xs text-gray-500")

            def _on_pick(*_args) -> None:
                if addr_select.value:
                    addr_input.value = addr_select.value

            addr_select.on_value_change(_on_pick)

        row = ui.row().classes("gap-4 items-stretch")
        with row:
            # overview
            with ui.card().classes("flex-1 min-w-[16rem]"):
                ui.label("状态总览").classes("text-base font-bold")
                with ui.column().classes("gap-1 mt-2 text-sm"):
                    ui.label("固件版本:")
                    ver_label = ui.label("—").classes("font-bold")
                    ui.label("电量:")
                    batt_label = ui.label("—").classes("font-bold")
                    ui.label("降噪模式:")
                    anc_label = ui.label("—").classes("font-bold")
                    ui.label("设备双连:")
                    mp_label = ui.label("—").classes("font-bold")
                    ui.label("支持的特性:")
                    feats_label = ui.label("—").classes("text-xs")
            # controls
            with ui.card().classes("flex-1 min-w-[18rem]"):
                ui.label("降噪模式").classes("text-base font-bold")
                with ui.row().classes("mt-2"):
                    for name in STATE_OPTIONS:
                        ui.button(STATE_OPTIONS[name],
                                  on_click=lambda n=name: set_anc(n)) \
                            .props("color=primary flat")
                ui.separator().classes("my-3")
                ui.label("设备双连（multipoint）").classes("text-base font-bold")
                with ui.row().classes("mt-2"):
                    ui.button("开启双连", on_click=lambda: set_multipoint(True)) \
                        .props("flat")
                    ui.button("关闭双连", on_click=lambda: set_multipoint(False)) \
                        .props("flat")
                ui.label("当前连接的设备：").classes("text-sm mt-3 font-bold")
                devices_col = ui.column().classes("gap-1 w-full")
        with row:
            # roadmap
            with ui.card().classes("w-64"):
                ui.label("路线图（后续实现）").classes("text-sm text-gray-400")
                with ui.column().classes("gap-1 mt-2"):
                    for icon, text, tip in (
                            ("swap_horiz", "切换解码器 LDAC", "规划中"),
                            ("tune", "切换场景预设", "规划中"),
                            ("volume_up", "应用内音量调节", "规划中")):
                        ui.button(text, icon=icon).props("flat disabled") \
                            .tooltip(tip)

        # log
        with ui.card().classes("w-full"):
            ui.label("通信日志").classes("text-base font-bold")
            logs_text = ui.textarea(value="") \
                .props("readonly outlined") \
                .classes("w-full h-44 font-mono text-xs")

    ui.timer(4.0, refresh)
    ui.timer(0.8, rescan, once=True)  # pre-populate the device picker


@ui.page("/")
def index_page() -> None:
    build()


def main() -> None:
    global config
    ap = argparse.ArgumentParser(description="MOONDROP EDGE PC 控制器")
    ap.add_argument("--addr", default=None, help="EDGE 蓝牙地址 (AA:BB:…)")
    ap.add_argument("--native", action="store_true",
                    help="独立窗口模式（需 pip install pywebview）")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    config = load_config()
    if args.addr:
        config["address"] = args.addr

    ui.run(title="MOONDROP EDGE · PC",
           host=args.host, port=args.port,
           native=args.native, window_size=(980, 900),
           show=True, reload=False)


if __name__ in {"__main__", "__mp_main__"}:
    main()
