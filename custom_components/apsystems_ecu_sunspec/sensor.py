"""Sensors: per inverter (models 10x/11x, DC block 114) and array totals.

Only points the firmware actually implements become entities: anything that
reads as a SunSpec "not implemented" sentinel at setup is skipped.
"""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfApparentPower,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfReactivePower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import EcuConfigEntry
from .coordinator import EcuCoordinator
from .entity import EcuEntity, InverterEntity
from .models import OPERATING_STATES, UnitLayout, active_events

MEAS = SensorStateClass.MEASUREMENT
DIAG = EntityCategory.DIAGNOSTIC


@dataclass(frozen=True, kw_only=True)
class EcuSensorDescription(SensorEntityDescription):
    always: bool = False  # create even if the value is missing at setup


def _w(key, name, **kw):
    return EcuSensorDescription(
        key=key, name=name, device_class=SensorDeviceClass.POWER, state_class=MEAS,
        native_unit_of_measurement=UnitOfPower.WATT, suggested_display_precision=0, **kw)


def _a(key, name, **kw):
    return EcuSensorDescription(
        key=key, name=name, device_class=SensorDeviceClass.CURRENT, state_class=MEAS,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE, suggested_display_precision=2, **kw)


def _v(key, name, **kw):
    return EcuSensorDescription(
        key=key, name=name, device_class=SensorDeviceClass.VOLTAGE, state_class=MEAS,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT, suggested_display_precision=1, **kw)


def _wh(key, name, **kw):
    return EcuSensorDescription(
        key=key, name=name, device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2, **kw)


COMMON = (
    _w("power", "Power", always=True),
    _a("current", "Current"),
    EcuSensorDescription(
        key="frequency", name="Frequency", device_class=SensorDeviceClass.FREQUENCY,
        state_class=MEAS, native_unit_of_measurement=UnitOfFrequency.HERTZ,
        suggested_display_precision=2),
    _wh("energy", "Energy"),
    EcuSensorDescription(
        key="temperature", name="Temperature", device_class=SensorDeviceClass.TEMPERATURE,
        state_class=MEAS, native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1),
    EcuSensorDescription(
        key="apparent_power", name="Apparent power", device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=MEAS, native_unit_of_measurement=UnitOfApparentPower.VOLT_AMPERE,
        entity_registry_enabled_default=False),
    EcuSensorDescription(
        key="reactive_power", name="Reactive power", device_class=SensorDeviceClass.REACTIVE_POWER,
        state_class=MEAS, native_unit_of_measurement=UnitOfReactivePower.VOLT_AMPERE_REACTIVE,
        entity_registry_enabled_default=False),
    EcuSensorDescription(
        key="power_factor", name="Power factor", device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=MEAS, suggested_display_precision=3, entity_registry_enabled_default=False),
    EcuSensorDescription(
        key="state", name="Operating state", device_class=SensorDeviceClass.ENUM,
        options=list(OPERATING_STATES.values()), translation_key="operating_state"),
    EcuSensorDescription(key="events", name="Events", entity_category=DIAG),
    # When the ECU last brought new measurements for this inverter: it goes on
    # serving the old ones once the inverter sleeps.
    EcuSensorDescription(
        key="last_update", name="Last data update", device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=DIAG, always=True),
    # DC points of the inverter model itself: unimplemented on the ECU-C, kept
    # for firmwares that do fill them (skipped automatically otherwise).
    _w("dc_power", "DC power"),
    _v("dc_voltage", "DC voltage"),
    _a("dc_current", "DC current"),
)

PHASE_SETS = {
    1: (_v("voltage_a", "Voltage"),),
    2: (
        _a("current_a", "Current L1"), _a("current_b", "Current L2"),
        _v("voltage_a", "Voltage L1"), _v("voltage_b", "Voltage L2"),
        _v("voltage_ab", "Voltage L1-L2"),
    ),
    3: (
        _a("current_a", "Current L1"), _a("current_b", "Current L2"), _a("current_c", "Current L3"),
        _v("voltage_ab", "Voltage L1-L2"), _v("voltage_bc", "Voltage L2-L3"),
        _v("voltage_ca", "Voltage L3-L1"),
        # Read 0 at night on the ECU-C; whether they ever carry a value is open.
        _v("voltage_a", "Voltage L1-N", entity_registry_enabled_default=False),
        _v("voltage_b", "Voltage L2-N", entity_registry_enabled_default=False),
        _v("voltage_c", "Voltage L3-N", entity_registry_enabled_default=False),
    ),
}


def dc_descriptions(channels: int) -> list[EcuSensorDescription]:
    out = [_w("dc_power_total", "DC power total", always=True)]
    for ch in range(1, channels + 1):
        out += [
            _w(f"dc{ch}_power", f"DC{ch} power", always=True),
            _v(f"dc{ch}_voltage", f"DC{ch} voltage", always=True),
            _a(f"dc{ch}_current", f"DC{ch} current", always=True),
        ]
    return out


ECU_SENSORS = (
    _w("power", "Power", always=True),
    _wh("energy", "Energy", always=True),
    EcuSensorDescription(
        key="inverters_producing", name="Inverters producing", state_class=MEAS, always=True),
    EcuSensorDescription(
        key="inverters_online", name="Inverters online", state_class=MEAS,
        entity_category=DIAG, always=True),
    EcuSensorDescription(key="events", name="Events", entity_category=DIAG, always=True),
)


def inverter_descriptions(layout: UnitLayout) -> list[EcuSensorDescription]:
    out = [*COMMON, *PHASE_SETS.get(layout.phases, ())]
    if layout.dc_channels:
        out += dc_descriptions(layout.dc_channels)
    return out


async def async_setup_entry(
    hass: HomeAssistant, entry: EcuConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    c: EcuCoordinator = entry.runtime_data
    entities: list[SensorEntity] = [EcuSensor(c, d) for d in ECU_SENSORS]
    if any(u.dc_channels for u in c.units):
        entities.append(EcuSensor(c, _w("dc_power_total", "DC power total", always=True)))
    for layout in c.units:
        first = (c.data or {}).get("units", {}).get(layout.unit) or {}
        for d in inverter_descriptions(layout):
            if d.always or first.get(d.key) is not None:
                entities.append(InverterSensor(c, layout, d))
    async_add_entities(entities)


def _events_state(bits) -> str | None:
    if bits is None:
        return None
    names = active_events(bits)
    return ", ".join(names) if names else "none"


class EcuSensor(EcuEntity, SensorEntity):
    entity_description: EcuSensorDescription

    def __init__(self, coordinator, description: EcuSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        v = self.values.get(self._key)
        if self._key == "events":
            return ", ".join(v) if v else "none"
        return v


class InverterSensor(InverterEntity, SensorEntity):
    entity_description: EcuSensorDescription

    def __init__(self, coordinator, layout, description: EcuSensorDescription) -> None:
        super().__init__(coordinator, layout, description.key)
        self.entity_description = description

    @property
    def native_value(self):
        v = (self.values or {}).get(self._key)
        if self._key == "state":
            return OPERATING_STATES.get(v) if v is not None else None
        if self._key == "events":
            return _events_state(v)
        return v

    @property
    def extra_state_attributes(self):
        if self._key == "events":
            v = (self.values or {}).get("events")
            return {"raw": None if v is None else f"0x{v:08X}"}
        return None
