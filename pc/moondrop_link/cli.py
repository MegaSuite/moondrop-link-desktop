"""CLI for Moondrop EDGE control (GAIA-over-BLE).

Usage:
  moondrop-link scan                           # discover BLE devices
  moondrop-link gatt    --addr XX:..           # list GATT services/characteristics
  moondrop-link probe   --addr XX:.. [--pair]  # send candidate GAIA frames, show replies
  moondrop-link status  --addr XX:..           # version/features/battery/AC/multipoint
  moondrop-link ac      --addr .. [--get | --set N | --sweep]   # audio-curation ANC
  moondrop-link multipoint --addr .. (--on | --off | --get | --devices)
  (anc/anc-conf are legacy aliases for ANC_V2 devices that expose feature 0x20)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .gaia import constants as C
from .gaia.features import (
    AncV2Feature,
    AudioCurationFeature,
    BasicFeature,
    BatteryFeature,
    OneBringTwoFeature,
)
from .gaia.session import GaiaError, GaiaSession
from .gaia.transport import GaiaTransport, scan

BANNER = ("NOTE: fields are reconstructed offline. If a write gets no reply, run "
          "`probe` (optionally --pair) and compare RX frames.")


def _log(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )


# ---------------------------------------------------------------------------
# scan / gatt / probe
# ---------------------------------------------------------------------------

async def cmd_scan(args) -> None:
    found = await scan(args.timeout, args.name)
    # dedupe, keep strongest rssi
    best: dict[str, tuple] = {}
    for dev, adv in found:
        key = dev.address
        if key not in best or (adv.rssi or 0) > (best[key][1] or -999):
            best[key] = (dev, adv)
    if not best:
        print("no devices found")
        return
    print(f"{'name':<24} {'address':<20} {'rssi':>5}  adv-services")
    for key, (dev, adv) in sorted(best.items()):
        name = adv.local_name or dev.name or "<unknown>"
        uuids = ",".join(u for u in (adv.service_uuids or []))
        print(f"{name:<24} {key:<20} {adv.rssi or 0:>5}  {uuids}")


async def _open_transport(args) -> GaiaTransport:
    t = GaiaTransport(args.addr)
    await t.connect()
    if getattr(args, "pair", False):
        print("pairing (watch for an OS consent dialog)...")
        await t.pair()
    return t


async def cmd_gatt(args) -> None:
    t = await _open_transport(args)
    try:
        print(f"--- GATT of {args.addr} ---")
        for svc in await t.list_services():
            print(f"service {svc['service']}")
            for ch in svc["chars"]:
                print(f"   char {ch['char']:<42} {','.join(ch['props'])}")
    finally:
        await t.disconnect()


async def cmd_probe(args) -> None:
    """Best-effort protocol discovery. Subscribes to *every* notifying
    characteristic, then sends a matrix of candidate GAIA frames over
    different endpoints/write modes and reads back the response/data
    characteristics. Prints every byte that comes back."""
    t = await _open_transport(args)
    got = []

    def on_frame(char_uuid: str, data: bytearray | bytes) -> None:
        got.append(bytes(data))
        print(f"NOTIFY {char_uuid}  {bytes(data).hex()}")

    # subscribe to every notify-capable characteristic we can find
    subscribed = []
    for svc in await t.list_services():
        for ch in svc["chars"]:
            if "notify" in ch["props"]:
                cu = ch["char"]
                try:
                    await t.subscribe(cu, lambda _h, d, cu=cu: on_frame(cu, d))
                    subscribed.append(cu)
                except Exception as e:  # noqa: BLE001
                    print(f"  subscribe {cu} failed: {e}")
    print("subscribed to notify:", ", ".join(subscribed) or "(none)")
    await asyncio.sleep(0.4)

    # snapshot readable chars
    reads = [C.GAIA_RSP_UUID, C.GAIA_DATA_UUID]
    for cu in reads:
        try:
            v = await t.read_char(cu)
            print(f"read {cu} -> {v.hex() if v else '(empty)'}")
        except Exception as e:  # noqa: BLE001
            print(f"read {cu} failed: {e}")

    # (frame label, hex, endpoint, with-response)
    candidates = []
    for label, hexstr in [
        ("v1v2 GetApiVersion    vendor 0x000A", "000a0300"),
        ("v3 basic app-version  vendor 0x001D", "001d0005"),
        ("v3 basic features", "001d0001"),
        ("v3 battery supported", "001d1a00"),
        ("v3 battery levels L/R/CASE", "001d1a01010203"),
        ("v3 ancv2 get mode", "001d4003"),
        ("v3 ancv2 set conf", "001d402a0001000101"),
        ("v3 audio-curation get mode", "001d1003"),
        ("v3 reg notif ANC_V2", "001d000720"),
        ("v3 reg notif battery", "001d00070d"),
        ("LE vendor/cmd app-version", "1d000500"),
        ("LE vendor/cmd ancv2 get mode", "1d00030040"),
    ]:
        frame = bytes.fromhex(hexstr)
        for ep, rsp in ((C.GAIA_CMD_UUID, False), (C.GAIA_CMD_UUID, True),
                        (C.GAIA_DATA_UUID, False)):
            tag = f"write {ep[4:8]} {'resp' if rsp else 'noresp'}"
            n0 = len(got)
            print(f"TX {tag}  {hexstr}   ({label})")
            try:
                if rsp:
                    await t.write_char(ep, frame, response=True)
                else:
                    await t.send_raw(ep, frame)
            except Exception as e:  # noqa: BLE001
                print(f"   write failed: {e}")
            await asyncio.sleep(args.wait)
            if len(got) > n0:
                print(f"   -> {len(got) - n0} frame(s)")
            else:
                print("   -> (no reply)")
            # read back GAIA response/data chars after each write
            for cu in reads:
                try:
                    v = await t.read_char(cu)
                    if v:
                        print(f"   read {cu[4:8]} now -> {v.hex()}")
                except Exception:
                    pass

    print(f"\ntotal notify frames received: {len(got)}")
    if not got:
        print("no GAIA replies at all. Likely causes:")
        print("  1) EDGE needs the exact byte protocol the phone app uses")
        print("     -> capture phone btsnoop (docs/verification.md step B)")
        print("  2) the GAIA frames need RWCP wrapping on the data char")
    await t.disconnect()


# ---------------------------------------------------------------------------
# connect + session commands
# ---------------------------------------------------------------------------

async def connect_session(args) -> GaiaSession:
    t = GaiaTransport(args.addr)
    s = GaiaSession(t, request_timeout=args.timeout)
    await s.open()
    print(f"connected {args.addr}")
    if getattr(args, "pair", False):
        print("pairing (watch for an OS consent dialog)...")
        await t.pair()
    if not getattr(args, "no_probe", False):
        info = await s.probe_version()
        if not info:
            print("WARNING: GAIA version probe got no reply. "
                  "Trying feature commands anyway (vendor 0x001D / v3).")
        elif (info.get("gaia_major") or 3) != 3:
            print(f"WARNING: device GAIA version={info.get('gaia_major')} "
                  f"(expected 3 for this client); report this.")
    return s


async def cmd_status(args) -> None:
    s = await connect_session(args)
    try:
        basic = BasicFeature(s)
        bat = BatteryFeature(s)
        mp = OneBringTwoFeature(s)
        try:
            ver = await basic.get_application_version()
            print(f"application version : {ver}")
        except GaiaError as e:
            print(f"app version: unavailable ({e})")

        print("supported features:")
        try:
            feats = await basic.get_supported_features()
            if not feats:
                print("  (empty)")
            for fid, fv in feats:
                print(f"  feature 0x{fid:02x} v{fv}")
        except GaiaError as e:
            print(f"  feature list unavailable ({e})")

        try:
            batt = await bat.read()
            for typ, lvl in sorted(batt.items()):
                name = C.BATTERY_NAMES.get(typ, f"battery-{typ}")
                print(f"battery {name:<10}: "
                      f"{'n/a' if lvl == C.BAT_LEVEL_UNKNOWN else str(lvl) + '%'}")
        except GaiaError as e:
            print(f"battery unavailable ({e})")

        # EDGE exposes audio-curation (feature 0x08), not ANC_V2(0x20).
        ac = AudioCurationFeature(s)
        try:
            acd = await ac.get_mode()
            if acd:
                idx = acd[0]
                name = C.AC_STATE_NAMES.get(idx, "?")
                print(f"ANC state: {name} (index {idx})")
            else:
                print("audio-curation: empty get-mode response")
        except GaiaError as e:
            print(f"audio-curation mode unavailable ({e})")
        try:
            conf = await ac.get_anc_switch_conf()
            print(f"audio-curation switch-conf bytes: {conf.hex() if conf else None}")
        except GaiaError:
            pass

        try:
            on = await mp.get_state()
            print(f"multipoint(dual link) enabled : {on}")
        except GaiaError as e:
            print(f"multipoint state unavailable ({e})")
        try:
            devs = await mp.get_current_devices()
            print(f"current linked devices ({len(devs)}):")
            for d in devs:
                print(f"  {d}")
        except GaiaError as e:
            print(f"current devices unavailable ({e})")
        print("\n" + BANNER)
    finally:
        await s.close()


async def cmd_anc(args) -> None:
    s = await connect_session(args)
    anc = AncV2Feature(s)
    try:
        if args.mode is not None:
            await anc.set_mode(args.mode)
            print(f"ANC mode set -> {C.ANC_MODE_NAMES[args.mode]}")
            m = await anc.get_mode()
            print(f"ANC mode now: {C.ANC_MODE_NAMES.get(m, m)}")
        else:
            m = await anc.get_mode()
            print(f"ANC mode: {C.ANC_MODE_NAMES.get(m, m)}")
            try:
                conf = await anc.get_switch_conf()
                print(f"ANC switch-conf bytes: {conf.hex() if conf else None}")
            except GaiaError:
                pass
        print(BANNER)
    finally:
        await s.close()


async def cmd_anc_conf(args) -> None:
    s = await connect_session(args)
    anc = AncV2Feature(s)
    try:
        cur = await anc.get_switch_conf()
        cur = list(cur) if cur else [1, 1, 1, 1, 0]
        cur[0] = args.state if args.state is not None else cur[0]
        cur[1] = args.anc_on if args.anc_on is not None else cur[1]
        cur[2] = args.anc_off if args.anc_off is not None else cur[2]
        cur[3] = args.tp if args.tp is not None else cur[3]
        cur[4] = args.order if args.order is not None else cur[4]
        await anc.set_switch_conf(bytes(cur))
        print(f"ANC switch-conf set: {bytes(cur).hex()}")
        print(BANNER)
    finally:
        await s.close()


async def cmd_multipoint(args) -> None:
    s = await connect_session(args)
    mp = OneBringTwoFeature(s)
    try:
        if args.on:
            await mp.set_state(True)
            await asyncio.sleep(0.6)
            print(f"multipoint -> enabled: {await mp.get_state()}")
        elif args.off:
            await mp.set_state(False)
            await asyncio.sleep(0.6)
            print(f"multipoint -> enabled: {await mp.get_state()}")
        elif args.devices:
            devs = await mp.get_current_devices()
            for d in devs:
                print(d)
        else:  # get
            print(f"multipoint enabled : {await mp.get_state()}")
            try:
                print("timeout:", await mp.get_timeout())
            except GaiaError:
                pass
        print(BANNER)
    finally:
        await s.close()


async def cmd_ac(args) -> None:
    """Audio-curation (feature 0x08) — EDGE's actual ANC control.

    The numeric mode value->state mapping is device-defined; until calibrated
    we expose raw numbers. Use --sweep to map modes by listening.
    """
    s = await connect_session(args)
    ac = AudioCurationFeature(s)

    def on_notif(payload: bytes, feat: int, cmd: int) -> None:
        print(f"  NOTIF feat=0x{feat:02x} cmd={cmd} payload={payload.hex()}")

    async def report_current() -> None:
        try:
            d = await ac.get_mode()
            idx = d[0] if d else None
            name = C.AC_STATE_NAMES.get(idx, "?")
            print(f"ANC state: {name}  (index {idx}, bytes {list(d) if d else None})")
        except GaiaError as e:
            print(f"read state failed: {e}")

    try:
        if args.state is not None:
            idx = args.state
            payload = C.AC_SET_PAYLOAD[idx]
            try:
                await ac.set_state(idx)
                print(f"set state {C.AC_STATE_NAMES[idx]} (payload 0x{payload:x})")
            except GaiaError as e:
                print(f"set no-ack ({e}) — may still have applied")
            await asyncio.sleep(1.2)
            await report_current()
        elif args.sweep:
            s.on_notification = on_notif
            try:
                await BasicFeature(s).register_notification(C.FEATURE_AUDIO_CURATION)
                print("registered audio-curation notifications")
            except GaiaError:
                print("(could not register notifications; continuing)")
            await asyncio.sleep(0.3)
            print("\nSWEEP: cycles the three EDGE ANC states (2 s each).")
            for idx in (0, 1, 2):
                name = C.AC_STATE_NAMES[idx]
                print(f"-- {name} (payload 0x{C.AC_SET_PAYLOAD[idx]:x}) --")
                try:
                    await ac.set_state(idx)
                except GaiaError as e:
                    print(f"   set no-ack ({e}) — may still have applied")
                await asyncio.sleep(2.0)
                await report_current()
            print("\nsweep done.")
        elif args.set is not None:
            try:
                await ac.set_mode(args.set)
                print(f"raw set-mode = {args.set} (payload 0x{args.set:x})")
            except GaiaError as e:
                print(f"set-mode {args.set}: no ack ({e}) — may still apply")
            await asyncio.sleep(1.0)
            await report_current()
        else:  # default: get everything
            await report_current()
            for label, fn in (("AC state raw (cmd0)", ac.get_ac_state),
                              ("modes count (cmd2)", ac.get_modes_count),
                              ("toggle-conf count (cmd7)", ac.get_toggle_conf_count),
                              ("switch-conf (cmd41)", ac.get_anc_switch_conf)):
                try:
                    v = await fn()
                    if isinstance(v, bytes):
                        print(f"{label}: {list(v)}")
                    else:
                        print(f"{label}: {v}")
                except GaiaError as e:
                    print(f"{label}: failed ({e})")
            for i in range(4):
                try:
                    tc = await ac.get_toggle_conf(i)
                    if tc:
                        print(f"toggle-conf[{i}] (cmd8): {list(tc)}")
                except GaiaError:
                    pass
        print(BANNER)
    finally:
        await s.close()


def _ac_state_arg(v: str) -> int:
    """name (off/anc/transparent) or index 0..2 -> AC state index."""
    if v.isdigit():
        idx = int(v)
        if idx in C.AC_STATE_NAMES:
            return idx
    table = {name: idx for idx, name in C.AC_STATE_NAMES.items()}
    if v in table:
        return table[v]
    raise argparse.ArgumentTypeError(
        f"unknown AC state {v!r} (use one of off|anc|transparent or 0..2)"
    )


def _mode_arg(v: str) -> int:
    table = {name: val for val, name in C.ANC_MODE_NAMES.items()}
    if v.isdigit():
        return int(v)
    if v in table:
        return table[v]
    raise argparse.ArgumentTypeError(
        f"unknown ANC mode {v!r} (use one of {', '.join(sorted(table))})"
    )


def _add_addr(sp, *, pair: bool = False, probe: bool = True):
    sp.add_argument("--addr", required=True)
    sp.add_argument("--timeout", type=float, default=5.0, help="BLE/request timeout s")
    sp.add_argument("--log", default="INFO")
    if pair:
        sp.add_argument("--pair", action="store_true", help="LE pair before talking")
    if not probe:
        sp.add_argument("--no-probe", action="store_true",
                        help="skip the GAIA version probe")


def main() -> None:
    p = argparse.ArgumentParser(prog="moondrop-link")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("scan")
    sp.add_argument("--timeout", type=float, default=5.0)
    sp.add_argument("--name", default=None, help="filter by name substring")
    sp.add_argument("--log", default="INFO")
    sp.set_defaults(func=cmd_scan)

    sp = sub.add_parser("gatt")
    _add_addr(sp, pair=True, probe=False)
    sp.set_defaults(func=cmd_gatt)

    sp = sub.add_parser("probe")
    _add_addr(sp, pair=True, probe=False)
    sp.add_argument("--wait", type=float, default=1.5,
                    help="seconds to wait after each candidate write")
    sp.set_defaults(func=cmd_probe)

    # 'ac' (audio-curation, EDGE) + 'status'/'multipoint'
    for name, pair, probe in (("status", True, True),
                              ("multipoint", True, True)):
        sp = sub.add_parser(name)
        _add_addr(sp, pair=pair, probe=probe)
        if name == "multipoint":
            g = sp.add_mutually_exclusive_group()
            g.add_argument("--on", action="store_true")
            g.add_argument("--off", action="store_true")
            g.add_argument("--devices", action="store_true")
        sp.set_defaults(func=globals()["cmd_" + name.replace("-", "_")])

    sp = sub.add_parser("ac", help="audio-curation (feature 0x08; EDGE's ANC)")
    _add_addr(sp, pair=True, probe=True)
    sp.set_defaults(timeout=2.0)  # quick no-ack detection on set commands
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--state", type=_ac_state_arg, default=None, metavar="S",
                   help="off|anc|transparent  (or index 0..2) to set")
    g.add_argument("--set", type=int, default=None, metavar="N",
                   help="expert: raw SET_MODE payload byte")
    g.add_argument("--sweep", action="store_true",
                   help="cycle off/anc/transparent so you can verify by ear")
    sp.set_defaults(func=cmd_ac)

    # legacy aliases for other products (ANC_V2 based); kept for reference
    for name, pair, probe in (("anc", True, True),
                              ("anc-conf", True, True)):
        sp = sub.add_parser(name)
        _add_addr(sp, pair=pair, probe=probe)
        if name == "anc":
            sp.add_argument("--mode", type=_mode_arg, default=None,
                            help="off|anc|transparent|anti-wind|adaptive|live "
                                 "(ANC_V2 only; EDGE lacks this feature)")
        if name == "anc-conf":
            for opt in ("state", "anc-on", "anc-off", "tp"):
                sp.add_argument(f"--{opt}", type=int, choices=(0, 1), default=None)
            sp.add_argument("--order", type=int, choices=range(6), default=None)
        sp.set_defaults(func=globals()["cmd_" + name.replace("-", "_")])

    args = p.parse_args()
    _log(args.log)
    try:
        asyncio.run(args.func(args))
    except GaiaError as e:
        print(f"GAIA error: {e}", file=sys.stderr)
        print(BANNER, file=sys.stderr)
        sys.exit(1)
    except asyncio.CancelledError:
        print("cancelled", file=sys.stderr)
        sys.exit(130)
    except TimeoutError:
        print("timeout waiting for the device", file=sys.stderr)
        print(BANNER, file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
