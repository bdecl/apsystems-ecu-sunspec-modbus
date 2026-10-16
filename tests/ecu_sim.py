"""Minimal Modbus TCP server that behaves like the ECU.

Written by hand rather than with pymodbus' simulator, whose datastore API
changes between releases, and because the ECU has one behaviour a stock
simulator does not: a unit id that is not configured gets no answer at all.
Supports function codes 3 (read), 6 and 16 (write).
"""
import asyncio
import struct

from ecu_image import BASE, SIZE


class EcuSim:
    def __init__(self, units: dict[int, list[int]]):
        self.units = {u: list(img) for u, img in units.items()}
        self.server: asyncio.base_events.Server | None = None
        self.port = 0
        self._writers: set[asyncio.StreamWriter] = set()

    def reg(self, unit: int, address: int) -> int:
        return self.units[unit][address - BASE]

    def set(self, unit: int, address: int, value: int) -> None:
        self.units[unit][address - BASE] = value

    async def start(self) -> int:
        self.server = await asyncio.start_server(self._client, "127.0.0.1", 0)
        self.port = self.server.sockets[0].getsockname()[1]
        return self.port

    async def stop(self) -> None:
        if self.server:
            self.server.close()
            # wait_closed() also waits for open client connections
            for writer in list(self._writers):
                writer.close()
            await asyncio.wait_for(self.server.wait_closed(), 5)

    def _answer(self, unit: int, pdu: bytes) -> bytes | None:
        img = self.units.get(unit)
        if img is None:
            return None  # silence, like the real ECU
        fc = pdu[0]

        def in_range(addr: int, count: int) -> bool:
            return BASE <= addr and addr + count <= BASE + SIZE and 0 < count <= 125

        if fc == 3:
            addr, count = struct.unpack(">HH", pdu[1:5])
            if not in_range(addr, count):
                return bytes([fc | 0x80, 2])
            regs = img[addr - BASE:addr - BASE + count]
            return bytes([fc, 2 * count]) + struct.pack(f">{count}H", *regs)
        if fc == 6:
            addr, value = struct.unpack(">HH", pdu[1:5])
            if not in_range(addr, 1):
                return bytes([fc | 0x80, 2])
            img[addr - BASE] = value
            return pdu[:5]
        if fc == 16:
            addr, count, nbytes = struct.unpack(">HHB", pdu[1:6])
            if not in_range(addr, count):
                return bytes([fc | 0x80, 2])
            values = struct.unpack(f">{count}H", pdu[6:6 + nbytes])
            img[addr - BASE:addr - BASE + count] = values
            return pdu[:5]
        return bytes([fc | 0x80, 1])

    async def _client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._writers.add(writer)
        try:
            while True:
                header = await reader.readexactly(7)
                tid, pid, length, unit = struct.unpack(">HHHB", header)
                pdu = await reader.readexactly(length - 1)
                out = self._answer(unit, pdu)
                if out is None:
                    continue
                writer.write(struct.pack(">HHHB", tid, pid, len(out) + 1, unit) + out)
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            self._writers.discard(writer)
            writer.close()
