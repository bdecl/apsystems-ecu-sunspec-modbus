"""Power limit (model 123 WMaxLimPct). Applies to the whole array.

The integration only exposes the device. Control loops belong in automations:
see the zero export blueprint in this repository.
"""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import UpdateFailed

from . import EcuConfigEntry
from .const import CONF_CONTROLS
from .entity import EcuEntity

LIMIT = NumberEntityDescription(
    key="limit_pct", name="Power limit", icon="mdi:solar-power-variant",
    native_unit_of_measurement=PERCENTAGE, native_min_value=0, native_max_value=100,
    native_step=0.1, mode=NumberMode.BOX,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: EcuConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.data.get(CONF_CONTROLS, {}).get("limit_pct"):
        async_add_entities([PowerLimit(entry.runtime_data, LIMIT)])


class PowerLimit(EcuEntity, NumberEntity):
    def __init__(self, coordinator, description: NumberEntityDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        return self.values.get("limit_pct")

    async def async_set_native_value(self, value: float) -> None:
        try:
            await self.coordinator.async_set_limit(value)
        except UpdateFailed as err:
            raise HomeAssistantError(str(err)) from err
