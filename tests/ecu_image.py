"""Register image of one ECU unit (one inverter), from docs/register-map.md.

Values are daytime-like but the layout, sentinels and quirks are the ones
measured on an ECU-C: integer + float inverter models, model 123 with three
working points, an end marker at 40210 and model 114 after it. Serial numbers
are made up.
"""
import struct

BASE = 40000
SIZE = 301  # the ECU answers from 40000 to 40300

NA16, NAS16 = 0xFFFF, 0x8000


def _str(text: str, words: int) -> list[int]:
    raw = text.encode().ljust(2 * words, b"\x00")
    return [int.from_bytes(raw[i:i + 2], "big") for i in range(0, 2 * words, 2)]


def _f(v: float) -> list[int]:
    return list(struct.unpack(">HH", struct.pack(">f", v)))


def _s(v: int) -> int:
    return v & 0xFFFF


NAN = [0x7FC0, 0x0000]


def build_unit(
    serial: str,
    model: str = "QT2-3",
    phases: int = 3,
    power_w: float = 2100.0,
    energy_wh: int = 2114,
    dc_channels: int = 4,
    with_dc_block: bool = True,
    limit_raw: int = 1000,
    limit_ena: int = 1,
    adapter_models: bool = False,
) -> list[int]:
    w = [0] * SIZE

    def put(addr: int, words: list[int]) -> None:
        w[addr - BASE:addr - BASE + len(words)] = words

    put(40000, [0x5375, 0x6E53])
    put(40002, [1, 66])
    put(40004, _str("APsystems", 16))
    put(40020, _str(model, 16))
    put(40036, _str("unimplemented", 8))
    put(40044, _str("V1169", 8))
    put(40052, _str(serial, 16))
    put(40068, [1, 0])

    ph_b = 100 if phases == 3 else NA16
    put(40070, [100 + phases, 50])
    put(40072, [
        300, 100, ph_b, ph_b, _s(-2),          # A, AphA..C, A_SF
        4190 if phases == 3 else NA16, 4180 if phases == 3 else NA16,
        4200 if phases == 3 else NA16,         # PPVphAB..CA
        0 if phases == 3 else 2301, 0 if phases == 3 else NA16,
        0 if phases == 3 else NA16, _s(-1),    # PhVphA..C, V_SF
        _s(int(power_w * 10)), _s(-1),         # W, W_SF
        4999, _s(-2),                          # Hz
        _s(int(power_w * 10)), _s(-1),         # VA
        0, _s(-1),                             # VAr
        1000, _s(-3),                          # PF
        energy_wh >> 16, energy_wh & 0xFFFF, 0,  # WH, WH_SF
        NA16, NAS16, NA16, NAS16, NAS16, NAS16,  # DCA, DCV, DCW + SF
        240, NAS16, NAS16, NAS16, _s(-1),      # temperatures, Tmp_SF
        4, NA16,                               # St, StVnd
        0, 0,                                  # Evt1
        *([NA16] * 10),                        # Evt2, EvtVnd1..4
    ])

    put(40122, [110 + phases, 60])
    fl = []
    for v in (3.0, 1.0, 1.0 if phases == 3 else None, 1.0 if phases == 3 else None,
              419.0 if phases == 3 else None, 418.0 if phases == 3 else None,
              420.0 if phases == 3 else None,
              0.0 if phases == 3 else 230.1, 0.0 if phases == 3 else None,
              0.0 if phases == 3 else None,
              power_w, 49.99, power_w, 0.0, 1.0, energy_wh + 0.685,
              None, None, None, 24.0, None, None, None):
        fl += NAN if v is None else _f(v)
    fl += [NA16, NA16] + [NA16] * 12           # St, StVnd, Evt1..EvtVnd4
    put(40124, fl)

    put(40184, [123, 24])
    put(40186, [
        NA16, NA16, 1, limit_raw, NA16, NA16, NA16, limit_ena,
        NAS16, NA16, NA16, NA16, NA16,
        NAS16, NAS16, NAS16, NA16, NA16, NA16, NA16, NA16,
        _s(-1), _s(-1), _s(-1),
    ])

    if adapter_models:
        # The adapter appends vendor model 64202 before the end marker.
        put(40210, [64202, 0])
        put(40212, [0xFFFF, 0])
        return w

    put(40210, [0xFFFF, 0])
    if with_dc_block:
        put(40212, [114, 48])
        for ch in range(dc_channels):
            put(40214 + 2 * ch, _f(37.5 + ch))
            put(40230 + 2 * ch, _f(1.2))
            put(40246 + 2 * ch, _f(45.0 + ch))
    return w
