"""APsystems ECU over its own SunSpec Modbus TCP server."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant

from .const import DEFAULT_SCAN_INTERVAL, PLATFORMS, READ_TIMEOUT
from .coordinator import EcuCoordinator
from .hub import EcuHub

type EcuConfigEntry = ConfigEntry[EcuCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EcuConfigEntry) -> bool:
    hub = EcuHub(entry.data[CONF_HOST], entry.data[CONF_PORT], timeout=READ_TIMEOUT)
    scan = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    coordinator = EcuCoordinator(hass, entry, hub, scan)
    try:
        await coordinator.async_config_entry_first_refresh()
    except Exception:
        await hub.close()
        raise
    entry.runtime_data = coordinator
    coordinator.start_keepalive()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: EcuConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: EcuConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        entry.runtime_data.stop_keepalive()
        await entry.runtime_data.hub.close()
    return ok
