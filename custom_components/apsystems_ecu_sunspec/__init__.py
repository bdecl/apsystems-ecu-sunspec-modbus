"""APsystems ECU over its own SunSpec Modbus TCP server."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DEFAULT_SCAN_INTERVAL, PLATFORMS, READ_TIMEOUT
from .coordinator import EcuCoordinator
from .entity import ecu_device
from .hub import EcuHub

type EcuConfigEntry = ConfigEntry[EcuCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EcuConfigEntry) -> bool:
    # Units are released by the modbus integration when the entry unloads.
    hub = EcuHub.for_entry(
        hass, entry, entry.data[CONF_HOST], entry.data[CONF_PORT], READ_TIMEOUT
    )
    scan = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = EcuCoordinator(hass, entry, hub, scan)
    await coordinator.async_config_entry_first_refresh()
    # The ECU device first: the inverter devices name it as their parent by id.
    coordinator.ecu_device_id = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **ecu_device(coordinator)
    ).id
    entry.runtime_data = coordinator
    coordinator.start_keepalive()
    # Options changes reload through OptionsFlowWithReload, reconfigure through
    # async_update_reload_and_abort: no update listener.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EcuConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        entry.runtime_data.stop_keepalive()
    return ok
