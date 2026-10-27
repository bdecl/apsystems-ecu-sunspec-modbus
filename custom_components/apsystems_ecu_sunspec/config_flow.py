"""Config flow: host, then automatic detection of inverters, topology,
DC block and controls, shown for confirmation before the entry is created."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector

from .const import (
    CONF_CONTROL_UNIT,
    CONF_CONTROLS,
    CONF_ECU_ID,
    CONF_KEEPALIVE,
    CONF_LAST_UNIT,
    CONF_UNITS,
    DEFAULT_KEEPALIVE,
    DEFAULT_LAST_UNIT,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MIN_SCAN_INTERVAL,
)
from .detect import Detection, detect
from .models import DEFAULT_ECU_TITLE, clean_ecu_id, ecu_title
from .hub import HubError

CONTROL_NAMES = {"conn": "Conn", "limit_pct": "WMaxLimPct", "limit_enabled": "WMaxLim_Ena"}


def _box(minimum: int, maximum: int, unit: str | None = None) -> selector.NumberSelector:
    """Plain numeric input box (an int range would render as a slider)."""
    config = selector.NumberSelectorConfig(
        min=minimum, max=maximum, step=1, mode=selector.NumberSelectorMode.BOX
    )
    if unit:
        config["unit_of_measurement"] = unit
    return selector.NumberSelector(config)


def _host_schema(defaults: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, "")): str,
            vol.Required(CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)): _box(1, 65535),
            vol.Required(
                CONF_LAST_UNIT, default=defaults.get(CONF_LAST_UNIT, DEFAULT_LAST_UNIT)
            ): _box(1, 247),
            # Optional: the ECU is invisible over Modbus, so its ID can only be
            # typed in. It names the ECU device and gives its model.
            vol.Optional(
                CONF_ECU_ID, description={"suggested_value": defaults.get(CONF_ECU_ID) or ""}
            ): str,
        }
    )


async def _run_detection(
    hass: HomeAssistant, user_input: dict[str, Any]
) -> tuple[Detection | None, str | None]:
    try:
        found = await detect(
            hass, user_input[CONF_HOST], user_input[CONF_PORT], user_input[CONF_LAST_UNIT]
        )
    except HubError:
        return None, "cannot_connect"
    if found.adapter:
        return None, "adapter_unsupported"
    if not found.units:
        return None, "no_inverters"
    return found, None


def _entry_data(user_input: dict[str, Any], found: Detection) -> dict[str, Any]:
    return {
        CONF_HOST: user_input[CONF_HOST],
        CONF_PORT: user_input[CONF_PORT],
        CONF_LAST_UNIT: user_input[CONF_LAST_UNIT],
        CONF_UNITS: [u.as_dict() for u in found.units],
        CONF_CONTROL_UNIT: found.control_unit,
        CONF_CONTROLS: found.controls,
        CONF_ECU_ID: user_input.get(CONF_ECU_ID),
    }


def _summary(found: Detection) -> dict[str, str]:
    dc = sorted({u.dc_channels for u in found.units})
    working = [CONTROL_NAMES[k] for k, ok in found.controls.items() if ok]
    return {
        "count": str(len(found.units)),
        "units": ", ".join(str(u.unit) for u in found.units),
        "models": ", ".join(f"{n} × {m}" for m, n in sorted(found.models.items())),
        "phases": " / ".join(str(p) for p in sorted(found.phases)),
        "dc": " / ".join(str(c) for c in dc),
        "controls": ", ".join(working) or "—",
        "control_unit": str(found.control_unit or "—"),
    }


def _normalise(user_input: dict[str, Any]) -> dict[str, Any]:
    """Numbers as ints, the ECU ID cleaned. Raises ValueError for a bad ID."""
    user_input[CONF_PORT] = int(user_input[CONF_PORT])
    user_input[CONF_LAST_UNIT] = int(user_input[CONF_LAST_UNIT])
    user_input[CONF_ECU_ID] = clean_ecu_id(user_input.get(CONF_ECU_ID))
    return user_input


class EcuConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._input: dict[str, Any] = {}
        self._found: Detection | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                user_input = _normalise(user_input)
            except ValueError:
                errors[CONF_ECU_ID] = "invalid_ecu_id"
            else:
                found, error = await _run_detection(self.hass, user_input)
                if error:
                    errors["base"] = error
                else:
                    # The lowest inverter serial stays the identity of the
                    # installation: the ECU ID is optional and typed by hand.
                    await self.async_set_unique_id(f"ecu_{min(u.serial for u in found.units)}")
                    self._abort_if_unique_id_configured(
                        updates={CONF_HOST: user_input[CONF_HOST]}
                    )
                    self._input, self._found = user_input, found
                    return await self.async_step_confirm()
        return self.async_show_form(
            step_id="user", data_schema=_host_schema(user_input or {}), errors=errors
        )

    async def async_step_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._found is not None
        if user_input is not None:
            return self.async_create_entry(
                title=ecu_title(self._input.get(CONF_ECU_ID)),
                data=_entry_data(self._input, self._found),
            )
        return self.async_show_form(
            step_id="confirm", description_placeholders=_summary(self._found)
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Run the detection again, e.g. after adding inverters in EMA."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                user_input = _normalise(user_input)
            except ValueError:
                errors[CONF_ECU_ID] = "invalid_ecu_id"
            else:
                found, error = await _run_detection(self.hass, user_input)
                if error:
                    errors["base"] = error
                else:
                    # Keep a name the user chose; follow the ECU ID otherwise.
                    auto = {DEFAULT_ECU_TITLE, ecu_title(entry.data.get(CONF_ECU_ID))}
                    title = (
                        ecu_title(user_input[CONF_ECU_ID]) if entry.title in auto else entry.title
                    )
                    return self.async_update_reload_and_abort(
                        entry, title=title, data=_entry_data(user_input, found)
                    )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_host_schema(user_input or dict(entry.data)),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return EcuOptionsFlow()


class EcuOptionsFlow(OptionsFlowWithReload):
    """Scan interval and limit keepalive; the entry reloads when they change."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data={k: int(v) for k, v in user_input.items()})
        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL, default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ): _box(MIN_SCAN_INTERVAL, 300, "s"),
                vol.Required(
                    CONF_KEEPALIVE, default=opts.get(CONF_KEEPALIVE, DEFAULT_KEEPALIVE)
                ): _box(0, 3600, "s"),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
