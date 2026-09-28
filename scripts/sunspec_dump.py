#!/usr/bin/env python3
"""
Full register-by-register dump of an APsystems ECU's SunSpec map.

Usage:  python3 sunspec_dump.py 192.168.1.131 1 > ecu_map.md

Reads every register of models 1, 103, 113 and 123, decodes each field
according to the SunSpec specification, and flags the ones the firmware
does not implement. Also probes the proprietary DC block that sits after
the end-of-chain marker.

Output is a markdown table, ready to paste into a GitHub issue or a forum
post. Run it in daylight so the measured values are meaningful.

Requires: pip install pymodbus
"""

import math
import struct
import sys

from pymodbus.client import ModbusTcpClient

# (offset_from_model_data_start, name, type) for each model.
# Types: u16 s16 sf enum bf32 acc32 f32 str<N>
MODEL_1 = [
    (0, "Mn", "str16"), (16, "Md", "str16"), (32, "Opt", "str8"),
    (40, "Vr", "str8"), (48, "SN", "str16"), (64, "DA", "u16"),
    (65, "Pad", "u16"),
]

MODEL_103 = [
    (0, "A", "u16"), (1, "AphA", "u16"), (2, "AphB", "u16"), (3, "AphC", "u16"),
    (4, "A_SF", "sf"),
    (5, "PPVphAB", "u16"), (6, "PPVphBC", "u16"), (7, "PPVphCA", "u16"),
    (8, "PhVphA", "u16"), (9, "PhVphB", "u16"), (10, "PhVphC", "u16"),
    (11, "V_SF", "sf"),
    (12, "W", "s16"), (13, "W_SF", "sf"),
    (14, "Hz", "u16"), (15, "Hz_SF", "sf"),
    (16, "VA", "s16"), (17, "VA_SF", "sf"),
    (18, "VAr", "s16"), (19, "VAr_SF", "sf"),
    (20, "PF", "s16"), (21, "PF_SF", "sf"),
    (22, "WH", "acc32"), (24, "WH_SF", "sf"),
    (25, "DCA", "u16"), (26, "DCA_SF", "sf"),
    (27, "DCV", "u16"), (28, "DCV_SF", "sf"),
    (29, "DCW", "s16"), (30, "DCW_SF", "sf"),
    (31, "TmpCab", "s16"), (32, "TmpSnk", "s16"), (33, "TmpTrns", "s16"),
    (34, "TmpOt", "s16"), (35, "Tmp_SF", "sf"),
    (36, "St", "enum"), (37, "StVnd", "enum"),
    (38, "Evt1", "bf32"), (40, "Evt2", "bf32"),
    (42, "EvtVnd1", "bf32"), (44, "EvtVnd2", "bf32"),
    (46, "EvtVnd3", "bf32"), (48, "EvtVnd4", "bf32"),
]

MODEL_113 = [
    (0, "A", "f32"), (2, "AphA", "f32"), (4, "AphB", "f32"), (6, "AphC", "f32"),
    (8, "PPVphAB", "f32"), (10, "PPVphBC", "f32"), (12, "PPVphCA", "f32"),
    (14, "PhVphA", "f32"), (16, "PhVphB", "f32"), (18, "PhVphC", "f32"),
    (20, "W", "f32"), (22, "Hz", "f32"), (24, "VA", "f32"), (26, "VAr", "f32"),
    (28, "PF", "f32"), (30, "WH", "f32"),
    (32, "DCA", "f32"), (34, "DCV", "f32"), (36, "DCW", "f32"),
    (38, "TmpCab", "f32"), (40, "TmpSnk", "f32"), (42, "TmpTrns", "f32"),
    (44, "TmpOt", "f32"),
    (46, "St", "enum"), (47, "StVnd", "enum"),
    (48, "Evt1", "bf32"), (50, "Evt2", "bf32"),
    (52, "EvtVnd1", "bf32"), (54, "EvtVnd2", "bf32"),
    (56, "EvtVnd3", "bf32"), (58, "EvtVnd4", "bf32"),
]

MODEL_123 = [
    (0, "Conn_WinTms", "u16"), (1, "Conn_RvrtTms", "u16"), (2, "Conn", "enum"),
    (3, "WMaxLimPct", "u16"), (4, "WMaxLimPct_WinTms", "u16"),
    (5, "WMaxLimPct_RvrtTms", "u16"), (6, "WMaxLimPct_RmpTms", "u16"),
    (7, "WMaxLim_Ena", "enum"),
    (8, "OutPFSet", "s16"), (9, "OutPFSet_WinTms", "u16"),
    (10, "OutPFSet_RvrtTms", "u16"), (11, "OutPFSet_RmpTms", "u16"),
    (12, "OutPFSet_Ena", "enum"),
    (13, "VArWMaxPct", "s16"), (14, "VArMaxPct", "s16"), (15, "VArAvalPct", "s16"),
    (16, "VArPct_WinTms", "u16"), (17, "VArPct_RvrtTms", "u16"),
    (18, "VArPct_RmpTms", "u16"), (19, "VArPct_Mod", "enum"),
    (20, "VArPct_Ena", "enum"),
    (21, "WMaxLimPct_SF", "sf"), (22, "OutPFSet_SF", "sf"), (23, "VArPct_SF", "sf"),
]

MODELS = {1: MODEL_1, 103: MODEL_103, 113: MODEL_113, 123: MODEL_123}
BASE = 40000
END_MARKER = 0xFFFF


def read(client, unit, address, count):
    for kwarg in ("device_id", "slave", "unit"):
        try:
            rr = client.read_holding_registers(address=address, count=count, **{kwarg: unit})
        except TypeError:
            continue
        if rr.isError():
            return None
        return rr.registers
    raise RuntimeError("no compatible pymodbus keyword for the unit id")


def decode(kind, regs):
    """Return (value, implemented) for one field."""
    if kind.startswith("str"):
        raw = b"".join(r.to_bytes(2, "big") for r in regs)
        text = raw.split(b"\x00")[0].decode("ascii", "replace").strip()
        return (repr(text) if text else "(empty)", bool(text))
    if kind == "u16":
        v = regs[0]
        return (v, v != 0xFFFF)
    if kind in ("s16", "sf"):
        v = struct.unpack(">h", regs[0].to_bytes(2, "big"))[0]
        return (v, regs[0] != 0x8000)
    if kind == "enum":
        v = regs[0]
        return (v, v != 0xFFFF)
    if kind == "bf32":
        v = (regs[0] << 16) | regs[1]
        return (f"0x{v:08X}", v != 0xFFFFFFFF)
    if kind == "acc32":
        v = (regs[0] << 16) | regs[1]
        return (v, True)
    if kind == "f32":
        v = struct.unpack(">f", struct.pack(">HH", regs[0], regs[1]))[0]
        return ("NaN" if math.isnan(v) else round(v, 3), not math.isnan(v))
    return (regs, True)


WIDTH = {"u16": 1, "s16": 1, "sf": 1, "enum": 1, "bf32": 2, "acc32": 2,
         "f32": 2, "str8": 8, "str16": 16}


def dump_model(client, unit, model_id, data_start, fields, out):
    out.append(f"\n### Model {model_id} — data {data_start}..{data_start + sum(WIDTH[f[2]] for f in fields) - 1}\n")
    out.append("| Register | Field | Type | Value | Implemented |")
    out.append("|---|---|---|---|---|")
    for offset, name, kind in fields:
        n = WIDTH[kind]
        addr = data_start + offset
        regs = read(client, unit, addr, n)
        if regs is None:
            out.append(f"| {addr} | {name} | {kind} | read error | — |")
            continue
        value, ok = decode(kind, regs)
        span = f"{addr}" if n == 1 else f"{addr}–{addr + n - 1}"
        out.append(f"| {span} | {name} | {kind} | {value} | {'yes' if ok else 'no'} |")


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.131"
    unit = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    client = ModbusTcpClient(host, port=502, timeout=5)
    if not client.connect():
        sys.exit(f"cannot connect to {host}:502")

    out = [f"# SunSpec register map — {host}, unit {unit}\n"]
    try:
        ptr = BASE + 2
        while True:
            header = read(client, unit, ptr, 2)
            if header is None:
                break
            model_id, length = header
            if model_id == END_MARKER:
                out.append(f"\nEnd-of-chain marker at {ptr}.\n")
                break
            if model_id in MODELS:
                dump_model(client, unit, model_id, ptr + 2, MODELS[model_id], out)
            else:
                out.append(f"\n### Model {model_id} — length {length}, no field table, raw dump\n")
                regs = read(client, unit, ptr + 2, min(length, 100))
                out.append(f"```\n{regs}\n```")
            ptr += length + 2
            if ptr > BASE + 2000:
                break

        # Proprietary block documented at 40214, sitting after the end marker.
        out.append("\n### Out-of-chain block at 40210 onwards (proprietary)\n")
        out.append("| Registers | Raw | As float32 |")
        out.append("|---|---|---|")
        for addr in range(40210, 40260, 2):
            regs = read(client, unit, addr, 2)
            if regs is None:
                out.append(f"| {addr}–{addr + 1} | read error | — |")
                continue
            f = struct.unpack(">f", struct.pack(">HH", regs[0], regs[1]))[0]
            shown = "NaN" if math.isnan(f) else round(f, 3)
            out.append(f"| {addr}–{addr + 1} | {regs} | {shown} |")
    finally:
        client.close()

    print("\n".join(out))


if __name__ == "__main__":
    main()
