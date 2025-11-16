"""The Ampere Storage Pro Modbus Integration."""

import asyncio
import logging

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT, CONF_SCAN_INTERVAL, CONF_SCAN_INTERVAL_LONG
from homeassistant.core import HomeAssistant

from .const import (
    CONF_UNIT,
    DEFAULT_NAME,
    DEFAULT_UNIT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SCAN_INTERVAL_LONG,
    DOMAIN,
)
from .hub import AmpereStorageProModbusHub

_LOGGER = logging.getLogger(__name__)

AMPERE_MODBUS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
        vol.Required(CONF_HOST): cv.string,
        vol.Required(CONF_PORT): cv.string,
        vol.Required(CONF_UNIT, default=DEFAULT_UNIT): cv.positive_int,
        vol.Optional(
            CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
        ): cv.positive_int,
        vol.Optional(
            CONF_SCAN_INTERVAL_LONG, default=DEFAULT_SCAN_INTERVAL_LONG
        ): cv.positive_int,
    }
)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema({cv.slug: AMPERE_MODBUS_SCHEMA})}, extra=vol.ALLOW_EXTRA
)

PLATFORMS = ["sensor"]


async def async_setup(hass, config):
    """Set up the Ampere Storage Pro modbus component."""
    hass.data[DOMAIN] = {}
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up a Ampere Storage Pro mobus."""
    host = entry.data[CONF_HOST]
    name = entry.data[CONF_NAME]
    port = entry.data[CONF_PORT]
    unit = entry.data[CONF_UNIT]
    scan_interval = entry.data[CONF_SCAN_INTERVAL]
    scan_interval_long = entry.data[CONF_SCAN_INTERVAL_LONG]

    _LOGGER.debug("Setup %s.%s", DOMAIN, name)

    hub = AmpereStorageProModbusHub(hass, name, host, port, unit, scan_interval, scan_interval_long)
    await hub.async_config_entry_first_refresh()

    """Register the hub."""
    hass.data[DOMAIN][name] = {"hub": hub}

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass, entry):
    """Unload Ampere Storage Pro mobus entry."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.data["name"])
    return unloaded
