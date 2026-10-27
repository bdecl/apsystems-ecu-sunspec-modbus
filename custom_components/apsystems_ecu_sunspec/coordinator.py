"""Polling coordinator: every detected unit per cycle, controls on one unit."""
from __future__ import annotations

from datetime import datetime, timedelta
import logging
from time import monotonic
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CONTROL_UNIT,
    CONF_KEEPALIVE,
    CONF_UNITS,
    DEFAULT_KEEPALIVE,
    DOMAIN,
    STALE_AFTER,
)
from .hub import EcuHub, HubError, IllegalAddress
from .models import UnitLayout, active_events, asleep, decode_unit, measurement_fingerprint

_LOGGER = logging.getLogger(__name__)

# Offsets inside model 123
OFF_CONN, OFF_LIMIT, OFF_LIMIT_ENA = 2, 3, 7


class EcuCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, hub: EcuHub, scan: int) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN,
            update_interval=timedelta(seconds=scan),
        )
        self.hub = hub
        self.units = [UnitLayout.from_dict(u) for u in entry.data[CONF_UNITS]]
        self.control_unit: int | None = entry.data.get(CONF_CONTROL_UNIT)
        self.last_limit: float | None = None
        self._unsub_keepalive = None
        # Units on which long merged reads failed: polled one model per read.
        self.split_reads: set[int] = set()
        # Per unit: last measurement registers, when they last changed (monotonic
        # clock, for the decision) and the same moment as a date (shown).
        self._fingerprints: dict[int, tuple[int, ...]] = {}
        self._changed_mono: dict[int, float] = {}
        self._changed_at: dict[int, datetime] = {}
        self.stale_after = STALE_AFTER
        self.ecu_device_id: str | None = None  # set by async_setup_entry

    @property
    def control_layout(self) -> UnitLayout | None:
        return next((u for u in self.units if u.unit == self.control_unit), None)

    async def _async_update_data(self) -> dict[str, Any]:
        units: dict[int, dict | None] = {}
        errors: list[str] = []
        for layout in self.units:
            ctrl = layout.unit == self.control_unit
            try:
                words = await self._read_unit(layout, ctrl)
            except (HubError, IllegalAddress) as err:
                errors.append(str(err))
                units[layout.unit] = None
                continue
            units[layout.unit] = self._freshness(layout, words, decode_unit(layout, words, ctrl))
        if all(v is None for v in units.values()):
            raise UpdateFailed(f"No answer from the ECU at {self.hub.host}:{self.hub.port}: {errors[0]}")
        if errors:
            _LOGGER.debug("Partial read: %s", errors)
        return {"units": units, "ecu": self._aggregate(units)}

    def _freshness(self, layout: UnitLayout, words: dict[int, int], data: dict) -> dict:
        """Flag data the ECU has not refreshed for a while as asleep.

        Until a unit has been watched for `stale_after`, its data counts as
        fresh: after a restart at night the old values show for that long.
        """
        fingerprint = measurement_fingerprint(layout, words)
        now = monotonic()
        if self._fingerprints.get(layout.unit) != fingerprint:
            self._fingerprints[layout.unit] = fingerprint
            self._changed_mono[layout.unit] = now
            self._changed_at[layout.unit] = dt_util.utcnow()
        stale = now - self._changed_mono[layout.unit] > self.stale_after
        out = asleep(data) if stale else data
        out["stale"] = stale
        out["last_update"] = self._changed_at[layout.unit]
        return out

    async def _read_unit(self, layout: UnitLayout, ctrl: bool) -> dict[int, int]:
        """Merged reads (up to 125 registers) by default. The ECU answers an
        invalid request with silence, so if a merged read fails, try once
        with one read per model and keep that mode for the unit if it works."""
        if layout.unit in self.split_reads:
            return await self.hub.read_words(layout.unit, layout.spans(ctrl, merge=False))
        try:
            return await self.hub.read_words(layout.unit, layout.spans(ctrl))
        except (HubError, IllegalAddress) as err:
            words = await self.hub.read_words(layout.unit, layout.spans(ctrl, merge=False))
            _LOGGER.info("Unit %s: long reads rejected (%s), reading model by model", layout.unit, err)
            self.split_reads.add(layout.unit)
            return words

    def _aggregate(self, units: dict[int, dict | None]) -> dict[str, Any]:
        answered = [d for d in units.values() if d is not None]
        live = [d for d in answered if not d.get("stale")]
        complete = len(answered) == len(units)

        def total(key: str, need_all: bool) -> float | None:
            # Sleeping inverters count with what asleep() gives them: 0 W.
            vals = [d.get(key) for d in answered]
            if not vals or any(v is None for v in vals) or (need_all and not complete):
                return None
            return round(sum(vals), 3)

        agg: dict[str, Any] = {
            "power": total("power", False),
            # A missing inverter would make the total dip: report nothing instead.
            "energy": total("energy", True),
            "dc_power_total": total("dc_power_total", False),
            "inverters_online": len(live),
            "inverters_producing": sum(1 for d in live if (d.get("power") or 0) > 0),
            "events": sorted({e for d in live for e in active_events(d.get("events"))}),
        }
        ctrl = units.get(self.control_unit) if self.control_unit else None
        if ctrl:
            for key in ("conn", "limit_pct", "limit_enabled", "limit_pct_sf"):
                agg[key] = ctrl.get(key)
        return agg

    # --- writes (model 123, global to the array on the ECU) ------------------
    async def _write(self, offset: int, word: int) -> None:
        layout = self.control_layout
        if layout is None or layout.controls is None:
            raise UpdateFailed("No control model on this ECU")
        try:
            await self.hub.write(layout.unit, layout.controls.start + offset, word)
        except (HubError, IllegalAddress) as err:
            raise UpdateFailed(f"Write failed: {err}") from err

    def _optimistic(self, **values) -> None:
        """Show a write at once: the follow-up refresh is debounced and the
        ECU echoes stored values anyway (see the README before trusting it)."""
        if self.data:
            self.data["ecu"].update(values)
            self.async_update_listeners()

    def _limit_word(self, pct: float) -> int:
        factor = (self.data or {}).get("ecu", {}).get("limit_pct_sf")
        factor = -1 if factor is None else factor
        return max(0, min(round(pct / 10**factor), round(100 / 10**factor)))

    async def async_set_limit(self, pct: float) -> None:
        await self._write(OFF_LIMIT, self._limit_word(pct))
        self.last_limit = pct
        self._optimistic(limit_pct=pct)
        # A limit is stored and silently ignored while WMaxLim_Ena is 0.
        if (self.data or {}).get("ecu", {}).get("limit_enabled") == 0:
            await self._write(OFF_LIMIT_ENA, 1)
            self._optimistic(limit_enabled=1)
        await self.async_request_refresh()

    async def async_set_limit_enabled(self, on: bool) -> None:
        await self._write(OFF_LIMIT_ENA, 1 if on else 0)
        self._optimistic(limit_enabled=1 if on else 0)
        await self.async_request_refresh()

    async def async_set_conn(self, on: bool) -> None:
        await self._write(OFF_CONN, 1 if on else 0)
        self._optimistic(conn=1 if on else 0)
        await self.async_request_refresh()

    # --- optional periodic rewrite of the last limit -------------------------
    def start_keepalive(self) -> None:
        period = self.config_entry.options.get(CONF_KEEPALIVE, DEFAULT_KEEPALIVE)
        if period <= 0:
            return

        async def _tick(_now) -> None:
            if self.last_limit is None:
                return
            try:
                await self._write(OFF_LIMIT, self._limit_word(self.last_limit))
            except UpdateFailed as err:
                _LOGGER.warning("Limit keepalive failed: %s", err)

        self._unsub_keepalive = async_track_time_interval(
            self.hass, _tick, timedelta(seconds=period)
        )

    def stop_keepalive(self) -> None:
        if self._unsub_keepalive:
            self._unsub_keepalive()
            self._unsub_keepalive = None
