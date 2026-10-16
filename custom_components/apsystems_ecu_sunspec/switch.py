"""Global switches of model 123: inverters on/off (Conn) and limit enable."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import UpdateFailed

from . import EcuConfigEntry
from .const import CONF_CONTROLS
from .entity import EcuEntity

SWITCHES = (
    # Conn = 0 stops every inverter of the ECU, not just one.
    SwitchEntityDescription(key="conn", name="Production", icon="mdi:solar-power"),
    # While 0, a written limit is stored, echoed back and ignored.
    SwitchEntityDescription(key="limit_enabled", name="Power limit enabled", icon="mdi:tune"),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: EcuConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    controls = entry.data.get(CONF_CONTROLS, {})
    c = entry.runtime_data
    async_add_entities(EcuSwitch(c, d) for d in SWITCHES if controls.get(d.key))


class EcuSwitch(EcuEntity, SwitchEntity):
    def __init__(self, coordinator, description: SwitchEntityDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def is_on(self) -> bool | None:
        v = self.values.get(self._key)
        return None if v is None else v == 1

    async def _set(self, on: bool) -> None:
        setter = (
            self.coordinator.async_set_conn if self._key == "conn"
            else self.coordinator.async_set_limit_enabled
        )
        try:
            await setter(on)
        except UpdateFailed as err:
            raise HomeAssistantError(str(err)) from err

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)
