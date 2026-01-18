"""Storage handler for RF Connect."""
from __future__ import annotations

import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store
from homeassistant.config_entries import ConfigEntry

from .const import (
    DOMAIN,
    STORAGE_VERSION,
    STORAGE_KEY,
    CONF_RF_CODES,
    RF_DEVICE_ID,
    RF_CHANNEL,
    RF_STATE,
    STATE_ON,
    STATE_OFF,
    DEVICE_TYPE_RELAY,
)

_LOGGER = logging.getLogger(__name__)

# Debounce time in seconds - prevents duplicate events
DEBOUNCE_TIME = 1.0

# Cleanup threshold - remove entries older than this (in seconds)
CLEANUP_THRESHOLD = 60.0


class RFStorage:
    """Handle RF Connect storage."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the storage."""
        self.hass = hass
        self._store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._data: dict[str, Any] = {}
        self._last_event_time: dict[str, float] = {}

    async def async_load(self) -> None:
        """Load data from storage."""
        data = await self._store.async_load()
        if data is not None:
            self._data = data
        else:
            self._data = {"devices": {}}

    async def async_save(self) -> None:
        """Save data to storage."""
        await self._store.async_save(self._data)

    @callback
    def get_device_data(self, entry_id: str) -> dict[str, Any] | None:
        """Get device data by entry ID."""
        return self._data.get("devices", {}).get(entry_id)

    async def async_save_device(self, entry_id: str, data: dict[str, Any]) -> None:
        """Save device data."""
        if "devices" not in self._data:
            self._data["devices"] = {}
        self._data["devices"][entry_id] = data
        await self.async_save()

    async def async_remove_device(self, entry_id: str) -> None:
        """Remove device data."""
        if "devices" in self._data and entry_id in self._data["devices"]:
            self._data["devices"].pop(entry_id)
            await self.async_save()

    async def handle_rf_received(
        self, hass: HomeAssistant, entry: ConfigEntry, event_data: dict[str, Any]
    ) -> None:
        """Handle received RF code and match it to devices.
        
        Uses @callback decorator to ensure atomic execution in the event loop,
        preventing race conditions in debounce logic.
        """
        # ESPHome sends 'device' not 'device_id'
        received_device_id = event_data.get("device") or event_data.get(RF_DEVICE_ID)
        received_channel = event_data.get(RF_CHANNEL)
        received_state = event_data.get(RF_STATE)

        if received_device_id is None or received_channel is None or received_state is None:
            _LOGGER.warning("Incomplete RF code received: %s", event_data)
            return

        # Convert strings to integers
        try:
            received_channel = int(received_channel)
            received_state = int(received_state)
        except (ValueError, TypeError):
            _LOGGER.warning("Invalid channel or state format: %s", event_data)
            return

        _LOGGER.debug("RF code received: device=%s, channel=%s, state=%s", 
                     received_device_id, received_channel, received_state)

        # Get RF codes for this entry
        rf_codes = entry.data.get(CONF_RF_CODES, [])
        
        # Check if this code matches any stored codes
        for rf_code in rf_codes:
            stored_device_id = rf_code.get(RF_DEVICE_ID)
            stored_channel = rf_code.get(RF_CHANNEL)
            state_type = rf_code.get("state_type")

            # Convert both to integers for comparison
            try:
                if isinstance(stored_device_id, str):
                    stored_device_int = int(stored_device_id, 16)
                else:
                    stored_device_int = int(stored_device_id)
                
                if isinstance(received_device_id, str):
                    received_device_int = int(received_device_id, 16) if received_device_id.startswith("0x") else int(received_device_id)
                else:
                    received_device_int = int(received_device_id)
            except (ValueError, TypeError):
                continue

            # Match device_id and channel
            if (
                stored_device_int == received_device_int
                and stored_channel == received_channel
            ):
                # Check for duplicate event within debounce period
                event_key = f"{received_device_int}_{received_channel}_{received_state}"
                current_time = time.time()
                last_time = self._last_event_time.get(event_key, 0)
                
                if current_time - last_time < DEBOUNCE_TIME:
                    _LOGGER.debug(
                        "Skipping duplicate RF event %s (%.2fs since last event, debounce: %.1fs)",
                        event_key,
                        current_time - last_time,
                        DEBOUNCE_TIME
                    )
                    return
                
                # Update last event time
                self._last_event_time[event_key] = current_time
                
                # Cleanup old entries to prevent unbounded memory growth
                # Remove entries older than CLEANUP_THRESHOLD
                keys_to_remove = [
                    key for key, timestamp in self._last_event_time.items()
                    if current_time - timestamp > CLEANUP_THRESHOLD
                ]
                for key in keys_to_remove:
                    del self._last_event_time[key]
                
                if keys_to_remove:
                    _LOGGER.debug("Cleaned up %d old debounce entries", len(keys_to_remove))
                
                # Determine the actual state (on=1, off=0)
                is_on_code = (received_state == STATE_ON)
                is_off_code = (received_state == STATE_OFF)

                _LOGGER.debug("RF code matched! Device: %s, Channel: %s, State type: %s, Received state: %s",
                            received_device_int, received_channel, state_type, received_state)

                # Fire events based on device type
                device_type = entry.data.get("device_type")
                
                if device_type == DEVICE_TYPE_RELAY:
                    # For relay devices, update switch state AND fire button events
                    if is_on_code:
                        # Update switch state
                        hass.bus.async_fire(
                            f"{DOMAIN}_state_update",
                            {
                                "entry_id": entry.entry_id,
                                "state": True,
                            },
                        )
                        # Fire button event
                        hass.bus.async_fire(
                            f"{DOMAIN}_button_pressed",
                            {
                                "entry_id": entry.entry_id,
                                "button_type": "on",
                            },
                        )
                        _LOGGER.debug("Fired state update and button event: ON for entry %s", entry.entry_id)
                        break
                    elif is_off_code:
                        # Update switch state
                        hass.bus.async_fire(
                            f"{DOMAIN}_state_update",
                            {
                                "entry_id": entry.entry_id,
                                "state": False,
                            },
                        )
                        # Fire button event
                        hass.bus.async_fire(
                            f"{DOMAIN}_button_pressed",
                            {
                                "entry_id": entry.entry_id,
                                "button_type": "off",
                            },
                        )
                        _LOGGER.debug("Fired state update and button event: OFF for entry %s", entry.entry_id)
                        break
                else:  # BUTTON
                    # Fire button event based on received state
                    if is_on_code:
                        hass.bus.async_fire(
                            f"{DOMAIN}_button_pressed",
                            {
                                "entry_id": entry.entry_id,
                                "button_type": "on",
                            },
                        )
                        _LOGGER.debug("Fired button event: ON for entry %s", entry.entry_id)
                        break
                    elif is_off_code:
                        hass.bus.async_fire(
                            f"{DOMAIN}_button_pressed",
                            {
                                "entry_id": entry.entry_id,
                                "button_type": "off",
                            },
                        )
                        _LOGGER.debug("Fired button event: OFF for entry %s", entry.entry_id)
                        break

                _LOGGER.debug(
                    "RF code matched for %s: %s (state: %s)",
                    entry.title,
                    received_device_id,
                    "on" if is_on_code else "off",
                )
                break
