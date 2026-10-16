"""End-to-end against a simulated ECU: one Modbus unit per inverter, silent
for addresses that are not configured, as the real gateway behaves."""
import pytest

from ecu_image import build_unit
from ecu_sim import EcuSim
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.apsystems_ecu_sunspec.const import DOMAIN


@pytest.fixture
async def ecu_factory():
    running = []

    async def make(units):
        ecu = EcuSim(units)
        port = await ecu.start()
        running.append(ecu)
        return ecu, port

    yield make
    for ecu in running:
        await ecu.stop()


async def _start(hass, port, last_unit=4):
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    return await hass.config_entries.flow.async_configure(
        r["flow_id"], {"host": "127.0.0.1", "port": port, "last_unit": last_unit})


async def _setup(hass, port, last_unit=4):
    r = await _start(hass, port, last_unit)
    assert r["step_id"] == "confirm", r
    summary = r["description_placeholders"]
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    return r["result"], summary


def _state(hass, eid):
    st = hass.states.get(eid)
    assert st is not None, f"{eid} missing"
    return st.state


async def test_three_phase_array(hass: HomeAssistant, ecu_factory):
    ecu, port = await ecu_factory({
        1: build_unit("9015000X0001", power_w=2100, energy_wh=2114),
        2: build_unit("9015000X0002", power_w=1900, energy_wh=1000, limit_ena=0),
    })
    # The control unit is unit 1; make its enable flag 0 to test auto-enable.
    ecu.set(1, 40193, 0)
    entry, summary = await _setup(hass, port)
    assert summary["count"] == "2" and summary["units"] == "1, 2"
    assert summary["models"] == "2 × QT2-3"
    assert summary["phases"] == "3" and summary["dc"] == "4"
    assert summary["controls"] == "Conn, WMaxLimPct, WMaxLim_Ena"
    assert summary["control_unit"] == "1"
    assert entry.unique_id == "ecu_9015000X0001"

    assert float(_state(hass, "sensor.apsystems_ecu_power")) == 4000
    assert float(_state(hass, "sensor.apsystems_ecu_energy")) == pytest.approx(3.114)  # kWh
    assert _state(hass, "sensor.apsystems_ecu_inverters_producing") == "2"
    assert float(_state(hass, "sensor.apsystems_ecu_dc_power_total")) == pytest.approx(2 * 186)
    assert float(_state(hass, "sensor.apsystems_inverter_1_power")) == 2100
    assert _state(hass, "sensor.apsystems_inverter_1_operating_state") == "mppt"
    assert _state(hass, "sensor.apsystems_inverter_1_events") == "none"
    assert float(_state(hass, "sensor.apsystems_inverter_2_voltage_l1_l2")) == 419
    assert float(_state(hass, "sensor.apsystems_inverter_2_dc4_voltage")) == pytest.approx(40.5)

    reg = er.async_get(hass)
    # DC points of model 103 are unimplemented on the ECU: no entity at all
    assert reg.async_get("sensor.apsystems_inverter_1_dc_power") is None
    # Phase-to-neutral voltages exist but are disabled by default
    ent = reg.async_get("sensor.apsystems_inverter_1_voltage_l1_n")
    assert ent is not None and ent.disabled_by is not None

    # Power limit: tenths of a percent on the wire, enable flag set if it was 0
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": "number.apsystems_ecu_power_limit", "value": 50.5}, blocking=True)
    assert ecu.reg(1, 40189) == 505
    assert ecu.reg(1, 40193) == 1
    assert ecu.reg(2, 40189) == 1000  # only the control unit is written
    assert float(_state(hass, "number.apsystems_ecu_power_limit")) == 50.5

    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": "switch.apsystems_ecu_production"}, blocking=True)
    assert ecu.reg(1, 40188) == 0
    assert _state(hass, "switch.apsystems_ecu_production") == "off"

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_single_phase_two_channels(hass: HomeAssistant, ecu_factory):
    _, port = await ecu_factory({
        1: build_unit("8016000X0001", model="DS3-L", phases=1, power_w=700, dc_channels=2),
    })
    _, summary = await _setup(hass, port, last_unit=3)
    assert summary["phases"] == "1" and summary["dc"] == "2"
    assert float(_state(hass, "sensor.apsystems_inverter_1_voltage")) == 230.1
    reg = er.async_get(hass)
    assert reg.async_get("sensor.apsystems_inverter_1_current_l2") is None
    assert reg.async_get("sensor.apsystems_inverter_1_dc3_voltage") is None
    assert reg.async_get("sensor.apsystems_inverter_1_dc2_power") is not None


async def test_without_dc_block(hass: HomeAssistant, ecu_factory):
    _, port = await ecu_factory({1: build_unit("9015000X0001", with_dc_block=False)})
    _, summary = await _setup(hass, port, last_unit=2)
    assert summary["dc"] == "0"
    reg = er.async_get(hass)
    assert reg.async_get("sensor.apsystems_inverter_1_dc_power_total") is None
    assert reg.async_get("sensor.apsystems_ecu_dc_power_total") is None


async def test_non_contiguous_addresses(hass: HomeAssistant, ecu_factory):
    """Addresses set in EMA need not start at 1 nor be contiguous."""
    _, port = await ecu_factory({
        3: build_unit("9015000X0003"), 5: build_unit("9015000X0005"),
    })
    _, summary = await _setup(hass, port, last_unit=8)
    assert summary["units"] == "3, 5"
    assert summary["control_unit"] == "3"


async def test_adapter_refused(hass: HomeAssistant, ecu_factory):
    _, port = await ecu_factory({1: build_unit("9015000X0001", adapter_models=True)})
    r = await _start(hass, port, 2)
    assert r["errors"] == {"base": "adapter_unsupported"}


async def test_cannot_connect(hass: HomeAssistant):
    r = await _start(hass, 1, 2)
    assert r["errors"] == {"base": "cannot_connect"}


async def test_reconfigure_finds_new_inverter(hass: HomeAssistant, ecu_factory):
    ecu, port = await ecu_factory({1: build_unit("9015000X0001")})
    entry, _ = await _setup(hass, port, last_unit=3)
    assert hass.states.get("sensor.apsystems_inverter_2_power") is None

    ecu2, port2 = await ecu_factory({
        1: build_unit("9015000X0001"), 2: build_unit("9015000X0002"),
    })
    r = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id})
    assert r["step_id"] == "reconfigure"
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"], {"host": "127.0.0.1", "port": port2, "last_unit": 3})
    assert r["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()
    assert len(entry.data["units"]) == 2
    assert hass.states.get("sensor.apsystems_inverter_2_power") is not None


async def test_options_and_diagnostics(hass: HomeAssistant, ecu_factory):
    from custom_components.apsystems_ecu_sunspec.diagnostics import (
        async_get_config_entry_diagnostics,
    )
    _, port = await ecu_factory({1: build_unit("9015000X0001")})
    entry, _ = await _setup(hass, port, last_unit=2)
    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert "9015000X0001" not in str(diag)
    assert "127.0.0.1" not in str(diag)

    r = await hass.config_entries.options.async_init(entry.entry_id)
    r = await hass.config_entries.options.async_configure(
        r["flow_id"], {"scan_interval": 15.0, "limit_keepalive": 0.0})
    assert r["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["scan_interval"] == 15
    await hass.async_block_till_done()


async def test_falls_back_to_short_reads(hass: HomeAssistant, ecu_factory):
    """A firmware that ignores long reads is polled model by model."""
    ecu, port = await ecu_factory({1: build_unit("9015000X0001")})
    original = ecu._answer

    def short_only(unit, pdu):
        if pdu[0] == 3 and int.from_bytes(pdu[3:5], "big") > 70:
            return None  # silence, as the ECU does for requests it rejects
        return original(unit, pdu)

    ecu._answer = short_only
    entry, _ = await _setup(hass, port, last_unit=2)
    assert float(_state(hass, "sensor.apsystems_inverter_1_power")) == 2100
    assert entry.runtime_data.split_reads == {1}
