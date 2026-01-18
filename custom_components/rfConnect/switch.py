"""Switch platform for RF Connect relay devices."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    CONF_DEVICE_NAME,
    CONF_ESPHOME_ENTITY,
    CONF_RF_CODES,
    ESPHOME_DOMAIN,
    ESPHOME_SERVICE,
    RF_DEVICE_ID,
    RF_CHANNEL,
    STATE_ON,
    STATE_OFF,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RF Connect switch from a config entry."""
    device_name = entry.data[CONF_DEVICE_NAME]
    
    async_add_entities([RFConnectSwitch(hass, entry, device_name)], True)


class RFConnectSwitch(SwitchEntity):
    """Representation of an RF Connect relay switch."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device_name: str,
    ) -> None:
        """Initialize the switch."""
        self.hass = hass
        self._entry = entry
        self._device_name = device_name
        self._attr_unique_id = f"{entry.entry_id}_switch"
        self._attr_is_on = False
        self._esphome_entity = entry.data[CONF_ESPHOME_ENTITY]

        # Device info
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=device_name,
            manufacturer="RF Connect",
            model="RF Relay",
        )

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        # Listen for state updates from RF codes
        @callback
        def handle_state_update(event):
            """Handle state update from RF receiver."""
            if event.data.get("entry_id") == self._entry.entry_id:
                self._attr_is_on = event.data.get("state", False)
                self.async_write_ha_state()

        self.async_on_remove(
            self.hass.bus.async_listen(
                f"{DOMAIN}_state_update", handle_state_update
            )
        )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the relay on."""
        await self._send_rf_command(STATE_ON)
        self._attr_is_on = True
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the relay off."""
        await self._send_rf_command(STATE_OFF)
        self._attr_is_on = False
        self.async_write_ha_state()

    async def _send_rf_command(self, state: int) -> None:
        """Send RF command via ESPHome."""
        rf_codes = self._entry.data.get(CONF_RF_CODES, [])
        
        # Find the appropriate RF code for this state
        state_type = "on" if state == STATE_ON else "off"
        rf_code = None
        
        for code in rf_codes:
            if code.get("state_type") == state_type:
                rf_code = code
                break
        
        if not rf_code:
            _LOGGER.error(
                "No RF code found for %s state on device %s",
                state_type,
                self._device_name,
            )
            return

        device_id = rf_code.get(RF_DEVICE_ID)
        channel = rf_code.get(RF_CHANNEL)

        if device_id is None or channel is None:
            _LOGGER.error("Invalid RF code configuration for %s", self._device_name)
            return

        # Convert hex string to integer
        try:
            if isinstance(device_id, str):
                device_id_int = int(device_id, 16)
            else:
                device_id_int = int(device_id)
        except (ValueError, TypeError) as err:
            _LOGGER.error("Invalid device_id format: %s - %s", device_id, err)
            return

        # Send the RF command via ESPHome
        service_data = {
            "device": device_id_int,
            "channel": channel,
            "state": state,
            "level": 0,  # No dimming
        }

        _LOGGER.debug(
            "Sending RF command: %s to %s (state: %s)",
            service_data,
            self._esphome_entity,
            state_type,
        )

        try:
            await self.hass.services.async_call(
                ESPHOME_DOMAIN,
                ESPHOME_SERVICE,
                service_data,
                blocking=True,
            )
        except Exception as err:
            _LOGGER.error("Failed to send RF command: %s", err)

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True
