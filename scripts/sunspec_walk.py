#!/usr/bin/env python3
"""
Walk the SunSpec model chain of an APsystems ECU over Modbus TCP.

Usage:  python3 sunspec_walk.py 192.168.1.131 1
        (host, then the inverter Modbus address configured in the ECU page)

Prints every SunSpec model the ECU actually exposes, with its ID, length and
register offsets. Useful to compare a real firmware against the official
"SunSpec Modbus" PDF, which only documents models 1, 101-103, 111-113, 123
and the DC block.

Requires: pip install pymodbus
"""

import sys

from pymodbus.client import ModbusTcpClient

# SunSpec model IDs worth naming; anything else is printed as "unknown".
NAMES = {
    1: "Common (manufacturer, model, serial)",
    101: "Inverter, single phase (int+SF)",
    102: "Inverter, split phase (int+SF)",
    103: "Inverter, three phase (int+SF)",
    111: "Inverter, single phase (float)",
    112: "Inverter, split phase (float)",
    113: "Inverter, three phase (float)",
    120: "Nameplate ratings",
    121: "Basic settings",
    122: "Measurements/status",
    123: "Immediate controls (Conn, WMaxLimPct)",
    124: "Storage",
    126: "Static volt-VAR",
    131: "Multiple MPPT inverter extension",
    160: "Multiple MPPT inverter extension",
    201: "Meter, single phase",
    202: "Meter, split phase",
    203: "Meter, wye three phase",
    204: "Meter, delta three phase",
    211: "Meter, single phase (float)",
    213: "Meter, wye three phase (float)",
}

BASE = 40000          # "SunS" identifier lives here on APsystems ECUs
END_MARKER = 0xFFFF


def read(client, unit, address, count):
    """Read holding registers, tolerating pymodbus 3.x API changes."""
    for kwarg in ("device_id", "slave", "unit"):
        try:
            rr = client.read_holding_registers(address=address, count=count, **{kwarg: unit})
        except TypeError:
            continue
        if rr.isError():
            raise IOError(f"Modbus error reading {address}+{count}: {rr}")
        return rr.registers
    raise RuntimeError("no compatible pymodbus keyword for the unit id")


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else "192.168.1.131"
    unit = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    client = ModbusTcpClient(host, port=502, timeout=5)
    if not client.connect():
        sys.exit(f"cannot connect to {host}:502")

    try:
        marker = read(client, unit, BASE, 2)
        text = b"".join(r.to_bytes(2, "big") for r in marker).decode("ascii", "replace")
        print(f"host {host}  unit {unit}")
        print(f"{BASE}: identifier = {marker} -> {text!r}"
              f"{'  (expected SunS)' if text != 'SunS' else '  OK'}\n")

        ptr = BASE + 2
        while True:
            model_id, length = read(client, unit, ptr, 2)
            if model_id == END_MARKER:
                print(f"{ptr}: end marker")
                break
            name = NAMES.get(model_id, "unknown / undocumented")
            print(f"{ptr}: model {model_id:<5} length {length:<5} "
                  f"data {ptr + 2}..{ptr + 1 + length}   {name}")
            ptr += length + 2
            if ptr > BASE + 2000:
                print("aborting: chain longer than 2000 registers, probably desynchronised")
                break

        # Model 123 timing registers, never readable from the official doc alone.
        print("\nImmediate controls block (model 123), raw values:")
        labels = ["Conn_WinTms", "Conn_RvrtTms", "Conn", "WMaxLimPct",
                  "WMaxLimPct_WinTms", "WMaxLimPct_RvrtTms", "WMaxLimPct_RmpTms",
                  "WMaxLim_Ena"]
        regs = read(client, unit, 40186, 8)
        for offset, (label, value) in enumerate(zip(labels, regs)):
            note = "  (0xFFFF = not implemented)" if value == 0xFFFF else ""
            print(f"  {40186 + offset}: {label:<20} {value}{note}")

    finally:
        client.close()


if __name__ == "__main__":
    main()
