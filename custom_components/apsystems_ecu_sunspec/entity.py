"""Base entities: one device for the ECU (array level), one per inverter."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import CONF_ECU_ID, DOMAIN, ECU_DEVICE_NAME, MANUFACTURER
from .coordinator import EcuCoordinator
from .models import UnitLayout, ecu_model, inverter_name


def ecu_device(coordinator: EcuCoordinator) -> DeviceInfo:
    entry = coordinator.config_entry
    ecu_id = entry.data.get(CONF_ECU_ID)
    info = DeviceInfo(
        identifiers={(DOMAIN, entry.unique_id)},
        name=entry.title or ECU_DEVICE_NAME,
        manufacturer=MANUFACTURER,
        model=ecu_model(ecu_id) or "ECU (SunSpec Modbus)",
    )
    if ecu_id:
        info["serial_number"] = ecu_id
    return info


class EcuEntity(CoordinatorEntity[EcuCoordinator]):
    """Array-level entity: totals and the global controls of model 123."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EcuCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"{coordinator.config_entry.unique_id}_{key}"
        self._attr_device_info = ecu_device(coordinator)

    @property
    def values(self) -> dict[str, Any]:
        return (self.coordinator.data or {}).get("ecu", {})


class InverterEntity(CoordinatorEntity[EcuCoordinator]):
    """Per-inverter entity, attached to the ECU device."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: EcuCoordinator, layout: UnitLayout, key: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self.layout = layout
        self._attr_unique_id = f"{layout.serial}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, layout.serial)},
            name=inverter_name(layout, coordinator.units),
            manufacturer=MANUFACTURER,
            model=layout.model,
            serial_number=layout.serial,
            sw_version=layout.version or None,
            via_device_id=coordinator.ecu_device_id,
        )

    @property
    def values(self) -> dict[str, Any] | None:
        return (self.coordinator.data or {}).get("units", {}).get(self.layout.unit)

    @property
    def available(self) -> bool:
        return super().available and self.values is not None
