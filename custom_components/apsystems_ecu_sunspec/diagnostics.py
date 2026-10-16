"""Diagnostics: detected layout and decoded values, identifiers redacted."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import EcuConfigEntry

REDACT = {CONF_HOST, "serial", "unique_id", "title"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EcuConfigEntry
) -> dict[str, Any]:
    c = entry.runtime_data
    return {
        "entry": async_redact_data(entry.as_dict(), REDACT),
        "split_reads": sorted(c.split_reads),
        "values": c.data,
    }
