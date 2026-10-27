"""Decoders against a register image built from the measured ECU-C map."""
import pytest

from ecu_image import BASE, build_unit
from ecusunspec.models import (
    DC_HEADER,
    ModelRef,
    UnitLayout,
    active_events,
    asleep,
    channels_for,
    decode_unit,
    measurement_fingerprint,
    merge_ranges,
)


def layout(phases=3, dc=4):
    return UnitLayout(
        unit=1, serial="9015000X0001", model="QT2-3", version="V1169", phases=phases,
        int_model=ModelRef(100 + phases, 40070, 50),
        float_model=ModelRef(110 + phases, 40122, 60),
        controls=ModelRef(123, 40184, 24),
        dc_channels=dc,
    )


def words(image):
    return {BASE + i: v for i, v in enumerate(image)}


def test_three_phase_values():
    d = decode_unit(layout(), words(build_unit("9015000X0001")), True)
    assert d["power"] == 2100.0
    assert d["current"] == 3.0 and d["current_c"] == 1.0
    assert d["voltage_ab"] == 419.0 and d["voltage_ca"] == 420.0
    assert d["frequency"] == 49.99
    assert d["power_factor"] == 1.0
    assert d["temperature"] == 24.0
    # integer model wins: exact counter, and it carries state and events
    assert d["energy"] == 2114
    assert d["state"] == 4
    assert d["events"] == 0
    # unimplemented everywhere stays None
    assert d["dc_power"] is None and d["dc_voltage"] is None


def test_float_fallback_when_int_point_missing():
    img = build_unit("9015000X0001")
    img[40084 - BASE] = 0x8000  # W unimplemented in model 103
    d = decode_unit(layout(), words(img), False)
    assert d["power"] == pytest.approx(2100.0)


def test_dc_block_is_volts_amps_watts():
    d = decode_unit(layout(), words(build_unit("9015000X0001")), False)
    assert d["dc1_voltage"] == pytest.approx(37.5)
    assert d["dc4_voltage"] == pytest.approx(40.5)
    assert d["dc2_current"] == pytest.approx(1.2)
    assert d["dc3_power"] == pytest.approx(47.0)
    assert d["dc_power_total"] == pytest.approx(45 + 46 + 47 + 48)


def test_controls_scaled():
    d = decode_unit(layout(), words(build_unit("9015000X0001", limit_raw=355)), True)
    assert d["limit_pct"] == 35.5
    assert d["conn"] == 1 and d["limit_enabled"] == 1


def test_controls_only_on_control_unit():
    d = decode_unit(layout(), words(build_unit("9015000X0001")), False)
    assert "limit_pct" not in d


def test_single_phase():
    img = build_unit("8016000X0001", model="DS3-L", phases=1, dc_channels=2)
    d = decode_unit(layout(phases=1, dc=2), words(img), False)
    assert d["voltage_a"] == 230.1
    assert d["current_b"] is None
    assert "dc3_voltage" not in d


def test_spans_fit_modbus_limit():
    spans = layout().spans(include_controls=True)
    assert all(end - start <= 125 for start, end in spans)
    assert spans[0][0] == 40072 and spans[-1][1] == DC_HEADER + 2 + 48
    assert len(spans) == 2


def test_merge_ranges():
    assert merge_ranges([(0, 50), (60, 100), (110, 200)]) == [(0, 100), (110, 200)]


def test_channels_and_events():
    assert channels_for("QT2-3") == 4 and channels_for("DS3-H") == 2 and channels_for("XYZ") == 0
    assert active_events(0x8123) == [
        "ground_fault", "dc_over_volt", "cabinet_open", "over_frequency", "hw_test_failure"
    ]


def test_unmerged_spans_one_per_model():
    spans = layout().spans(include_controls=True, merge=False)
    assert spans == [(40072, 40122), (40124, 40184), (40186, 40210), (40214, 40262)]


def test_fingerprint_ignores_controls():
    """Writing a power limit must not make old measurements look fresh."""
    img = words(build_unit("9015000X0001"))
    fp = measurement_fingerprint(layout(), img)
    img[40189] = 500  # WMaxLimPct
    img[40193] = 0  # WMaxLim_Ena
    assert measurement_fingerprint(layout(), img) == fp
    img[40086] += 1  # Hz in the integer model
    assert measurement_fingerprint(layout(), img) != fp


def test_fingerprint_covers_dc_block():
    img = words(build_unit("9015000X0001"))
    fp = measurement_fingerprint(layout(), img)
    img[DC_HEADER + 2] ^= 1  # DCV1, low bit
    assert measurement_fingerprint(layout(), img) != fp


def test_asleep_values():
    d = asleep(decode_unit(layout(), words(build_unit("9015000X0001")), True))
    assert d["state"] == 2  # sleeping, whatever the ECU still says
    assert d["power"] == 0.0 and d["current"] == 0.0 and d["current_a"] == 0.0
    assert d["dc_power_total"] == 0.0 and d["dc1_power"] == 0.0 and d["dc1_current"] == 0.0
    assert d["apparent_power"] == 0.0 and d["reactive_power"] == 0.0
    assert d["voltage_ab"] is None and d["dc1_voltage"] is None
    assert d["frequency"] is None and d["temperature"] is None and d["power_factor"] is None
    assert d["events"] is None
    assert d["energy"] == 2114  # counters keep their value
    # the global controls of the control unit are not measurements
    assert d["limit_pct"] == 100.0 and d["limit_enabled"] == 1 and d["conn"] is not None
    # unimplemented points stay unimplemented
    assert d["dc_power"] is None
