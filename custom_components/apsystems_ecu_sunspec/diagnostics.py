"""Diagnostics: detected layout, raw registers and decoded values.

Identifiers are redacted. The raw registers are the ones polled each cycle
(inverter models, controls, DC block): model 1, which holds the serial
number, is not among them. The first 4 characters of each inverter serial
stay visible because they tell the inverter family.
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from . import EcuConfigEntry

REDACT = {CONF_HOST, "serial", "unique_id", "title", "ecu_id", "serial_number"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: EcuConfigEntry
) -> dict[str, Any]:
    c = entry.runtime_data
    layouts = []
    for layout in c.units:
        d = layout.as_dict()
        d["serial_prefix"] = (layout.serial or "")[:4]
        layouts.append(d)
    return {
        "entry": async_redact_data(entry.as_dict(), REDACT),
        "control_unit": c.control_unit,
        "units": async_redact_data(layouts, REDACT),
        "split_reads": sorted(c.split_reads),
        "keepalive_limit": c.last_limit,
        "raw_registers": {
            unit: {str(addr): f"0x{word:04X}" for addr, word in sorted(words.items())}
            for unit, words in c.last_words.items()
        },
        "values": c.data,
    }
