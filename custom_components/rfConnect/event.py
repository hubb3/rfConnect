"""Event platform for RF Connect button devices."""
from __future__ import annotations

import logging

from homeassistant.components.event import EventEntity, EventDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    CONF_DEVICE_NAME,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up RF Connect event entities from a config entry."""
    device_name = entry.data[CONF_DEVICE_NAME]
    
    # Create two event entities: one for "on" and one for "off"
    async_add_entities(
        [
            RFConnectButtonEvent(hass, entry, device_name, "on"),
            RFConnectButtonEvent(hass, entry, device_name, "off"),
        ],
        True,
    )


class RFConnectButtonEvent(EventEntity):
    """Representation of an RF Connect button event."""

    _attr_has_entity_name = True
    _attr_event_types = ["pressed"]
    _attr_device_class = EventDeviceClass.BUTTON

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device_name: str,
        button_type: str,
    ) -> None:
        """Initialize the button event."""
        self.hass = hass
        self._entry = entry
        self._device_name = device_name
        self._button_type = button_type
        self._attr_unique_id = f"{entry.entry_id}_button_{button_type}"
        self._attr_name = f"Pressed {button_type.upper()}"

        # Device info
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=device_name,
            manufacturer="RF Connect",
            model="RF Button",
        )

    async def async_added_to_hass(self) -> None:
        """Run when entity about to be added to hass."""
        await super().async_added_to_hass()

        # Listen for button press events
        @callback
        def handle_button_press(event):
            """Handle button press from RF receiver."""
            if (
                event.data.get("entry_id") == self._entry.entry_id
                and event.data.get("button_type") == self._button_type
            ):
                self._trigger_event("pressed")
                self.async_write_ha_state()

        self.async_on_remove(
            self.hass.bus.async_listen(
                f"{DOMAIN}_button_pressed", handle_button_press
            )
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return True
