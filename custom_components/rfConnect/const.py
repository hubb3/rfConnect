"""Constants for the RF Connect integration."""

DOMAIN = "rfconnect"

# Configuration
CONF_ESPHOME_ENTITY = "esphome_entity"
CONF_DEVICE_NAME = "device_name"
CONF_DEVICE_TYPE = "device_type"
CONF_RF_CODES = "rf_codes"

# Device types
DEVICE_TYPE_RELAY = "relay"
DEVICE_TYPE_BUTTON = "button"

# ESPHome service and event
ESPHOME_DOMAIN = "esphome"
ESPHOME_SERVICE = "esphomerf_rf_code_send"
ESPHOME_EVENT = "esphome.rf_code_received"

# RF Code fields
RF_DEVICE_ID = "device_id"
RF_CHANNEL = "channel"
RF_STATE = "state"

# States
STATE_ON = 1
STATE_OFF = 0

# Storage
STORAGE_VERSION = 1
STORAGE_KEY = "rfconnect_devices"
