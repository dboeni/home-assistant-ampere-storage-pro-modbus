"""Ampere Modbus Hub"""

import asyncio
import logging
from datetime import timedelta
from typing import List, Optional
import inspect
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from voluptuous.validators import Number
import threading
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.constants import Endian
from pymodbus.payload import BinaryPayloadDecoder
from pymodbus.exceptions import ConnectionException, ModbusIOException

from .const import (
    DEVICE_STATUSSES,
    PV_DIRECTION,
    BATTERY_DIRECTION,
    GRID_DIRECTION,
    FAULT_MESSAGES
)

_LOGGER = logging.getLogger(__name__)


class AmpereStorageProModbusHub(DataUpdateCoordinator[dict]):
    def __init__(
        self,
        hass: HomeAssistant,
        name: str,
        host: str,
        port: Number,
        unit: Number,
        scan_interval: Number,
    ):
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(seconds=scan_interval),
            update_method=self._async_update_data,
        )
        self._host = host
        self._port = port
        self._unit = unit
        self._client: Optional[AsyncModbusTcpClient] = None
        self._closing = False
        self._read_lock = asyncio.Lock()
        self._connection_lock = asyncio.Lock()
        self._lock = threading.Lock()

        self._inverter_data: dict = {}
        self.data: dict = {}

    def _create_client(self) -> AsyncModbusTcpClient:
        """Create a new client instance."""
        client = AsyncModbusTcpClient(host=self._host,
                                      port=self._port,
                                      timeout=10,
                                      )
        _LOGGER.debug(
            f"Created new Modbus client: AsyncModbusTcpClient {self._host}:{self._port}")
        return client

    async def _safe_close(self) -> bool:
        """Safely closes the Modbus connection."""
        if not self._client:
            return True

        try:
            if self._client.connected:
                close = getattr(self._client, "close", None)
                if close:
                    await close() if inspect.iscoroutinefunction(close) else close()
                transport = getattr(self._client, "transport", None)
                if transport:
                    transport.close()
                await asyncio.sleep(0.2)
                return not self._client.connected
            return True
        except Exception as e:
            _LOGGER.warning(f"Error during safe close: {e}", exc_info=True)
            return False
        finally:
            self._client = None

    async def close(self) -> None:
        """Closes the Modbus connection with improved resource management."""
        if self._closing:
            return

        self._closing = True
        try:
            async with asyncio.timeout(5.0):
                async with self._connection_lock:
                    await self._safe_close()
        except (asyncio.TimeoutError, Exception) as e:
            _LOGGER.warning(f"Error during close: {e}", exc_info=True)
        finally:
            self._closing = False

    async def ensure_modbus_connection(self) -> None:
        """Ensure the Modbus connection is established and stable."""
        if self._client and self._client.connected:
            return

        self._client = self._client or self._create_client()
        try:
            await asyncio.wait_for(self._client.connect(), timeout=10)
            _LOGGER.info("Successfully connected to Modbus server.")
        except Exception as e:
            _LOGGER.warning(
                f"Error during connection attempt: {e}", exc_info=True)
            raise ConnectionException(
                "Failed to connect to Modbus server.") from e

    async def read_holding_registers(
        self,
        unit: int,
        address: int,
        count: int,
        max_retries: int = 3,
        base_delay: float = 2.0
    ) -> List[int]:
        """Reads Modbus registers with error handling."""
        for attempt in range(max_retries):
            try:
                async with self._read_lock:
                    response = await self._client.read_holding_registers(
                        address=address, count=count, slave=unit
                    )

                if (not response) or response.isError() or len(response.registers) != count:
                    raise ModbusIOException(
                        f"Invalid response from address {address}")

                return response.registers

            except (ModbusIOException, ConnectionException) as e:
                _LOGGER.error(
                    f"Read attempt {attempt + 1} failed at address {address}: {e}")
                if attempt <= max_retries:
                    delay = min(base_delay * (2 ** attempt), 10.0)
                    await asyncio.sleep(delay)
                    if not await self._safe_close():
                        _LOGGER.warning(
                            "Failed to safely close the Modbus client.")
                    try:
                        await self.ensure_modbus_connection()
                    except ConnectionException:
                        _LOGGER.error("Failed to reconnect Modbus client.")
                        continue
                    else:
                        _LOGGER.info("Reconnected Modbus client successfully.")
        _LOGGER.error(
            f"Failed to read registers from unit {unit}, address {address} after {max_retries} attempts")
        raise ConnectionException(
            f"Read operation failed for address {address} after {max_retries} attempts")

    async def _async_update_data(self) -> dict:
        await self.ensure_modbus_connection()
        if not self._inverter_data:
            self._inverter_data.update(await self.read_modbus_inverter_data())
        all_read_data = {**self._inverter_data}

        all_read_data.update(await self.read_modbus_device_data())
        all_read_data.update(await self.read_modbus_realtime_data())
        all_read_data.update(await self.read_modbus_longterm_data())

        await self.close()
        return all_read_data

    async def read_modbus_inverter_data(self) -> dict:
        try:
            regs = await self.read_holding_registers(self._unit, 0x8F00, 29)
            decoder = BinaryPayloadDecoder.fromRegisters(
                regs, byteorder=Endian.BIG)
            data = {}

            devicetype = decoder.decode_16bit_uint()
            data["devicetype"] = devicetype
            subtype = decoder.decode_16bit_uint()
            data["subtype"] = subtype
            commver = decoder.decode_16bit_uint()
            data["commver"] = round(commver * 0.001, 3)

            serialnumber = decoder.decode_string(20).decode("ascii")
            data["serialnumber"] = str(serialnumber)
            productcode = decoder.decode_string(20).decode("ascii")
            data["productcode"] = str(productcode)

            dv = decoder.decode_16bit_uint()
            data["dv"] = round(dv * 0.001, 3)
            mcv = decoder.decode_16bit_uint()
            data["mcv"] = round(mcv * 0.001, 3)
            scv = decoder.decode_16bit_uint()
            data["scv"] = round(scv * 0.001, 3)
            disphwversion = decoder.decode_16bit_uint()
            data["disphwversion"] = round(disphwversion * 0.001, 3)
            ctrlhwversion = decoder.decode_16bit_uint()
            data["ctrlhwversion"] = round(ctrlhwversion * 0.001, 3)
            powerhwversion = decoder.decode_16bit_uint()
            data["powerhwversion"] = round(powerhwversion * 0.001, 3)

            return data
        except Exception as e:
            _LOGGER.error(f"Error reading inverter data: {e}")
            return {}

    async def read_modbus_device_data(self) -> dict:
        try:
            regs = await self.read_holding_registers(self._unit, 0x4004, 7)
            decoder = BinaryPayloadDecoder.fromRegisters(
                regs, byteorder=Endian.BIG)
            data = {}

            mpv = decoder.decode_16bit_uint()
            data["devicestatus"] = DEVICE_STATUSSES.get(mpv, "Unknown")

            fault1 = decoder.decode_32bit_uint()
            fault2 = decoder.decode_32bit_uint()
            fault3 = decoder.decode_32bit_uint()
            error_messages = []
            error_messages.extend(msg for code, msg in FAULT_MESSAGES[0].items()
                                  if fault1 & code)
            error_messages.extend(msg for code, msg in FAULT_MESSAGES[1].items()
                                  if fault2 & code)
            error_messages.extend(msg for code, msg in FAULT_MESSAGES[2].items()
                                  if fault3 & code)
            data["deviceerror"] = ", ".join(error_messages).strip()[:254]

            return data
        except Exception as e:
            _LOGGER.error(f"Error reading inverter data: {e}")
            return {}

    async def read_modbus_realtime_data(self) -> dict:
        try:
            regs = await self.read_holding_registers(self._unit, 0x4069, 60)
            decoder = BinaryPayloadDecoder.fromRegisters(
                regs, byteorder=Endian.BIG)
            data = {}

            batteryvoltage = decoder.decode_16bit_uint()
            batterycurrent = decoder.decode_16bit_int()
            decoder.skip_bytes(4)
            batterypower = decoder.decode_16bit_int()
            batterytemperature = decoder.decode_16bit_int()
            batterypercent = decoder.decode_16bit_uint()
            data["batteryvoltage"] = round(batteryvoltage * 0.1, 1)
            data["batterycurrent"] = round(batterycurrent * 0.01, 2)
            data["batterypower"] = round(batterypower * 1, 0)
            data["batterytemperature"] = round(batterytemperature * 0.1, 0)
            data["batterypercent"] = round(batterypercent * 0.01, 0)

            decoder.skip_bytes(2)  # res

            pv1volt = decoder.decode_16bit_uint()
            pv1curr = decoder.decode_16bit_uint()
            pv1power = decoder.decode_16bit_uint()
            data["pv1volt"] = round(pv1volt * 0.1, 1)
            data["pv1curr"] = round(pv1curr * 0.01, 2)
            data["pv1power"] = round(pv1power * 1, 0)

            pv2volt = decoder.decode_16bit_uint()
            pv2curr = decoder.decode_16bit_uint()
            pv2power = decoder.decode_16bit_uint()
            data["pv2volt"] = round(pv2volt * 0.1, 1)
            data["pv2curr"] = round(pv2curr * 0.01, 2)
            data["pv2power"] = round(pv2power * 1, 0)

            data["totalpvpower"] = round(
                pv1power * 1, 0) + round(pv2power * 1, 0)

            decoder.skip_bytes(12)  # pv3 & pv4
            decoder.skip_bytes(32)  # unkown, always = 0

            # net side
            decoder.skip_bytes(2)  # V Volt (R)
            decoder.skip_bytes(2)  # A Current (R)
            decoder.skip_bytes(2)  # Hz Frequenz (R)
            decoder.skip_bytes(2)  # W Power L1 (R)
            decoder.skip_bytes(2)  # A Current L2 (S)
            decoder.skip_bytes(2)  # W Power L2 (S)
            decoder.skip_bytes(2)  # A Current L3 (T)
            decoder.skip_bytes(2)  # W Power L3 (T)

            pvflow = decoder.decode_16bit_uint()
            data["pvflow"] = pvflow
            if pvflow in PV_DIRECTION:
                data["pvflowtext"] = PV_DIRECTION[pvflow]
            else:
                data["pvflowtext"] = "Unknown"

            batteryflow = decoder.decode_16bit_int()
            data["batteryflow"] = batteryflow
            if batteryflow in BATTERY_DIRECTION:
                data["batteryflowtext"] = BATTERY_DIRECTION[batteryflow]
            else:
                data["batteryflowtext"] = "Unknown"

            gridflow = decoder.decode_16bit_int()
            data["gridflow"] = gridflow
            if gridflow in GRID_DIRECTION:
                data["gridflowtext"] = GRID_DIRECTION[gridflow]
            else:
                data["gridflowtext"] = "Unknown"

            decoder.skip_bytes(2)  # flow load

            decoder.skip_bytes(14)  # res

            # Internal CT acquisition
            decoder.skip_bytes(2)  # W The total system load consumes power
            # W CT real power of the grid
            gridpower = decoder.decode_16bit_int()
            data["gridpower"] = gridpower
            decoder.skip_bytes(2)  # VA CT Apparent power of the grid
            decoder.skip_bytes(2)  # W CT PV real power
            decoder.skip_bytes(2)  # VA CT PV Apparent power

            return data

        except Exception as e:
            _LOGGER.error(f"Error reading inverter data: {e}")
            return {}

    async def read_modbus_longterm_data(self) -> dict:
        try:
            regs = await self.read_holding_registers(self._unit, 0x40BF, 88)
            decoder = BinaryPayloadDecoder.fromRegisters(
                regs, byteorder=Endian.BIG)
            data = {}

            dailypvgeneration = decoder.decode_32bit_uint()
            monthpvgeneration = decoder.decode_32bit_uint()
            yearpvgeneration = decoder.decode_32bit_uint()
            totalpvgeneration = decoder.decode_32bit_uint()
            data["dailypvgeneration"] = round(dailypvgeneration * 0.01, 2)
            data["monthpvgeneration"] = round(monthpvgeneration * 0.01, 2)
            data["yearpvgeneration"] = round(yearpvgeneration * 0.01, 2)
            data["totalpvgeneration"] = round(totalpvgeneration * 0.01, 2)

            dailychargebattery = decoder.decode_32bit_uint()
            monthchargebattery = decoder.decode_32bit_uint()
            yearchargebattery = decoder.decode_32bit_uint()
            totalchargebattery = decoder.decode_32bit_uint()
            data["dailychargebattery"] = round(dailychargebattery * 0.01, 2)
            data["monthchargebattery"] = round(monthchargebattery * 0.01, 2)
            data["yearchargebattery"] = round(yearchargebattery * 0.01, 2)
            data["totalchargebattery"] = round(totalchargebattery * 0.01, 2)

            dailydischargebattery = decoder.decode_32bit_uint()
            monthdischargebattery = decoder.decode_32bit_uint()
            yeardischargebattery = decoder.decode_32bit_uint()
            totaldischargebattery = decoder.decode_32bit_uint()
            data["dailydischargebattery"] = round(
                dailydischargebattery * 0.01, 2)
            data["monthdischargebattery"] = round(
                monthdischargebattery * 0.01, 2)
            data["yeardischargebattery"] = round(
                yeardischargebattery * 0.01, 2)
            data["totaldischargebattery"] = round(
                totaldischargebattery * 0.01, 2)

            return data

        except Exception as e:
            _LOGGER.error(f"Error reading inverter data: {e}")
            return {}
