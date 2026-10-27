"""SunSpec models served by the APsystems ECU, decoded without Home Assistant.

Everything here is pure Python so it can be unit-tested on its own. Offsets are
relative to the first data register of a model (header + 2), as in the SunSpec
specification. The behaviour notes come from measurements on an ECU-C, see
docs/register-map.md in this repository.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import math
import struct

BASE = 40000
SUNS = (0x5375, 0x6E53)  # "SunS"
END_MARKER = 0xFFFF
MAX_READ = 125  # Modbus limit for one holding-register read

# The ECU places a DC block (model 114) after the end-of-chain marker, so a
# conforming chain walk never finds it. Its address is fixed.
DC_HEADER = 40212
DC_MODEL = 114
DC_LENGTH = 48
DC_CHANNELS = 8

MODEL_COMMON = 1
INT_MODELS = {101: 1, 102: 2, 103: 3}  # model -> phase count
FLOAT_MODELS = {111: 1, 112: 2, 113: 3}
MODEL_CONTROLS = 123
# Models only served by the bolkedebruin/apsystems-sunspec adapter, never by
# the ECU's own port 502 server.
ADAPTER_MODELS = {120, 121, 160, 64202}

OPERATING_STATES = {
    1: "off",
    2: "sleeping",
    3: "starting",
    4: "mppt",
    5: "throttled",
    6: "shutting_down",
    7: "fault",
    8: "standby",
}

EVENT1_BITS = {
    0: "ground_fault",
    1: "dc_over_volt",
    2: "ac_disconnect",
    3: "dc_disconnect",
    4: "grid_disconnect",
    5: "cabinet_open",
    6: "manual_shutdown",
    7: "over_temp",
    8: "over_frequency",
    9: "under_frequency",
    10: "ac_over_volt",
    11: "ac_under_volt",
    12: "blown_string_fuse",
    13: "under_temp",
    14: "memory_loss",
    15: "hw_test_failure",
}

# DC channels per inverter family, from the model string of model 1.
CHANNELS_BY_FAMILY = (
    ("QT2", 4),
    ("QS1", 4),
    ("YC1000", 4),
    ("DS3", 2),
    ("YC600", 2),
    ("EZ1", 2),
)


@dataclass
class ModelRef:
    """One model found on a unit: id, header address and data length."""

    model_id: int
    address: int
    length: int

    @property
    def start(self) -> int:
        return self.address + 2

    @property
    def end(self) -> int:  # exclusive
        return self.start + self.length


@dataclass
class UnitLayout:
    """What one Modbus unit (one inverter on the ECU) exposes."""

    unit: int
    serial: str
    model: str
    version: str
    phases: int
    int_model: ModelRef | None = None
    float_model: ModelRef | None = None
    controls: ModelRef | None = None
    dc_channels: int = 0  # 0 = no DC block
    others: list[int] = field(default_factory=list)

    def as_dict(self) -> dict:
        def ref(r: ModelRef | None):
            return None if r is None else [r.model_id, r.address, r.length]

        return {
            "unit": self.unit,
            "serial": self.serial,
            "model": self.model,
            "version": self.version,
            "phases": self.phases,
            "int_model": ref(self.int_model),
            "float_model": ref(self.float_model),
            "controls": ref(self.controls),
            "dc_channels": self.dc_channels,
            "others": list(self.others),
        }

    @classmethod
    def from_dict(cls, d: dict) -> UnitLayout:
        def ref(v):
            return None if v is None else ModelRef(*v)

        return cls(
            unit=d["unit"],
            serial=d["serial"],
            model=d["model"],
            version=d.get("version", ""),
            phases=d["phases"],
            int_model=ref(d.get("int_model")),
            float_model=ref(d.get("float_model")),
            controls=ref(d.get("controls")),
            dc_channels=d.get("dc_channels", 0),
            others=list(d.get("others", [])),
        )

    def spans(self, include_controls: bool, merge: bool = True) -> list[tuple[int, int]]:
        """Address ranges to poll each cycle, merged into as few reads as
        possible. Gaps inside a span are read too: the ECU answers anywhere
        between 40000 and 40300. merge=False gives one read per model."""
        wanted = [m for m in (self.int_model, self.float_model) if m]
        if include_controls and self.controls:
            wanted.append(self.controls)
        ranges = sorted((m.start, m.end) for m in wanted)
        if self.dc_channels:
            ranges.append((DC_HEADER + 2, DC_HEADER + 2 + DC_LENGTH))
            ranges.sort()
        return merge_ranges(ranges) if merge else ranges


def merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Merge [start, end) ranges into reads of at most MAX_READ registers."""
    out: list[tuple[int, int]] = []
    for start, end in ranges:
        if out and end - out[-1][0] <= MAX_READ:
            out[-1] = (out[-1][0], max(out[-1][1], end))
        else:
            out.append((start, end))
    return out


# ---------------------------------------------------------------------------
# Primitive decoders. Each returns None for SunSpec "not implemented" values.
# ---------------------------------------------------------------------------


def u16(w: int) -> int | None:
    return None if w == 0xFFFF else w


def s16(w: int) -> int | None:
    if w == 0x8000:
        return None
    return w - 0x10000 if w & 0x8000 else w


def sf(w: int) -> int | None:
    v = s16(w)
    return None if v is None or not -10 <= v <= 10 else v


def acc32(hi: int, lo: int) -> int:
    return (hi << 16) | lo


def bf32(hi: int, lo: int) -> int | None:
    v = (hi << 16) | lo
    return None if v == 0xFFFFFFFF else v


def f32(hi: int, lo: int) -> float | None:
    v = struct.unpack(">f", struct.pack(">HH", hi, lo))[0]
    return None if math.isnan(v) or math.isinf(v) else v


def string(words: list[int]) -> str:
    raw = b"".join(w.to_bytes(2, "big") for w in words)
    return raw.split(b"\x00", 1)[0].decode("ascii", "replace").strip()


def scaled(value: int | None, factor: int | None) -> float | None:
    if value is None or factor is None:
        return None
    return round(value * 10**factor, max(0, -factor))


def to_float_words(value: float) -> tuple[int, int]:
    """Encode a float32 the way the ECU stores it (big-endian words)."""
    hi, lo = struct.unpack(">HH", struct.pack(">f", value))
    return hi, lo


def channels_for(model: str) -> int:
    up = model.upper()
    for prefix, count in CHANNELS_BY_FAMILY:
        if up.startswith(prefix):
            return count
    return 0


# ---------------------------------------------------------------------------
# Model decoders. `w` is the list of data words of the model, from offset 0.
# ---------------------------------------------------------------------------


def decode_common(w: list[int]) -> dict:
    return {
        "manufacturer": string(w[0:16]),
        "model": string(w[16:32]),
        "options": string(w[32:40]),
        "version": string(w[40:48]),
        "serial": string(w[48:64]),
        "device_address": w[64] if len(w) > 64 else None,
    }


def decode_inverter_int(w: list[int]) -> dict:
    """Models 101/102/103 (integer + scale factor). Same layout for all three;
    phase B and C points are simply unimplemented on 101."""
    a_sf, v_sf, w_sf = sf(w[4]), sf(w[11]), sf(w[13])
    hz_sf, va_sf, var_sf, pf_sf = sf(w[15]), sf(w[17]), sf(w[19]), sf(w[21])
    wh_sf, tmp_sf = sf(w[24]), sf(w[35])
    dca_sf, dcv_sf, dcw_sf = sf(w[26]), sf(w[28]), sf(w[30])
    wh_raw = acc32(w[22], w[23])
    return {
        "current": scaled(u16(w[0]), a_sf),
        "current_a": scaled(u16(w[1]), a_sf),
        "current_b": scaled(u16(w[2]), a_sf),
        "current_c": scaled(u16(w[3]), a_sf),
        "voltage_ab": scaled(u16(w[5]), v_sf),
        "voltage_bc": scaled(u16(w[6]), v_sf),
        "voltage_ca": scaled(u16(w[7]), v_sf),
        "voltage_a": scaled(u16(w[8]), v_sf),
        "voltage_b": scaled(u16(w[9]), v_sf),
        "voltage_c": scaled(u16(w[10]), v_sf),
        "power": scaled(s16(w[12]), w_sf),
        "frequency": scaled(u16(w[14]), hz_sf),
        "apparent_power": scaled(s16(w[16]), va_sf),
        "reactive_power": scaled(s16(w[18]), var_sf),
        "power_factor": scaled(s16(w[20]), pf_sf),
        "energy": scaled(wh_raw, wh_sf) if wh_raw else None,
        "dc_current": scaled(u16(w[25]), dca_sf),
        "dc_voltage": scaled(u16(w[27]), dcv_sf),
        "dc_power": scaled(s16(w[29]), dcw_sf),
        "temperature": scaled(s16(w[31]), tmp_sf),
        "state": u16(w[36]),
        "events": bf32(w[38], w[39]),
    }


def decode_inverter_float(w: list[int]) -> dict:
    """Models 111/112/113. On the ECU, St and Evt1 are not implemented here."""

    def f(i: int) -> float | None:
        return f32(w[i], w[i + 1])

    return {
        "current": f(0),
        "current_a": f(2),
        "current_b": f(4),
        "current_c": f(6),
        "voltage_ab": f(8),
        "voltage_bc": f(10),
        "voltage_ca": f(12),
        "voltage_a": f(14),
        "voltage_b": f(16),
        "voltage_c": f(18),
        "power": f(20),
        "frequency": f(22),
        "apparent_power": f(24),
        "reactive_power": f(26),
        "power_factor": f(28),
        "energy": f(30),
        "dc_current": f(32),
        "dc_voltage": f(34),
        "dc_power": f(36),
        "temperature": f(38),
        "state": u16(w[46]),
        "events": bf32(w[48], w[49]),
    }


def decode_controls(w: list[int]) -> dict:
    """Model 123. Only Conn, WMaxLimPct and WMaxLim_Ena work on the ECU."""
    pct_sf = sf(w[21])
    return {
        "conn": u16(w[2]),
        "limit_pct": scaled(u16(w[3]), pct_sf),
        "limit_enabled": u16(w[7]),
        "limit_pct_sf": pct_sf,
    }


def decode_dc(w: list[int], channels: int) -> dict:
    """Out-of-chain model 114: DCV1..8, DCA1..8, DCW1..8, all float32."""
    out: dict = {}
    for ch in range(1, channels + 1):
        i = 2 * (ch - 1)
        out[f"dc{ch}_voltage"] = f32(w[i], w[i + 1])
        out[f"dc{ch}_current"] = f32(w[16 + i], w[17 + i])
        out[f"dc{ch}_power"] = f32(w[32 + i], w[33 + i])
    powers = [out[f"dc{ch}_power"] for ch in range(1, channels + 1)]
    out["dc_power_total"] = None if any(p is None for p in powers) else round(sum(powers), 1)
    return out


INVERTER_KEYS = tuple(decode_inverter_float([0] * 50).keys())


def merge_inverter(primary: dict | None, fallback: dict | None) -> dict:
    """Integer model first (it carries state and events and its energy
    counter does not lose precision), float model for anything the integer
    model leaves unimplemented."""
    primary, fallback = primary or {}, fallback or {}
    return {
        k: primary.get(k) if primary.get(k) is not None else fallback.get(k)
        for k in INVERTER_KEYS
    }


def active_events(bits: int | None) -> list[str]:
    if bits is None:
        return []
    return [name for bit, name in EVENT1_BITS.items() if bits & (1 << bit)]


def decode_unit(layout: UnitLayout, words: dict[int, int], with_controls: bool) -> dict:
    """Decode everything polled for one unit from an address -> word map."""

    def block(ref: ModelRef | None) -> list[int] | None:
        if ref is None:
            return None
        try:
            return [words[a] for a in range(ref.start, ref.end)]
        except KeyError:
            return None

    iw, fw = block(layout.int_model), block(layout.float_model)
    data = merge_inverter(
        decode_inverter_int(iw) if iw else None,
        decode_inverter_float(fw) if fw else None,
    )
    if layout.dc_channels:
        dc = block(ModelRef(DC_MODEL, DC_HEADER, DC_LENGTH))
        if dc:
            data.update(decode_dc(dc, layout.dc_channels))
    if with_controls:
        cw = block(layout.controls)
        if cw:
            data.update(decode_controls(cw))
    return data


# --- data the ECU keeps serving after the inverters went to sleep -----------
#
# Once the inverters stop at dusk, the ECU goes on answering with the values of
# its last round: voltage, frequency, a few watts, operating state "MPPT". No
# register says the data is old. During the day the ECU refreshes them about
# every 5 minutes and the measurements change at nearly every round, so data
# that has not changed for several rounds is taken as asleep.

STATE_SLEEPING = 2
_QUANTITIES_WITHOUT_ZERO = ("voltage", "frequency", "temperature", "power_factor", "events")


def measurement_fingerprint(layout: UnitLayout, words: dict[int, int]) -> tuple[int, ...]:
    """The measurement registers of one unit, controls excluded (writing a
    limit must not make old data look fresh)."""
    ranges = [(m.start, m.end) for m in (layout.int_model, layout.float_model) if m]
    if layout.dc_channels:
        ranges.append((DC_HEADER + 2, DC_HEADER + 2 + DC_LENGTH))
    return tuple(words.get(a, -1) for start, end in sorted(ranges) for a in range(start, end))


def asleep(data: dict) -> dict:
    """What an inverter that stopped producing reports: no power and no
    current, no live voltage, frequency or temperature, state sleeping.
    Energy counters keep their last value."""
    out = dict(data)
    for key, value in data.items():
        if value is None or key in ("energy", "conn", "limit_pct", "limit_enabled", "limit_pct_sf"):
            continue
        if any(q in key for q in _QUANTITIES_WITHOUT_ZERO):
            out[key] = None
        elif "power" in key or "current" in key:
            out[key] = 0.0
    out["state"] = STATE_SLEEPING
    return out


# --- the ECU itself ---------------------------------------------------------
#
# The ECU does not show itself over Modbus, so its ID (12 digits, on the label
# and in EMA) is typed in at setup. Its prefix tells the model, after
# APsystems' SunSpec Modbus document.

ECU_ID_PREFIXES = (  # longest first
    ("2160", "ECU-R"),
    ("2162", "ECU-R Pro"),
    ("2163", "ECU-B"),
    ("215", "ECU-C"),
)
DEFAULT_ECU_TITLE = "APsystems ECU"


def clean_ecu_id(text: str | None) -> str | None:
    """The ECU ID without spaces, or None when left empty. Raises ValueError
    unless it is 12 digits."""
    value = "".join((text or "").split())
    if not value:
        return None
    if len(value) != 12 or not value.isdigit():
        raise ValueError(value)
    return value


def ecu_model(ecu_id: str | None) -> str | None:
    if not ecu_id:
        return None
    return next((name for prefix, name in ECU_ID_PREFIXES if ecu_id.startswith(prefix)), "ECU")


def ecu_title(ecu_id: str | None) -> str:
    """Name of the entry and of the ECU device: model and ID tail."""
    if not ecu_id:
        return DEFAULT_ECU_TITLE
    return f"{ecu_model(ecu_id)} ({ecu_id[-4:]})"


def inverter_name(layout: UnitLayout, layouts: list[UnitLayout]) -> str:
    """Device name of an inverter: model and the end of its serial, e.g.
    "QT2-3 (7556)". Unique even with several ECUs, unlike the Modbus
    address. The whole serial when two inverters of the ECU share an end."""
    tail = layout.serial[-4:]
    clash = any(o is not layout and o.serial[-4:] == tail for o in layouts)
    return f"{layout.model} ({layout.serial if clash else tail})"
