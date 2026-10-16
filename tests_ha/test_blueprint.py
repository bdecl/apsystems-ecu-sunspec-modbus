"""The zero export blueprint, run as a real automation against the simulated ECU."""
import pathlib
import shutil

import pytest

from ecu_image import build_unit
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from test_integration import _setup, ecu_factory  # noqa: F401  (fixture)

SRC = (pathlib.Path(__file__).parents[1] / "blueprints" / "automation"
       / "apsystems_ecu_sunspec" / "zero_export.yaml")
RATED = 18000


@pytest.fixture
def blueprint(hass: HomeAssistant):
    dest = pathlib.Path(hass.config.path("blueprints/automation/apsystems_ecu_sunspec"))
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(SRC, dest / "zero_export.yaml")
    yield "apsystems_ecu_sunspec/zero_export.yaml"
    shutil.rmtree(dest)


async def _automation(hass, path, **extra):
    inputs = {
        "grid_power": "sensor.grid",
        "power_limit": "number.apsystems_ecu_power_limit",
        "array_power": RATED,
        **extra,
    }
    assert await async_setup_component(hass, "automation", {
        "automation": [{"id": "zx", "alias": "zx", "use_blueprint": {"path": path, "input": inputs}}]
    })
    await hass.async_block_till_done()


async def _run(hass):
    await hass.services.async_call(
        "automation", "trigger", {"entity_id": "automation.zx", "skip_condition": False},
        blocking=True)
    await hass.async_block_till_done()


def _limit(hass):
    return float(hass.states.get("number.apsystems_ecu_power_limit").state)


async def test_cuts_when_exporting(hass: HomeAssistant, ecu_factory, blueprint):  # noqa: F811
    ecu, port = await ecu_factory({1: build_unit("9015000X0001")})
    await _setup(hass, port, last_unit=2)
    hass.states.async_set("sensor.grid", "-2000", {"device_class": "power", "unit_of_measurement": "W"})
    await _automation(hass, blueprint)
    await _run(hass)
    # excess = 50 - (-2000) = 2050 W = 11.39 % of 18 kW, times 0.8
    assert _limit(hass) == pytest.approx(90.9)
    assert ecu.reg(1, 40189) == 909


async def test_releases_gently_and_respects_sign(hass: HomeAssistant, ecu_factory, blueprint):  # noqa: F811
    ecu, port = await ecu_factory({1: build_unit("9015000X0001", limit_raw=400)})
    await _setup(hass, port, last_unit=2)
    # Sensor positive when exporting: 1000 W import is reported as -1000.
    hass.states.async_set("sensor.grid", "-1000", {"device_class": "power", "unit_of_measurement": "W"})
    await _automation(hass, blueprint, import_positive=False)
    await _run(hass)
    # excess = 50 - 1000 = -950 W = -5.28 %, times 0.15 -> +0.8 %
    assert _limit(hass) == pytest.approx(40.8)


async def test_disabled_restores_full_output(hass: HomeAssistant, ecu_factory, blueprint):  # noqa: F811
    ecu, port = await ecu_factory({1: build_unit("9015000X0001", limit_raw=300)})
    await _setup(hass, port, last_unit=2)
    hass.states.async_set("sensor.grid", "-2000", {"device_class": "power", "unit_of_measurement": "W"})
    hass.states.async_set("input_boolean.allow", "off")
    await _automation(hass, blueprint, enable_entity="input_boolean.allow")
    await _run(hass)
    assert _limit(hass) == 100
    assert ecu.reg(1, 40189) == 1000


async def test_holds_when_grid_unavailable(hass: HomeAssistant, ecu_factory, blueprint):  # noqa: F811
    ecu, port = await ecu_factory({1: build_unit("9015000X0001", limit_raw=500)})
    await _setup(hass, port, last_unit=2)
    hass.states.async_set("sensor.grid", "unavailable")
    await _automation(hass, blueprint)
    await _run(hass)
    assert _limit(hass) == 50
