"""Ampere Modbus Hub"""

from pymodbus.register_read_message import ReadInputRegistersResponse
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from voluptuous.validators import Number
from homeassistant.helpers.typing import HomeAssistantType
import logging
import threading
from datetime import timedelta
from homeassistant.core import CALLBACK_TYPE, callback
from pymodbus.client import ModbusTcpClient
from pymodbus.constants import Endian
from pymodbus.exceptions import ConnectionException
from pymodbus.payload import BinaryPayloadDecoder

from .const import (
    PV_DIRECTION,
    BATTERY_DIRECTION,
    GRID_DIRECTION,
)

_LOGGER = logging.getLogger(__name__)


class AmpereStorageProModbusHub(DataUpdateCoordinator[dict]):
    """Thread safe wrapper class for pymodbus."""

    def __init__(
        self,
        hass: HomeAssistantType,
        name: str,
        host: str,
        port: Number,
        unit: Number,
        scan_interval: Number,
    ):
        """Initialize the Modbus hub."""
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(seconds=scan_interval),
        )

        self.unit = unit
        self._client = ModbusTcpClient(host=host, port=port, timeout=5)
        self._lock = threading.Lock()

        self.inverter_data: dict = {}
        self.data: dict = {}

    @callback
    def async_remove_listener(self, update_callback: CALLBACK_TYPE) -> None:
        """Remove data update listener."""
        super().async_remove_listener(update_callback)

        """No listeners left then close connection"""
        if not self._listeners:
            self.close()

    def close(self) -> None:
        """Disconnect client."""
        with self._lock:
            self._client.close()

    def _read_input_registers(self, unit, address, count) -> ReadInputRegistersResponse:
        """Read input registers."""
        with self._lock:
            return self._client.read_input_registers(
                address=address, count=count, slave=unit
            )

    async def _async_update_data(self) -> dict:
        realtime_data = {}
        longterm_data = {}
        try:
            """Inverter info is only fetched once"""
            if not self.inverter_data:
                self.inverter_data = await self.hass.async_add_executor_job(
                    self.read_modbus_inverter_data
                )

            """Read realtime data"""
            realtime_data = await self.hass.async_add_executor_job(
                self.read_modbus_realtime_data
            )
            longterm_data = await self.hass.async_add_executor_job(
                self.read_modbus_longterm_data
            )
        except ConnectionException:
            _LOGGER.error("Reading realtime data failed! Inverter is unreachable.")

        return {
            **self.inverter_data,
            **realtime_data,
            **longterm_data,
        }

    def read_modbus_inverter_data(self) -> dict:
        _LOGGER.error("Reading inverter data")
        inverter_data = self._read_input_registers(
            unit=self.unit, address=0x8F00, count=29
        )

        if inverter_data.isError():
            return {}

        data = {}
        decoder = BinaryPayloadDecoder.fromRegisters(
            inverter_data.registers, byteorder=Endian.BIG
        )

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

    def read_modbus_realtime_data(self) -> dict:

        realtime_data = self._read_input_registers(
            unit=self.unit, address=0x4069, count=48
        )

        if realtime_data.isError():
            return {}

        data = {}

        decoder = BinaryPayloadDecoder.fromRegisters(
            realtime_data.registers, byteorder=Endian.BIG
        )
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

        data["totalpvpower"] = round(pv1power * 1, 0) + round(pv2power * 1, 0)

        decoder.skip_bytes(12)  # pv3 & pv4
        decoder.skip_bytes(32)  # unkown, always = 0
        decoder.skip_bytes(16)  # net side (V A Hz W 4xr)

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

        decoder.skip_bytes(1)  # flow load

        return data

    def read_modbus_longterm_data(self) -> dict:

        longterm_data = self._read_input_registers(
            unit=self.unit, address=0x40BF, count=24
        )

        if longterm_data.isError():
            return {}

        data = {}

        decoder = BinaryPayloadDecoder.fromRegisters(
            longterm_data.registers, byteorder=Endian.BIG
        )

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
        data["dailydischargebattery"] = round(dailydischargebattery * 0.01, 2)
        data["monthdischargebattery"] = round(monthdischargebattery * 0.01, 2)
        data["yeardischargebattery"] = round(yeardischargebattery * 0.01, 2)
        data["totaldischargebattery"] = round(totaldischargebattery * 0.01, 2)

        return data
