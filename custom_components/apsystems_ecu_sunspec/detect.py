"""Auto-detection: which units answer, which models each one serves.

Runs once in the config flow (and again on reconfigure). The result is stored
in the config entry so that setup does not rescan the ECU on every restart.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import logging

from homeassistant.core import HomeAssistant

from .hub import EcuHub, HubConnectError, HubError, IllegalAddress
from .models import (
    ADAPTER_MODELS,
    BASE,
    DC_CHANNELS,
    DC_HEADER,
    DC_LENGTH,
    DC_MODEL,
    END_MARKER,
    FLOAT_MODELS,
    INT_MODELS,
    MODEL_COMMON,
    MODEL_CONTROLS,
    SUNS,
    ModelRef,
    UnitLayout,
    channels_for,
    decode_common,
    decode_controls,
    f32,
)

_LOGGER = logging.getLogger(__name__)

SCAN_TIMEOUT = 1.5  # s, a missing unit is silent, not an error
MAX_MISSES = 3  # consecutive silent units that end the scan
CHAIN_LIMIT = 2000


class NotSunSpec(Exception):
    """Something answered but it is not a SunSpec device."""


@dataclass
class Detection:
    units: list[UnitLayout] = field(default_factory=list)
    adapter: bool = False  # bolkedebruin/apsystems-sunspec, not the ECU's own server
    control_unit: int | None = None
    controls: dict[str, bool] = field(default_factory=dict)

    @property
    def phases(self) -> set[int]:
        return {u.phases for u in self.units}

    @property
    def models(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for u in self.units:
            out[u.model] = out.get(u.model, 0) + 1
        return out


async def _walk(hub: EcuHub, unit: int) -> list[ModelRef]:
    refs: list[ModelRef] = []
    ptr = BASE + 2
    while ptr < BASE + CHAIN_LIMIT:
        model_id, length = await hub.read(unit, ptr, 2)
        if model_id == END_MARKER:
            return refs
        refs.append(ModelRef(model_id, ptr, length))
        ptr += length + 2
    raise NotSunSpec(f"unit {unit}: chain longer than {CHAIN_LIMIT} registers")


async def _dc_channels(hub: EcuHub, unit: int, model: str) -> int:
    try:
        header = await hub.read(unit, DC_HEADER, 2)
    except (HubError, IllegalAddress):
        return 0
    if header != [DC_MODEL, DC_LENGTH]:
        return 0
    known = channels_for(model)
    if known:
        return known
    # Unknown family: count channels that report a voltage, at least 2.
    words = await hub.read(unit, DC_HEADER + 2, 2 * DC_CHANNELS)
    live = [
        ch for ch in range(DC_CHANNELS)
        if (f32(words[2 * ch], words[2 * ch + 1]) or 0) > 0
    ]
    return max(2, (live[-1] + 1) if live else 4)


async def _identify(hub: EcuHub, unit: int) -> tuple[UnitLayout, list[int]]:
    refs = await _walk(hub, unit)
    ids = [r.model_id for r in refs]
    common = next((r for r in refs if r.model_id == MODEL_COMMON), None)
    if common is None:
        raise NotSunSpec(f"unit {unit}: no common model")
    info = decode_common(await hub.read(unit, common.start, common.length))
    int_model = next((r for r in refs if r.model_id in INT_MODELS), None)
    float_model = next((r for r in refs if r.model_id in FLOAT_MODELS), None)
    phases = (
        INT_MODELS[int_model.model_id] if int_model
        else FLOAT_MODELS[float_model.model_id] if float_model
        else 0
    )
    layout = UnitLayout(
        unit=unit,
        serial=info["serial"],
        model=info["model"] or "unknown",
        version=info["version"],
        phases=phases,
        int_model=int_model,
        float_model=float_model,
        controls=next((r for r in refs if r.model_id == MODEL_CONTROLS), None),
        others=[i for i in ids if i not in (MODEL_COMMON, MODEL_CONTROLS)
                and i not in INT_MODELS and i not in FLOAT_MODELS],
    )
    layout.dc_channels = await _dc_channels(hub, unit, layout.model)
    return layout, ids


async def detect(
    hass: HomeAssistant, host: str, port: int, last_unit: int, timeout: float = SCAN_TIMEOUT
) -> Detection:
    """Scan units 1..last_unit. Raises HubConnectError if nothing listens."""
    result = Detection()
    async with EcuHub.temporary(hass, host, port, timeout) as hub:
        misses = 0
        for unit in range(1, last_unit + 1):
            try:
                marker = await hub.read(unit, BASE, 2)
            except HubConnectError:
                raise
            except (HubError, IllegalAddress) as err:
                if not hub.connected:
                    # The link itself never came up: nothing listens there.
                    raise HubConnectError(str(err)) from err
                misses += 1
                if result.units and misses >= MAX_MISSES:
                    break
                continue
            misses = 0
            if tuple(marker) != SUNS:
                _LOGGER.debug("Unit %s answers but has no SunS marker", unit)
                continue
            try:
                layout, ids = await _identify(hub, unit)
            except HubConnectError:
                raise
            except (HubError, IllegalAddress, NotSunSpec) as err:
                _LOGGER.warning("Unit %s skipped: %s", unit, err)
                continue
            if ADAPTER_MODELS.intersection(ids):
                result.adapter = True
            if layout.phases:
                result.units.append(layout)

        for layout in result.units:
            if layout.controls is None:
                continue
            try:
                c = decode_controls(
                    await hub.read(layout.unit, layout.controls.start, layout.controls.length)
                )
            except (HubError, IllegalAddress):
                continue
            result.control_unit = layout.unit
            result.controls = {
                "conn": c["conn"] is not None,
                "limit_pct": c["limit_pct"] is not None,
                "limit_enabled": c["limit_enabled"] is not None,
            }
            break
    return result
