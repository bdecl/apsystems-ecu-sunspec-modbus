"""Constants for the APsystems ECU SunSpec integration."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "apsystems_ecu_sunspec"
MANUFACTURER = "APsystems"

CONF_LAST_UNIT = "last_unit"
CONF_UNITS = "units"
CONF_CONTROL_UNIT = "control_unit"
CONF_CONTROLS = "controls"
CONF_KEEPALIVE = "limit_keepalive"

DEFAULT_PORT = 502
DEFAULT_LAST_UNIT = 32
DEFAULT_SCAN_INTERVAL = 10  # s; the ECU itself refreshes inverter data far less often
MIN_SCAN_INTERVAL = 5
DEFAULT_KEEPALIVE = 0  # s, 0 = do not rewrite the power limit periodically
READ_TIMEOUT = 3.0
STALE_AFTER = 900  # s without any change in the measurements: inverter asleep (ECU round ~5 min)

ECU_DEVICE_NAME = "APsystems ECU"
INVERTER_DEVICE_NAME = "APsystems inverter {unit}"

PLATFORMS = [Platform.NUMBER, Platform.SENSOR, Platform.SWITCH]
