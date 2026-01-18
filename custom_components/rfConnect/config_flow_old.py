"""Config flow for RF Connect integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_ESPHOME_ENTITY,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TYPE,
    CONF_RF_CODES,
    DEVICE_TYPE_RELAY,
    DEVICE_TYPE_BUTTON,
    RF_DEVICE_ID,
    RF_CHANNEL,
    RF_STATE,
)

_LOGGER = logging.getLogger(__name__)


class RFConnectConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RF Connect."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._esphome_entity: str | None = None
        self._device_name: str | None = None
        self._device_type: str | None = None
        self._rf_codes: list[dict[str, Any]] = []
        self._learned_code: dict[str, Any] | None = None
        self._timeout_task: Any | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - ESPHome entity selection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._esphome_entity = user_input[CONF_ESPHOME_ENTITY]
            return await self.async_step_device_setup()

        schema = vol.Schema(
            {
                vol.Required(CONF_ESPHOME_ENTITY, default="esphome.espHomeRF"): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "description": "Enter the ESPHome entity ID for your RF controller"
            },
        )

    async def async_step_device_setup(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle device name and type selection."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._device_name = user_input[CONF_DEVICE_NAME]
            self._device_type = user_input[CONF_DEVICE_TYPE]
            
            # Go to RF code learning
            return await self.async_step_learn_rf_code()

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_NAME): str,
                vol.Required(CONF_DEVICE_TYPE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            {"label": "Relay (Switch)", "value": DEVICE_TYPE_RELAY},
                            {"label": "Button (Events)", "value": DEVICE_TYPE_BUTTON},
                        ],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="device_setup",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_learn_rf_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Learn the RF code (device_id and channel)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input.get("learn_from_remote"):
                # Start listening for RF codes
                return await self.async_step_listen_rf()
            
            # Manual entry
            try:
                device_id = user_input[RF_DEVICE_ID].strip()
                if not device_id.startswith("0x"):
                    device_id = f"0x{device_id}"
                
                channel = int(user_input[RF_CHANNEL])
                
                # Create both ON and OFF codes with the same device_id and channel
                self._rf_codes = [
                    {
                        RF_DEVICE_ID: device_id,
                        RF_CHANNEL: channel,
                        "state_type": "on",
                    },
                    {
                        RF_DEVICE_ID: device_id,
                        RF_CHANNEL: channel,
                        "state_type": "off",
                    },
                ]
                
                # Create the config entry
                return self.async_create_entry(
                    title=self._device_name or "RF Device",
                    data={
                        CONF_ESPHOME_ENTITY: self._esphome_entity,
                        CONF_DEVICE_NAME: self._device_name,
                        CONF_DEVICE_TYPE: self._device_type,
                        CONF_RF_CODES: self._rf_codes,
                    },
                )
            except (ValueError, KeyError):
                errors["base"] = "invalid_rf_code"

        schema = vol.Schema(
            {
                vol.Optional("learn_from_remote", default=False): bool,
                vol.Optional(RF_DEVICE_ID, default=""): str,
                vol.Optional(RF_CHANNEL, default=1): int,
            }
        )

        return self.async_show_form(
            step_id="learn_rf_code",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "device_name": self._device_name or "Device",
                "instruction": f"Check 'Learn from remote' and press Next, then press your RF button. Or enter device_id and channel manually.",
            },
        )

    async def async_step_manual_input(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manually input RF code."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device_id = user_input.get(RF_DEVICE_ID)
            channel = user_input.get(RF_CHANNEL)
            state_type = user_input.get("state_type")
            
            if device_id and channel is not None and state_type:
                try:
                    if not device_id.startswith("0x"):
                        device_id = f"0x{device_id}"
                    
                    # Add the code
                    self._rf_codes.append({
                        RF_DEVICE_ID: device_id,
                        RF_CHANNEL: int(channel),
                        "state_type": state_type,
                    })
                    
                    # Ask if they want to add another
                    return await self.async_step_add_another()
                except (ValueError, KeyError):
                    errors["base"] = "invalid_rf_code"
            else:
                errors["base"] = "invalid_rf_code"

        return self.async_show_form(
            step_id="manual_input",
            data_schema=vol.Schema({
                vol.Required(RF_DEVICE_ID): str,
                vol.Required(RF_CHANNEL, default=1): int,
                vol.Required("state_type"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["on", "off"],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }),
            errors=errors,
            description_placeholders={
                "device_name": self._device_name or "Device",
            },
        )

    async def async_step_listen_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Listen for RF code from ESPHome."""
        if user_input is not None:
            # Check if user wants to enter manually
            if user_input.get("manual_entry"):
                _LOGGER.info("User selected manual entry, returning to learn_rf_code step")
                return await self.async_step_learn_rf_code()
            
            # User confirmed or cancelled
            if self._learned_code:
                # Create both ON and OFF codes
                self._rf_codes = [
                    {
                        RF_DEVICE_ID: self._learned_code[RF_DEVICE_ID],
                        RF_CHANNEL: self._learned_code[RF_CHANNEL],
                        "state_type": "on",
                    },
                    {
                        RF_DEVICE_ID: self._learned_code[RF_DEVICE_ID],
                        RF_CHANNEL: self._learned_code[RF_CHANNEL],
                        "state_type": "off",
                    },
                ]
                
                # Create the config entry
                return self.async_create_entry(
                    title=self._device_name or "RF Device",
                    data={
                        CONF_ESPHOME_ENTITY: self._esphome_entity,
                        CONF_DEVICE_NAME: self._device_name,
                        CONF_DEVICE_TYPE: self._device_type,
                        CONF_RF_CODES: self._rf_codes,
                    },
                )
            else:
                return await self.async_step_learn_rf_code()

        # Listen for RF code event
        @callback
        def rf_code_received(event):
            """Handle RF code received."""
            device = event.data.get("device")
            channel = event.data.get(RF_CHANNEL)
            state = event.data.get(RF_STATE)
            
            _LOGGER.info(f"Config flow received RF code: device={device}, channel={channel}, state={state}")
            
            if device and channel and state == "1":  # Only capture ON codes
                try:
                    channel_int = int(channel)
                    if not device or device == "0x":  # Validate device ID
                        _LOGGER.warning(f"Invalid device ID received: {device}")
                        return
                    
                    self._learned_code = {
                        RF_DEVICE_ID: device,
                        RF_CHANNEL: channel_int,
                    }
                    _LOGGER.info(f"Successfully captured RF code: {device} channel {channel_int}")
                    # Continue the flow
                    self.hass.async_create_task(
                        self.hass.config_entries.flow.async_configure(
                            flow_id=self.flow_id, user_input={}
                        )
                    )
                except (ValueError, TypeError) as err:
                    _LOGGER.error(f"Error parsing RF code: {err}")

        # Register listener
        self.hass.bus.async_listen_once("esphome.rf_code_received", rf_code_received)

        # If we have a learned code, show it and create the device
        if self._learned_code:
            device_id = self._learned_code.get(RF_DEVICE_ID)
            channel = self._learned_code.get(RF_CHANNEL)
            
            # Create the device entry directly
            rf_codes = []
            rf_codes.append({RF_DEVICE_ID: device_id, RF_CHANNEL: channel, "state_type": "on"})
            rf_codes.append({RF_DEVICE_ID: device_id, RF_CHANNEL: channel, "state_type": "off"})
            
            return self.async_create_entry(
                title=self._device_name,
                data={
                    CONF_ESPHOME_ENTITY: self._esphome_entity,
                    CONF_DEVICE_NAME: self._device_name,
                    CONF_DEVICE_TYPE: self._device_type,
                    CONF_RF_CODES: rf_codes,
                },
            )

        # Show form with waiting message and manual entry option
        return self.async_show_form(
            step_id="listen_rf",
            data_schema=vol.Schema({
                vol.Optional("manual_entry", default=False): bool,
            }),
            description_placeholders={
                "device_name": self._device_name or "Device",
                "instruction": f"Press the ON button on your RF remote for '{self._device_name}' now...",
            },
        )

    async def async_step_add_another(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask if user wants to add another code."""
        if user_input is not None:
            if user_input.get("add_another"):
                # Go back to learn more codes
                return await self.async_step_learn_codes()
            else:
                # Complete - create the entry
                if not self._rf_codes:
                    # No codes added, go back
                    return await self.async_step_learn_codes()
                
                return self.async_create_entry(
                    title=self._device_name or "RF Device",
                    data={
                        CONF_ESPHOME_ENTITY: self._esphome_entity,
                        CONF_DEVICE_NAME: self._device_name,
                        CONF_DEVICE_TYPE: self._device_type,
                        CONF_RF_CODES: self._rf_codes,
                    },
                )

        # Show form asking if they want to add another
        return self.async_show_form(
            step_id="add_another",
            data_schema=vol.Schema({
                vol.Required("add_another", default=False): bool,
            }),
            description_placeholders={
                "device_name": self._device_name or "Device",
                "code_count": str(len(self._rf_codes) // 2),
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> RFConnectOptionsFlow:
        """Get the options flow for this handler."""
        return RFConnectOptionsFlow(config_entry)


class RFConnectOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for RF Connect."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry
        self._learned_code: dict[str, Any] | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        return await self.async_step_menu()

    async def async_step_menu(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show the menu."""
        return self.async_show_menu(
            step_id="menu",
            menu_options=["add_rf_code", "remove_rf_code", "delete_device"],
        )

    async def async_step_add_rf_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Add a new RF code to the device."""
        errors: dict[str, str] = {}

        if user_input is not None:
            # Check if user wants automatic learning
            if user_input.get("learn_from_remote"):
                return await self.async_step_listen_rf_options()
            
            try:
                device_id = user_input[RF_DEVICE_ID].strip()
                if not device_id.startswith("0x"):
                    device_id = f"0x{device_id}"
                
                # Get current RF codes
                rf_codes = list(self._config_entry.data.get(CONF_RF_CODES, []))
                
                # Add new code
                rf_codes.append({
                    RF_DEVICE_ID: device_id,
                    RF_CHANNEL: int(user_input[RF_CHANNEL]),
                    "state_type": user_input["state_type"],
                })
                
                # Update config entry
                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    data={**self._config_entry.data, CONF_RF_CODES: rf_codes},
                )
                
                return self.async_create_entry(title="", data={})
            except (ValueError, KeyError):
                errors["base"] = "invalid_rf_code"

        schema = vol.Schema(
            {
                vol.Optional("learn_from_remote", default=False): bool,
                vol.Optional(RF_DEVICE_ID): str,
                vol.Optional(RF_CHANNEL, default=1): int,
                vol.Optional("state_type"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["on", "off"],
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="add_rf_code",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_remove_rf_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Remove an RF code from the device."""
        rf_codes = self._config_entry.data.get(CONF_RF_CODES, [])
        
        if not rf_codes:
            return self.async_abort(reason="no_codes")

        if user_input is not None:
            # Get the selected device_id and channel
            selected = user_input["code_index"]
            device_id, channel = selected.split("|")
            channel = int(channel)
            
            # Remove all codes with this device_id and channel (both ON and OFF)
            rf_codes = [
                code for code in rf_codes
                if not (code.get(RF_DEVICE_ID) == device_id and code.get(RF_CHANNEL) == channel)
            ]
            
            # Update config entry
            self.hass.config_entries.async_update_entry(
                self._config_entry,
                data={**self._config_entry.data, CONF_RF_CODES: rf_codes},
            )
            
            return self.async_create_entry(title="", data={})

        # Group codes by device_id + channel (unique combinations)
        unique_codes = {}
        for code in rf_codes:
            device_id = code.get(RF_DEVICE_ID)
            channel = code.get(RF_CHANNEL)
            key = f"{device_id}|{channel}"
            if key not in unique_codes:
                unique_codes[key] = {
                    "device_id": device_id,
                    "channel": channel,
                }
        
        # Create options for selection
        options = [
            {
                "label": f"{info['device_id']} channel {info['channel']}",
                "value": key,
            }
            for key, info in unique_codes.items()
        ]

        schema = vol.Schema(
            {
                vol.Required("code_index"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=options,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        return self.async_show_form(step_id="remove_rf_code", data_schema=schema)

    async def async_step_listen_rf_options(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Listen for RF code from ESPHome (options flow)."""
        if user_input is not None:
            # Check if user wants manual entry
            if user_input.get("manual_entry"):
                return await self.async_step_add_rf_code()
            
            # If we have learned code, add it
            if hasattr(self, "_learned_code") and self._learned_code:
                device_id = self._learned_code.get(RF_DEVICE_ID)
                channel = self._learned_code.get(RF_CHANNEL)
                
                # Get current RF codes
                rf_codes = list(self._config_entry.data.get(CONF_RF_CODES, []))
                
                # Add both ON and OFF codes
                rf_codes.append({RF_DEVICE_ID: device_id, RF_CHANNEL: channel, "state_type": "on"})
                rf_codes.append({RF_DEVICE_ID: device_id, RF_CHANNEL: channel, "state_type": "off"})
                
                # Update config entry
                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    data={**self._config_entry.data, CONF_RF_CODES: rf_codes},
                )
                
                # Clear learned code
                self._learned_code = None
                
                return self.async_create_entry(title="", data={})

        # Set up listener
        @callback
        def rf_code_received(event):
            """Handle RF code received."""
            device = event.data.get("device")
            channel = event.data.get(RF_CHANNEL)
            state = event.data.get(RF_STATE)
            
            _LOGGER.info(f"Options flow received RF code: device={device}, channel={channel}, state={state}")
            
            if device and channel and state == "1":
                try:
                    channel_int = int(channel)
                    if not device or device == "0x":
                        _LOGGER.warning(f"Invalid device ID received: {device}")
                        return
                    
                    self._learned_code = {
                        RF_DEVICE_ID: device,
                        RF_CHANNEL: channel_int,
                    }
                    _LOGGER.info(f"Successfully captured RF code in options: {device} channel {channel_int}")
                    self.hass.async_create_task(
                        self.hass.config_entries.options.async_configure(
                            flow_id=self.flow_id, user_input={}
                        )
                    )
                except (ValueError, TypeError) as err:
                    _LOGGER.error(f"Error parsing RF code in options: {err}")

        # Register listener
        self.hass.bus.async_listen_once("esphome.rf_code_received", rf_code_received)

        # If we captured a code, add it
        if hasattr(self, "_learned_code") and self._learned_code:
            device_id = self._learned_code.get(RF_DEVICE_ID)
            channel = self._learned_code.get(RF_CHANNEL)
            
            # Get current RF codes
            rf_codes = list(self._config_entry.data.get(CONF_RF_CODES, []))
            
            # Add both ON and OFF codes
            rf_codes.append({RF_DEVICE_ID: device_id, RF_CHANNEL: channel, "state_type": "on"})
            rf_codes.append({RF_DEVICE_ID: device_id, RF_CHANNEL: channel, "state_type": "off"})
            
            # Update config entry
            self.hass.config_entries.async_update_entry(
                self._config_entry,
                data={**self._config_entry.data, CONF_RF_CODES: rf_codes},
            )
            
            # Clear learned code
            self._learned_code = None
            
            return self.async_create_entry(title="", data={})

        # Show waiting form
        return self.async_show_form(
            step_id="listen_rf_options",
            data_schema=vol.Schema({
                vol.Optional("manual_entry", default=False): bool,
            }),
            description_placeholders={
                "device_name": self._config_entry.data.get(CONF_DEVICE_NAME, "device"),
            },
        )

    async def async_step_delete_device(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Delete the device."""
        if user_input is not None:
            if user_input.get("confirm"):
                await self.hass.config_entries.async_remove(self._config_entry.entry_id)
                return self.async_create_entry(title="", data={})
            return self.async_abort(reason="not_confirmed")

        schema = vol.Schema(
            {
                vol.Required("confirm", default=False): bool,
            }
        )

        return self.async_show_form(
            step_id="delete_device",
            data_schema=schema,
            description_placeholders={
                "device_name": self._config_entry.title,
            },
        )
