"""The RF Connect integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, Event, callback
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    CONF_ESPHOME_ENTITY,
    CONF_DEVICE_TYPE,
    DEVICE_TYPE_RELAY,
    DEVICE_TYPE_BUTTON,
    ESPHOME_EVENT,
)
from .storage import RFStorage

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SWITCH, Platform.EVENT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up RF Connect from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    
    # Initialize storage
    storage = RFStorage(hass)
    await storage.async_load()
    hass.data[DOMAIN][entry.entry_id] = {
        "storage": storage,
        "esphome_entity": entry.data[CONF_ESPHOME_ENTITY],
    }

    # Set up platforms based on device type
    device_type = entry.data.get(CONF_DEVICE_TYPE)
    platforms_to_load = []
    
    if device_type == DEVICE_TYPE_RELAY:
        # Relay devices get both switch (for control) and event (for press detection)
        platforms_to_load.append(Platform.SWITCH)
        platforms_to_load.append(Platform.EVENT)
    elif device_type == DEVICE_TYPE_BUTTON:
        # Button devices only get event entities
        platforms_to_load.append(Platform.EVENT)
    
    if platforms_to_load:
        await hass.config_entries.async_forward_entry_setups(entry, platforms_to_load)

    # Listen for RF codes from ESPHome
    async def handle_rf_received(event: Event) -> None:
        """Handle RF code received from ESPHome."""
        await storage.handle_rf_received(hass, entry, event.data)

    entry.async_on_unload(
        hass.bus.async_listen(ESPHOME_EVENT, handle_rf_received)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    device_type = entry.data.get(CONF_DEVICE_TYPE)
    platforms_to_unload = []
    
    if device_type == DEVICE_TYPE_RELAY:
        platforms_to_unload.append(Platform.SWITCH)
    elif device_type == DEVICE_TYPE_BUTTON:
        platforms_to_unload.append(Platform.EVENT)
    
    if platforms_to_unload:
        unload_ok = await hass.config_entries.async_unload_platforms(
            entry, platforms_to_unload
        )
    else:
        unload_ok = True

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle removal of an entry."""
    if entry.entry_id in hass.data.get(DOMAIN, {}):
        storage: RFStorage = hass.data[DOMAIN][entry.entry_id]["storage"]
        await storage.async_remove_device(entry.entry_id)
