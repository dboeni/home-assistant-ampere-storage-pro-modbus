from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
    SensorEntityDescription,
    EntityCategory,
)
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    PERCENTAGE,
)
import logging
from typing import Optional

from homeassistant.const import CONF_NAME
from homeassistant.core import callback
import homeassistant.util.dt as dt_util

from .const import (
    ATTR_MANUFACTURER,
    DOMAIN,
)

from .hub import AmpereStorageProModbusHub

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities):
    hub_name = entry.data[CONF_NAME]
    hub = hass.data[DOMAIN][hub_name]["hub"]

    device_info = {
        "identifiers": {(DOMAIN, hub_name)},
        "name": hub_name,
        "manufacturer": ATTR_MANUFACTURER,
    }

    entities = []
    for sensor_description in SENSOR_TYPES.values():
        sensor = AmpereSensor(
            hub_name,
            hub,
            device_info,
            sensor_description,
        )
        entities.append(sensor)

    async_add_entities(entities)
    return True


class AmpereSensor(CoordinatorEntity, SensorEntity):
    """Representation of an Ampere Storage Pro Modbus sensor."""

    def __init__(
        self,
        platform_name: str,
        hub: AmpereStorageProModbusHub,
        device_info,
        description: AmpereModbusSensorEntityDescription,
    ):
        """Initialize the sensor."""
        self._platform_name = platform_name
        self._attr_device_info = device_info
        self.entity_description: AmpereModbusSensorEntityDescription = description

        super().__init__(coordinator=hub)

    @property
    def name(self):
        """Return the name."""
        return f"{self._platform_name} {self.entity_description.name}"

    @property
    def unique_id(self) -> Optional[str]:
        return f"{self._platform_name}_{self.entity_description.key}"

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return (
            self.coordinator.data[self.entity_description.key]
            if self.entity_description.key in self.coordinator.data
            else None
        )


@dataclass
class AmpereModbusSensorEntityDescription(SensorEntityDescription):
    """A class that describes Zoonneplan sensor entities."""


SENSOR_TYPES: dict[str, list[AmpereModbusSensorEntityDescription]] = {
    "DeviceType": AmpereModbusSensorEntityDescription(
        name="Device Type",
        key="devicetype",
        icon="mdi:information-outline",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "SubType": AmpereModbusSensorEntityDescription(
        name="Sub Type",
        key="subtype",
        icon="mdi:information-outline",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "CommVer": AmpereModbusSensorEntityDescription(
        name="Comms Protocol Version",
        key="commver",
        icon="mdi:information-outline",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "SerialNumber": AmpereModbusSensorEntityDescription(
        name="Serial Number",
        key="serialnumber",
        icon="mdi:information-outline",
        entity_registry_enabled_default=True,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "ProductCode": AmpereModbusSensorEntityDescription(
        name="Product Code",
        key="productcode",
        icon="mdi:information-outline",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "DV": AmpereModbusSensorEntityDescription(
        name="Display Software Version",
        key="dv",
        icon="mdi:information-outline",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "MCV": AmpereModbusSensorEntityDescription(
        name="Master Ctrl Software Version",
        key="mcv",
        icon="mdi:information-outline",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "SCV": AmpereModbusSensorEntityDescription(
        name="Slave Ctrl Software Version",
        key="scv",
        icon="mdi:information-outline",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "DispHWVersion": AmpereModbusSensorEntityDescription(
        name="Display Board Hardware Version",
        key="disphwversion",
        icon="mdi:information-outline",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "CtrlHWVersion": AmpereModbusSensorEntityDescription(
        name="Control Board Hardware Version",
        key="ctrlhwversion",
        icon="mdi:information-outline",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "PowerHWVersion": AmpereModbusSensorEntityDescription(
        name="Power Board Hardware Version",
        key="powerhwversion",
        icon="mdi:information-outline",
        entity_registry_enabled_default=False,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "BatteryVoltage": AmpereModbusSensorEntityDescription(
        name="Battery Voltage",
        key="batteryvoltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "BatteryCurr": AmpereModbusSensorEntityDescription(
        name="Battery Current",
        key="batterycurrent",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "BatteryPower": AmpereModbusSensorEntityDescription(
        name="Battery Power",
        key="batterypower",
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:solar-power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "BatteryTemperature": AmpereModbusSensorEntityDescription(
        name="Battery Temperature",
        key="batterytemperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "BatteryPercent": AmpereModbusSensorEntityDescription(
        name="Battery Percent",
        key="batterypercent",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "PV1Volt": AmpereModbusSensorEntityDescription(
        name="PV1 Voltage",
        key="pv1volt",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "PV1Curr": AmpereModbusSensorEntityDescription(
        name="PV1 Current",
        key="pv1curr",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "PV1Power": AmpereModbusSensorEntityDescription(
        name="PV1 Power",
        key="pv1power",
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:solar-power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "PV2Volt": AmpereModbusSensorEntityDescription(
        name="PV2 Voltage",
        key="pv2volt",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "PV2Curr": AmpereModbusSensorEntityDescription(
        name="PV2 Current",
        key="pv2curr",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    "PV2Power": AmpereModbusSensorEntityDescription(
        name="PV2 Power",
        key="pv2power",
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:solar-power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "TotalPvPower": AmpereModbusSensorEntityDescription(
        name="Total PV Power",
        key="totalpvpower",
        native_unit_of_measurement=UnitOfPower.WATT,
        icon="mdi:solar-power",
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "GridPower": AmpereModbusSensorEntityDescription(
        name="Grid Power",
        key="gridpower",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "DailyPvGeneration": AmpereModbusSensorEntityDescription(
        name="Daily PV Generation",
        key="dailypvgeneration",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:solar-power",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "MonthPvGeneration": AmpereModbusSensorEntityDescription(
        name="Month PV Generation",
        key="monthpvgeneration",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:solar-power",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    "YearPvGeneration": AmpereModbusSensorEntityDescription(
        name="Year PV Generation",
        key="yearpvgeneration",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:solar-power",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    "TotalPvGeneration": AmpereModbusSensorEntityDescription(
        name="Total PV Generation",
        key="totalpvgeneration",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        icon="mdi:solar-power",
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "DailyChargeBattery": AmpereModbusSensorEntityDescription(
        name="Daily Charge Battery",
        key="dailychargebattery",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "MonthChargeBattery": AmpereModbusSensorEntityDescription(
        name="Month Charge Battery",
        key="monthchargebattery",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    "YearChargeBattery": AmpereModbusSensorEntityDescription(
        name="Year Charge Battery",
        key="yearchargebattery",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    "TotalChargeBattery": AmpereModbusSensorEntityDescription(
        name="Total Charge Battery",
        key="totalchargebattery",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "DailyDischargeBattery": AmpereModbusSensorEntityDescription(
        name="Daily Discharge Battery",
        key="dailydischargebattery",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "MonthDischargeBattery": AmpereModbusSensorEntityDescription(
        name="Month Discharge Battery",
        key="monthdischargebattery",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    "YearDischargeBattery": AmpereModbusSensorEntityDescription(
        name="Year Discharge Battery",
        key="yeardischargebattery",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_registry_enabled_default=False,
    ),
    "TotalDischargeBattery": AmpereModbusSensorEntityDescription(
        name="Total Discharge Battery",
        key="totaldischargebattery",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    "PvFlowText": AmpereModbusSensorEntityDescription(
        name="PV Flow Text",
        key="pvflowtext",
        icon="mdi:information-outline",
        entity_registry_enabled_default=True,
    ),
    "PvFlow": AmpereModbusSensorEntityDescription(
        name="PV Flow",
        key="pvflow",
        icon="mdi:information-outline",
        entity_registry_enabled_default=True,
    ),
    "BatteryFlowText": AmpereModbusSensorEntityDescription(
        name="Battery Flow Text",
        key="batteryflowtext",
        icon="mdi:information-outline",
        entity_registry_enabled_default=True,
    ),
    "BatteryFlow": AmpereModbusSensorEntityDescription(
        name="Battery Flow",
        key="batteryflow",
        icon="mdi:information-outline",
        entity_registry_enabled_default=True,
    ),
    "GridFlowText": AmpereModbusSensorEntityDescription(
        name="Grid Flow Text",
        key="gridflowtext",
        icon="mdi:information-outline",
        entity_registry_enabled_default=True,
    ),
    "GridFlow": AmpereModbusSensorEntityDescription(
        name="Grid Flow",
        key="gridflow",
        icon="mdi:information-outline",
        entity_registry_enabled_default=True,
    ),
    "DeviceStatus": AmpereModbusSensorEntityDescription(
        name="Device Status",
        key="devicestatus",
        icon="mdi:information-outline",
        entity_registry_enabled_default=True,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    "DeviceError": AmpereModbusSensorEntityDescription(
        name="Device Error",
        key="deviceerror",
        icon="mdi:information-outline",
        entity_registry_enabled_default=True,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}
