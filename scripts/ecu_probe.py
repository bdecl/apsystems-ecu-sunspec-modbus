#!/usr/bin/env python3
"""
Probe an APsystems ECU for undocumented Modbus content.

Two passes:

  1. Unit scan   - which slave ids answer at all, and what each one says it is.
                   Looks for a non-inverter device: the ECU itself, a meter, a
                   storage system. This is where CT data would live if it is
                   exposed at all.

  2. Address sweep - coarse probe of the whole 16-bit address space on one unit,
                   then a finer scan around every hit, to find blocks outside
                   the SunSpec chain.

Usage:
    python3 ecu_probe.py 192.168.1.131 units
    python3 ecu_probe.py 192.168.1.131 sweep 1

Read-only. Nothing is written to the device.
Requires: pip install pymodbus
"""

import sys
import time

from pymodbus.client import ModbusTcpClient

KNOWN = {
    (40000, 40261): "documented SunSpec chain + model 114",
}


def read(client, unit, address, count, retries=0):
    """Read holding registers. Returns list or None on any Modbus error."""
    for kwarg in ("device_id", "slave", "unit"):
        try:
            rr = client.read_holding_registers(address=address, count=count, **{kwarg: unit})
        except TypeError:
            continue
        except Exception:
            return None
        return None if rr.isError() else rr.registers
    raise RuntimeError("no compatible pymodbus keyword for the unit id")


def as_text(regs):
    raw = b"".join(r.to_bytes(2, "big") for r in regs)
    return raw.split(b"\x00")[0].decode("ascii", "replace").strip()


def scan_units(host, lo=0, hi=247):
    """Find every slave id that answers, and identify it via the Common model."""
    print(f"scanning unit ids {lo}..{hi} on {host} — this takes a few minutes\n")
    client = ModbusTcpClient(host, port=502, timeout=1.0, retries=0)
    if not client.connect():
        sys.exit(f"cannot connect to {host}:502")
    found = []
    try:
        for unit in range(lo, hi + 1):
            regs = read(client, unit, 40004, 16)
            if regs is None:
                continue
            mn = as_text(regs)
            md_regs = read(client, unit, 40020, 16)
            sn_regs = read(client, unit, 40052, 16)
            md = as_text(md_regs) if md_regs else "?"
            sn = as_text(sn_regs) if sn_regs else "?"
            print(f"  unit {unit:>3}: {mn!r} / {md!r} / serial {sn!r}"
                  f"{'   <- unit 0, likely an alias, compare the serial' if unit == 0 else ''}")
            found.append((unit, mn, md, sn))
            if unit % 25 == 0:
                time.sleep(0.1)
    finally:
        client.close()
    print(f"\n{len(found)} unit(s) answered.")
    if len(found) <= 1 and (lo, hi) == (0, 247):
        print("Only the inverter address(es) you configured respond — the ECU does not")
        print("expose itself as a separate Modbus device, so its CTs are not reachable here.")
    return found


def sweep(host, unit, step=100, span=65500):
    """Coarse probe of the address space, then fine scan around each hit."""
    client = ModbusTcpClient(host, port=502, timeout=1.0, retries=0)
    if not client.connect():
        sys.exit(f"cannot connect to {host}:502")

    hits = []
    try:
        print(f"coarse probe of 0..{span} on unit {unit}, step {step}\n")
        for addr in range(0, span, step):
            regs = read(client, unit, addr, 1)
            if regs is not None:
                hits.append(addr)
        if not hits:
            print("no address answered outside the chain.")
            return
        # Collapse consecutive hits into regions.
        regions, start, prev = [], hits[0], hits[0]
        for a in hits[1:]:
            if a - prev > step:
                regions.append((start, prev + step))
                start = a
            prev = a
        regions.append((start, prev + step))

        print(f"{len(hits)} probe points answered, in {len(regions)} region(s):\n")
        for lo, hi in regions:
            label = ""
            for (klo, khi), name in KNOWN.items():
                if lo <= khi and hi >= klo:
                    label = f"  <- overlaps {name}"
            print(f"  {lo}..{hi}{label}")

        print("\nfine scan, non-zero content only:\n")
        for lo, hi in regions:
            for addr in range(lo, hi, 10):
                regs = read(client, unit, addr, 10)
                if regs is None or not any(r not in (0, 0xFFFF) for r in regs):
                    continue
                if 40000 <= addr <= 40261:
                    continue  # already mapped
                print(f"  {addr}..{addr + 9}: {regs}")
    finally:
        client.close()


def main():
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    host, mode = sys.argv[1], sys.argv[2]
    if mode == "units":
        lo = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        hi = int(sys.argv[4]) if len(sys.argv) > 4 else 247
        scan_units(host, lo, hi)
    elif mode == "sweep":
        unit = int(sys.argv[3]) if len(sys.argv) > 3 else 1
        sweep(host, unit)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
