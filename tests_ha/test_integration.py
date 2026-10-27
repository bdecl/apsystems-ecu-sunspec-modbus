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
    assert float(_state(hass, "sensor.qt2_3_0001_power")) == 2100
    assert _state(hass, "sensor.qt2_3_0001_operating_state") == "mppt"
    assert _state(hass, "sensor.qt2_3_0001_events") == "none"
    assert float(_state(hass, "sensor.qt2_3_0002_voltage_l1_l2")) == 419
    assert float(_state(hass, "sensor.qt2_3_0002_dc4_voltage")) == pytest.approx(40.5)

    from homeassistant.helpers import device_registry as dr
    dev = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, "9015000X0002"), entry.entry_id)
    assert dev.name == "QT2-3 (0002)" and dev.serial_number == "9015000X0002"

    reg = er.async_get(hass)
    # DC points of model 103 are unimplemented on the ECU: no entity at all
    assert reg.async_get("sensor.qt2_3_0001_dc_power") is None
    # Phase-to-neutral voltages exist but are disabled by default
    ent = reg.async_get("sensor.qt2_3_0001_voltage_l1_n")
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
    assert float(_state(hass, "sensor.ds3_l_0001_voltage")) == 230.1
    reg = er.async_get(hass)
    assert reg.async_get("sensor.ds3_l_0001_current_l2") is None
    assert reg.async_get("sensor.ds3_l_0001_dc3_voltage") is None
    assert reg.async_get("sensor.ds3_l_0001_dc2_power") is not None


async def test_without_dc_block(hass: HomeAssistant, ecu_factory):
    _, port = await ecu_factory({1: build_unit("9015000X0001", with_dc_block=False)})
    _, summary = await _setup(hass, port, last_unit=2)
    assert summary["dc"] == "0"
    reg = er.async_get(hass)
    assert reg.async_get("sensor.qt2_3_0001_dc_power_total") is None
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
    assert hass.states.get("sensor.qt2_3_0002_power") is None

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
    assert hass.states.get("sensor.qt2_3_0002_power") is not None


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
    assert float(_state(hass, "sensor.qt2_3_0001_power")) == 2100
    assert entry.runtime_data.split_reads == {1}


async def test_uses_shared_connection(hass: HomeAssistant, ecu_factory):
    """The entry holds its units on the modbus integration's shared link, the
    scan's temporary hold is gone, and unloading closes the link."""
    from homeassistant.components.modbus.connection import async_get_connection_info

    ecu, port = await ecu_factory({
        1: build_unit("9015000X0001"),
        2: build_unit("9015000X0002"),
    })
    entry, _ = await _setup(hass, port)
    info = async_get_connection_info(hass)
    assert len(info) == 1
    assert info[0].endpoint == ("tcp", "127.0.0.1", port)
    assert info[0].units == {entry.entry_id: [1, 2]}

    # A second scan while the entry is loaded rides on the same link. It gets
    # as far as reading the serials, which is how it knows the ECU is known.
    r = await _start(hass, port, 2)
    assert r["type"] is FlowResultType.ABORT and r["reason"] == "already_configured", r
    assert len(async_get_connection_info(hass)) == 1

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert async_get_connection_info(hass) == []


async def test_frozen_data_counts_as_asleep(hass: HomeAssistant, ecu_factory):
    """At dusk the ECU keeps serving the last values of the inverters. Data
    that stops changing is shown as asleep, per inverter, until it moves."""
    ecu, port = await ecu_factory({
        1: build_unit("9015000X0001", power_w=2100),
        2: build_unit("9015000X0002", power_w=1900),
    })
    entry, _ = await _setup(hass, port)
    coordinator = entry.runtime_data
    assert _state(hass, "sensor.apsystems_ecu_inverters_online") == "2"
    assert _state(hass, "sensor.qt2_3_0001_last_data_update") not in ("unknown", "unavailable")

    # Nothing changes from now on, and the limit is 0 s: both fall asleep.
    coordinator.stale_after = 0
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "sensor.apsystems_ecu_inverters_online") == "0"
    assert _state(hass, "sensor.apsystems_ecu_inverters_producing") == "0"
    assert float(_state(hass, "sensor.apsystems_ecu_power")) == 0
    assert float(_state(hass, "sensor.apsystems_ecu_dc_power_total")) == 0
    assert float(_state(hass, "sensor.apsystems_ecu_energy")) == pytest.approx(2 * 2.114)
    assert _state(hass, "sensor.qt2_3_0001_operating_state") == "sleeping"
    assert float(_state(hass, "sensor.qt2_3_0001_power")) == 0
    assert _state(hass, "sensor.qt2_3_0001_voltage_l1_l2") == "unknown"
    assert _state(hass, "sensor.qt2_3_0001_frequency") == "unknown"
    # The controls stay usable and keep their real value.
    assert float(_state(hass, "number.apsystems_ecu_power_limit")) == 100

    # Writing a limit does not wake anything up.
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": "number.apsystems_ecu_power_limit", "value": 80}, blocking=True)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "sensor.apsystems_ecu_inverters_online") == "0"

    # Morning: the ECU brings new data for inverter 2 only.
    ecu.set(2, 40086, ecu.reg(2, 40086) + 1)  # frequency moves
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert _state(hass, "sensor.apsystems_ecu_inverters_online") == "1"
    assert _state(hass, "sensor.apsystems_ecu_inverters_producing") == "1"
    assert float(_state(hass, "sensor.apsystems_ecu_power")) == 1900
    assert _state(hass, "sensor.qt2_3_0002_operating_state") == "mppt"
    assert _state(hass, "sensor.qt2_3_0001_operating_state") == "sleeping"

    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_no_deprecated_ha_usage(hass: HomeAssistant, ecu_factory, caplog):
    """No update listener (options reload through OptionsFlowWithReload,
    reconfigure through async_update_reload_and_abort) and inverter devices
    linked to the ECU device by id (via_device is removed in 2027.8)."""
    from homeassistant.helpers import device_registry as dr

    ecu, port = await ecu_factory({1: build_unit("9015000X0001"), 2: build_unit("9015000X0002")})
    entry, _ = await _setup(hass, port, last_unit=2)
    assert not entry.update_listeners

    reg = dr.async_get(hass)
    parent = reg.async_get_device_by_identifier((DOMAIN, entry.unique_id), entry.entry_id)
    child = reg.async_get_device_by_identifier((DOMAIN, "9015000X0002"), entry.entry_id)
    assert parent is not None and child is not None and child.via_device_id == parent.id

    # Options: a changed value reloads the entry, which picks it up.
    r = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.options.async_configure(
        r["flow_id"], {"scan_interval": 20.0, "limit_keepalive": 0.0})
    await hass.async_block_till_done()
    assert entry.runtime_data.update_interval.total_seconds() == 20

    # Reconfigure on the same ECU: reloads without the update listener warning.
    r = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id})
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"], {"host": "127.0.0.1", "port": port, "last_unit": 2})
    assert r["reason"] == "reconfigure_successful"
    await hass.async_block_till_done()

    assert "update listener" not in caplog.text
    assert "via_device" not in caplog.text
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_ecu_id_names_the_ecu(hass: HomeAssistant, ecu_factory):
    """The ECU is invisible over Modbus: an ECU ID typed at setup gives the
    entry and the ECU device their name, model and serial number."""
    from homeassistant.helpers import device_registry as dr

    _, port = await ecu_factory({1: build_unit("9015000X0001")})
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"], {"host": "127.0.0.1", "port": port, "last_unit": 2, "ecu_id": "2150 0000 1234"})
    r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
    await hass.async_block_till_done()
    entry = r["result"]
    assert entry.title == "ECU-C (1234)" and entry.data["ecu_id"] == "215000001234"
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, entry.unique_id), entry.entry_id)
    assert device.name == "ECU-C (1234)" and device.model == "ECU-C"
    assert device.serial_number == "215000001234"
    assert hass.states.get("sensor.ecu_c_1234_power") is not None
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_ecu_id_is_checked(hass: HomeAssistant, ecu_factory):
    _, port = await ecu_factory({1: build_unit("9015000X0001")})
    r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    r = await hass.config_entries.flow.async_configure(
        r["flow_id"], {"host": "127.0.0.1", "port": port, "last_unit": 2, "ecu_id": "2150001234"})
    assert r["type"] is FlowResultType.FORM and r["errors"] == {"ecu_id": "invalid_ecu_id"}


async def test_ecu_id_added_later(hass: HomeAssistant, ecu_factory):
    """Reconfigure can add the ID to an existing entry: the default title
    follows it, a title the user chose stays. Entity ids do not change."""
    from homeassistant.helpers import device_registry as dr

    _, port = await ecu_factory({1: build_unit("9015000X0001")})
    entry, _ = await _setup(hass, port, last_unit=2)
    assert entry.title == "APsystems ECU"

    async def reconfigure(ecu_id):
        r = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_RECONFIGURE, "entry_id": entry.entry_id})
        r = await hass.config_entries.flow.async_configure(
            r["flow_id"], {"host": "127.0.0.1", "port": port, "last_unit": 2, "ecu_id": ecu_id})
        assert r["reason"] == "reconfigure_successful"
        await hass.async_block_till_done()

    await reconfigure("216200005678")
    assert entry.title == "ECU-R Pro (5678)"
    device = dr.async_get(hass).async_get_device_by_identifier((DOMAIN, entry.unique_id), entry.entry_id)
    assert device.name == "ECU-R Pro (5678)" and device.serial_number == "216200005678"
    assert hass.states.get("sensor.apsystems_ecu_power") is not None  # same entity ids

    hass.config_entries.async_update_entry(entry, title="ECU garage")
    await reconfigure("215000001234")
    assert entry.title == "ECU garage"
    assert await hass.config_entries.async_unload(entry.entry_id)


async def test_two_ecus(hass: HomeAssistant, ecu_factory):
    """Two ECUs: one entry and one Modbus link each, and with their IDs typed
    in, the ECU devices and their entities can be told apart."""
    from homeassistant.components.modbus.connection import async_get_connection_info

    _, p1 = await ecu_factory({1: build_unit("9015000A0001")})
    _, p2 = await ecu_factory({1: build_unit("9015000B0001")})
    entries = []
    for port, ecu_id in ((p1, "215000001111"), (p2, "216000002222")):
        r = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
        r = await hass.config_entries.flow.async_configure(
            r["flow_id"], {"host": "127.0.0.1", "port": port, "last_unit": 1, "ecu_id": ecu_id})
        r = await hass.config_entries.flow.async_configure(r["flow_id"], {})
        await hass.async_block_till_done()
        entries.append(r["result"])
    assert len({e.unique_id for e in entries}) == 2
    assert len(async_get_connection_info(hass)) == 2
    assert hass.states.get("sensor.ecu_c_1111_power") is not None
    assert hass.states.get("sensor.ecu_r_2222_power") is not None
    for e in entries:
        assert await hass.config_entries.async_unload(e.entry_id)
