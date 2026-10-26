"""Modbus access to the ECU through Home Assistant's shared connections.

The ECU serves one Modbus unit per inverter on the same TCP port. The units
are taken from the `modbus` integration, which keeps one connection per host
and port for every integration that asks for it and serialises their
requests instead of letting them compete for the ECU.

An address or unit the ECU does not serve produces silence rather than a
Modbus exception, so a timeout is the normal answer for "not there" and the
scan uses a short one.
"""
from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import AsyncExitStack, asynccontextmanager

from modbus_connection import (
    ModbusConnectionError,
    ModbusError,
    ModbusExceptionError,
    ModbusTcpParams,
    ModbusUnit,
)

from homeassistant.components.modbus import async_get_temporary_unit, async_get_unit
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError


class HubError(Exception):
    """No answer or connection lost."""


class HubConnectError(HubError):
    """No link to host:port, or the link is held with other settings."""


class IllegalAddress(Exception):
    """The device answered with a Modbus exception."""


class EcuHub:
    """Reads and writes on the ECU's units, each taken once and kept."""

    def __init__(
        self,
        host: str,
        port: int,
        take_unit: Callable[[int], Awaitable[ModbusUnit]],
        timeout: float,
    ) -> None:
        self.host, self.port = host, port
        self._take_unit = take_unit
        self._timeout = timeout
        self._units: dict[int, ModbusUnit] = {}

    @classmethod
    def for_entry(
        cls, hass: HomeAssistant, entry: ConfigEntry, host: str, port: int, timeout: float
    ) -> EcuHub:
        """Units held for the life of the config entry, released on its unload."""
        params = ModbusTcpParams(host=host, port=port)

        async def take_unit(unit: int) -> ModbusUnit:
            return async_get_unit(hass, entry, params, unit)

        return cls(host, port, take_unit, timeout)

    @classmethod
    @asynccontextmanager
    async def temporary(
        cls, hass: HomeAssistant, host: str, port: int, timeout: float
    ) -> AsyncIterator[EcuHub]:
        """Units held only for the context, for the config flow's scan.

        A connection already held by a loaded entry is shared and stays up;
        one opened here is closed on exit.
        """
        params = ModbusTcpParams(host=host, port=port)
        async with AsyncExitStack() as stack:

            async def take_unit(unit: int) -> ModbusUnit:
                return await stack.enter_async_context(
                    async_get_temporary_unit(hass, params, unit)
                )

            yield cls(host, port, take_unit, timeout)

    async def _unit(self, unit: int) -> ModbusUnit:
        if (held := self._units.get(unit)) is None:
            try:
                held = await self._take_unit(unit)
            except HomeAssistantError as err:
                raise HubConnectError(str(err)) from err
            # The link's timeout is the largest any holder asks for.
            held.require_timeout(self._timeout)
            self._units[unit] = held
        return held

    @property
    def connected(self) -> bool:
        """Whether the link to the ECU is open; a silent unit leaves it open."""
        return any(u.connected for u in self._units.values())

    async def read(self, unit: int, address: int, count: int) -> list[int]:
        modbus = await self._unit(unit)
        what = f"unit {unit} {address}+{count}"
        try:
            return list(await modbus.read_holding_registers(address, count))
        except ModbusExceptionError as err:
            raise IllegalAddress(f"{what}: {err}") from err
        except ModbusConnectionError as err:
            raise HubConnectError(f"{what}: {err}") from err
        except ModbusError as err:
            raise HubError(f"{what}: {err}") from err

    async def read_words(self, unit: int, spans: list[tuple[int, int]]) -> dict[int, int]:
        words: dict[int, int] = {}
        for start, end in spans:
            regs = await self.read(unit, start, end - start)
            words.update({start + i: w for i, w in enumerate(regs)})
        return words

    async def write(self, unit: int, address: int, word: int) -> None:
        modbus = await self._unit(unit)
        what = f"write unit {unit} {address}={word}"
        try:
            # Function code 16, accepted by every ECU firmware seen so far.
            await modbus.write_registers(address, [word])
        except ModbusExceptionError as err:
            raise IllegalAddress(f"{what}: {err}") from err
        except ModbusConnectionError as err:
            raise HubConnectError(f"{what}: {err}") from err
        except ModbusError as err:
            raise HubError(f"{what}: {err}") from err
