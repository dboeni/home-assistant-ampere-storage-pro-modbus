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
from pymodbus.client.mixin import ModbusClientMixin
from pymodbus.exceptions import ConnectionException, ModbusIOException

from .const import (
    DEVICE_STATUSSES,
    PV_DIRECTION,
    BATTERY_DIRECTION,
    GRID_DIRECTION,
    FAULT_MESSAGES,
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
        client = AsyncModbusTcpClient(
            host=self._host,
            port=self._port,
            timeout=10,
        )
        _LOGGER.debug(
            f"Created new Modbus client: AsyncModbusTcpClient {self._host}:{self._port}"
        )
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
            _LOGGER.warning(f"Error during connection attempt: {e}", exc_info=True)
            raise ConnectionException("Failed to connect to Modbus server.") from e

    async def read_holding_registers(
        self,
        unit: int,
        address: int,
        count: int,
        max_retries: int = 3,
        base_delay: float = 2.0,
    ) -> List[int]:
        """Reads Modbus registers with error handling."""
        for attempt in range(max_retries):
            try:
                async with self._read_lock:
                    response = await self._client.read_holding_registers(
                        address=address, count=count, device_id=unit
                    )

                if (
                    (not response)
                    or response.isError()
                    or len(response.registers) != count
                ):
                    raise ModbusIOException(f"Invalid response from address {address}")

                return response.registers

            except (ModbusIOException, ConnectionException) as e:
                _LOGGER.error(
                    f"Read attempt {attempt + 1} failed at address {address}: {e}"
                )
                if attempt <= max_retries:
                    delay = min(base_delay * (2**attempt), 10.0)
                    await asyncio.sleep(delay)
                    if not await self._safe_close():
                        _LOGGER.warning("Failed to safely close the Modbus client.")
                    try:
                        await self.ensure_modbus_connection()
                    except ConnectionException:
                        _LOGGER.error("Failed to reconnect Modbus client.")
                        continue
                    else:
                        _LOGGER.info("Reconnected Modbus client successfully.")
        _LOGGER.error(
            f"Failed to read registers from unit {unit}, address {address} after {max_retries} attempts"
        )
        raise ConnectionException(
            f"Read operation failed for address {address} after {max_retries} attempts"
        )

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

    def decode_16bit_uint(self, register: List[int], position: int) -> tuple[any, int]:
        try:
            value = self._client.convert_from_registers(
                [register[position]], ModbusClientMixin.DATATYPE.UINT16
            )
        except Exception as e:
            _LOGGER.error(f"Error decode_16bit_uint: {e}")

        position += 1
        return value, position

    def decode_16bit_int(self, register: List[int], position: int) -> tuple[any, int]:
        try:
            value = self._client.convert_from_registers(
                [register[position]], ModbusClientMixin.DATATYPE.INT16
            )
        except Exception as e:
            _LOGGER.error(f"Error decode_16bit_int: {e}")

        position += 1
        return value, position

    def decode_32bit_uint(self, register: List[int], position: int) -> tuple[any, int]:
        try:
            value = self._client.convert_from_registers(
                [register[position], register[position + 1]],
                ModbusClientMixin.DATATYPE.UINT32,
            )
        except Exception as e:
            _LOGGER.error(f"Error decode_32bit_uint: {e}")

        position += 2
        return value, position

    def decode_32bit_int(self, register: List[int], position: int) -> tuple[any, int]:
        try:
            value = self._client.convert_from_registers(
                [register[position], register[position + 1]],
                ModbusClientMixin.DATATYPE.INT32,
            )
        except Exception as e:
            _LOGGER.error(f"Error decode_32bit_int: {e}")

        position += 2
        return value, position

    def decode_string(
        self, length: int, register: List[int], position: int
    ) -> tuple[str, int]:

        registerOfString: List[int] = []
        for i in range(length):
            registerOfString.append(register[position + i])

        try:
            value = self._client.convert_from_registers(
                registerOfString, ModbusClientMixin.DATATYPE.STRING
            )
        except Exception as e:
            _LOGGER.error(f"Error decode_string: {e}")
            value = ""

        position += length
        return str(value), position

    async def read_modbus_inverter_data(self) -> dict:
        try:
            registerList = await self.read_holding_registers(self._unit, 0x8F00, 29)
            position: int = 0
            data = {}

            value, position = self.decode_16bit_uint(registerList, position)
            data["devicetype"] = value

            value, position = self.decode_16bit_uint(registerList, position)
            data["subtype"] = value

            value, position = self.decode_16bit_uint(registerList, position)
            data["commver"] = round(value * 0.001, 3)

            value, position = self.decode_string(10, registerList, position)
            data["serialnumber"] = str(value)

            value, position = self.decode_string(10, registerList, position)
            data["productcode"] = str(value)

            value, position = self.decode_16bit_uint(registerList, position)
            data["dv"] = round(value * 0.001, 3)
            value, position = self.decode_16bit_uint(registerList, position)
            data["mcv"] = round(value * 0.001, 3)
            value, position = self.decode_16bit_uint(registerList, position)
            data["scv"] = round(value * 0.001, 3)
            value, position = self.decode_16bit_uint(registerList, position)
            data["disphwversion"] = round(value * 0.001, 3)
            value, position = self.decode_16bit_uint(registerList, position)
            data["ctrlhwversion"] = round(value * 0.001, 3)
            value, position = self.decode_16bit_uint(registerList, position)
            data["powerhwversion"] = round(value * 0.001, 3)

            return data
        except Exception as e:
            _LOGGER.error(f"Error reading inverter data: {e}")
            return {}

    async def read_modbus_device_data(self) -> dict:
        try:
            registerList = await self.read_holding_registers(self._unit, 0x4004, 7)
            position: int = 0
            data = {}

            value, position = self.decode_16bit_uint(registerList, position)
            data["devicestatus"] = DEVICE_STATUSSES.get(value, "Unknown")

            fault1, position = self.decode_32bit_uint(registerList, position)
            fault2, position = self.decode_32bit_uint(registerList, position)
            fault3, position = self.decode_32bit_uint(registerList, position)
            error_messages = []
            error_messages.extend(
                msg for code, msg in FAULT_MESSAGES[0].items() if fault1 & code
            )
            error_messages.extend(
                msg for code, msg in FAULT_MESSAGES[1].items() if fault2 & code
            )
            error_messages.extend(
                msg for code, msg in FAULT_MESSAGES[2].items() if fault3 & code
            )
            data["deviceerror"] = ", ".join(error_messages).strip()[:254]

            return data
        except Exception as e:
            _LOGGER.error(f"Error reading inverter data: {e}")
            return {}

    async def read_modbus_realtime_data(self) -> dict:
        try:
            registerList = await self.read_holding_registers(self._unit, 0x4069, 60)
            position: int = 0
            data = {}

            value, position = self.decode_16bit_uint(registerList, position)
            data["batteryvoltage"] = round(value * 0.1, 1)

            value, position = self.decode_16bit_int(registerList, position)
            data["batterycurrent"] = round(value * 0.01, 2)

            position += 2  # skip 4 bytes

            value, position = self.decode_16bit_int(registerList, position)
            data["batterypower"] = round(value * 1, 0)
            value, position = self.decode_16bit_int(registerList, position)
            data["batterytemperature"] = round(value * 0.1, 0)
            value, position = self.decode_16bit_uint(registerList, position)
            data["batterypercent"] = round(value * 0.01, 0)

            position += 1  # skip 2 bytes

            value, position = self.decode_16bit_uint(registerList, position)
            data["pv1volt"] = round(value * 0.1, 1)
            value, position = self.decode_16bit_uint(registerList, position)
            data["pv1curr"] = round(value * 0.01, 2)
            pv1power, position = self.decode_16bit_uint(registerList, position)
            data["pv1power"] = round(pv1power * 1, 0)

            value, position = self.decode_16bit_uint(registerList, position)
            data["pv2volt"] = round(value * 0.1, 1)
            value, position = self.decode_16bit_uint(registerList, position)
            data["pv2curr"] = round(value * 0.01, 2)
            pv2power, position = self.decode_16bit_uint(registerList, position)
            data["pv2power"] = round(pv2power * 1, 0)

            data["totalpvpower"] = round(pv1power * 1, 0) + round(pv2power * 1, 0)

            # pv3 & pv4
            position += 6  # skip 12 bytes
            # unkown, always = 0
            position += 16  # skip 32 bytes

            # net side
            # skip 16 bytes
            position += 1  # V Volt (R)
            position += 1  # A Current (R)
            position += 1  # Hz Frequenz (R)
            position += 1  # W Power L1 (R)
            position += 1  # A Current L2 (S)
            position += 1  # W Power L2 (S)
            position += 1  # A Current L3 (T)
            position += 1  # W Power L3 (T)

            value, position = self.decode_16bit_int(registerList, position)
            data["pvflow"] = value
            if value in PV_DIRECTION:
                data["pvflowtext"] = PV_DIRECTION[value]
            else:
                data["pvflowtext"] = "Unknown"

            value, position = self.decode_16bit_int(registerList, position)
            data["batteryflow"] = value
            if value in BATTERY_DIRECTION:
                data["batteryflowtext"] = BATTERY_DIRECTION[value]
            else:
                data["batteryflowtext"] = "Unknown"

            value, position = self.decode_16bit_int(registerList, position)
            data["gridflow"] = value
            if value in GRID_DIRECTION:
                data["gridflowtext"] = GRID_DIRECTION[value]
            else:
                data["gridflowtext"] = "Unknown"

            # flow load
            position += 1  # skip 2 bytes
            # res
            position += 7  # skip 14 bytes

            # Internal CT acquisition
            # W The total system load consumes power
            position += 1  # skip 2 bytes
            # W CT real power of the grid
            value, position = self.decode_16bit_int(registerList, position)
            data["gridpower"] = value
            position += 1  # VA CT Apparent power of the grid
            position += 1  # W CT PV real power
            position += 1  # VA CT PV Apparent power

            return data

        except Exception as e:
            _LOGGER.error(f"Error reading inverter data: {e}")
            return {}

    async def read_modbus_longterm_data(self) -> dict:
        try:
            registerList = await self.read_holding_registers(self._unit, 0x40BF, 88)
            position: int = 0
            data = {}

            value, position = self.decode_32bit_uint(registerList, position)
            data["dailypvgeneration"] = round(value * 0.01, 2)
            value, position = self.decode_32bit_uint(registerList, position)
            data["monthpvgeneration"] = round(value * 0.01, 2)
            value, position = self.decode_32bit_uint(registerList, position)
            data["yearpvgeneration"] = round(value * 0.01, 2)
            value, position = self.decode_32bit_uint(registerList, position)
            data["totalpvgeneration"] = round(value * 0.01, 2)

            value, position = self.decode_32bit_uint(registerList, position)
            data["dailychargebattery"] = round(value * 0.01, 2)
            value, position = self.decode_32bit_uint(registerList, position)
            data["monthchargebattery"] = round(value * 0.01, 2)
            value, position = self.decode_32bit_uint(registerList, position)
            data["yearchargebattery"] = round(value * 0.01, 2)
            value, position = self.decode_32bit_uint(registerList, position)
            data["totalchargebattery"] = round(value * 0.01, 2)

            value, position = self.decode_32bit_uint(registerList, position)
            data["dailydischargebattery"] = round(value * 0.01, 2)
            value, position = self.decode_32bit_uint(registerList, position)
            data["monthdischargebattery"] = round(value * 0.01, 2)
            value, position = self.decode_32bit_uint(registerList, position)
            data["yeardischargebattery"] = round(value * 0.01, 2)
            value, position = self.decode_32bit_uint(registerList, position)
            data["totaldischargebattery"] = round(value * 0.01, 2)

            return data

        except Exception as e:
            _LOGGER.error(f"Error reading inverter data: {e}")
            return {}
