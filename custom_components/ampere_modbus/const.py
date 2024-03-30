DOMAIN = "ampere_storage_pro_modbus"
ATTR_MANUFACTURER = "Ampere"

CONF_UNIT = "unit"

DEFAULT_NAME = "AmpereStoragePro"
DEFAULT_SCAN_INTERVAL = 15
DEFAULT_PORT = 502
DEFAULT_UNIT = 2

PV_DIRECTION = {
    0: "No output",
    1: "Output",
}

BATTERY_DIRECTION = {
    1: "Battery discharge",
    0: "No battery flow",
    -1: "Battery charge",
}

GRID_DIRECTION = {
    1: "Grid output",
    0: "No grid flow",
    -1: "Grid input",
}
