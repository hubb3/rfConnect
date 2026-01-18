"""Config flow for RF Connect integration."""
from __future__ import annotations

import asyncio
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

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - select ESPHome entity."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._esphome_entity = user_input[CONF_ESPHOME_ENTITY]
            return await self.async_step_device_setup()

        schema = vol.Schema(
            {
                vol.Required(CONF_ESPHOME_ENTITY, default="esphome.esphomeRF"): str,
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_device_setup(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Configure device name and type."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._device_name = user_input[CONF_DEVICE_NAME]
            self._device_type = user_input[CONF_DEVICE_TYPE]
            return await self.async_step_learn_codes()

        schema = vol.Schema(
            {
                vol.Required(CONF_DEVICE_NAME): str,
                vol.Required(CONF_DEVICE_TYPE): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[
                            selector.SelectOptionDict(value=DEVICE_TYPE_RELAY, label="RF Relay (Switch)"),
                            selector.SelectOptionDict(value=DEVICE_TYPE_BUTTON, label="RF Button (Event)"),
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

    async def async_step_learn_codes(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Learn RF codes - all-in-one page with auto-updating counter."""
        _LOGGER.info(f"learn_codes called with user_input: {user_input}")
        
        # Check if user wants manual input or is done
        if user_input is not None:
            if user_input.get("manual_input"):
                return await self.async_step_manual_input()
            
            if user_input.get("done"):
                if not self._rf_codes:
                    return self.async_show_form(
                        step_id="learn_codes",
                        data_schema=vol.Schema({
                            vol.Optional("manual_input", default=False): bool,
                            vol.Optional("done", default=False): bool,
                        }),
                        errors={"base": "invalid_rf_code"},
                        description_placeholders={
                            "device_name": self._device_name or "Device",
                            "code_count": "0",
                        },
                    )
                
                return self.async_create_entry(
                    title=self._device_name or "RF Device",
                    data={
                        CONF_ESPHOME_ENTITY: self._esphome_entity,
                        CONF_DEVICE_NAME: self._device_name,
                        CONF_DEVICE_TYPE: self._device_type,
                        CONF_RF_CODES: self._rf_codes,
                    },
                )

        # Set up continuous listener until user clicks done
        if not hasattr(self, '_listener_active'):
            _LOGGER.info("Setting up continuous RF listener")
            self._listener_active = True
            
            @callback
            def rf_code_received(event):
                """Handle RF code."""
                device = event.data.get("device")
                channel = event.data.get(RF_CHANNEL)
                state = event.data.get(RF_STATE)
                
                _LOGGER.info(f"RF code: device={device}, ch={channel}, state={state}")
                
                if device and channel:
                    try:
                        channel_int = int(channel)
                        if not device or device == "0x":
                            return
                        
                        if state == "1":
                            # Add code on state ON
                            # Check if code already exists
                            already_exists = any(
                                code.get(RF_DEVICE_ID) == device and code.get(RF_CHANNEL) == channel_int
                                for code in self._rf_codes
                            )
                            
                            if already_exists:
                                _LOGGER.info(f"Code already exists: {device} ch{channel_int}")
                                return
                            
                            self._rf_codes.append({RF_DEVICE_ID: device, RF_CHANNEL: channel_int, "state_type": "on"})
                            self._rf_codes.append({RF_DEVICE_ID: device, RF_CHANNEL: channel_int, "state_type": "off"})
                            
                            _LOGGER.info(f"Captured: {device} ch{channel_int}. Total codes: {len(self._rf_codes) // 2}")
                        
                        elif state == "0":
                            # Remove code on state OFF
                            initial_count = len(self._rf_codes)
                            self._rf_codes = [
                                code for code in self._rf_codes
                                if not (code.get(RF_DEVICE_ID) == device and code.get(RF_CHANNEL) == channel_int)
                            ]
                            removed_count = initial_count - len(self._rf_codes)
                            if removed_count > 0:
                                _LOGGER.info(f"Removed: {device} ch{channel_int}. Total codes: {len(self._rf_codes) // 2}")
                            else:
                                _LOGGER.info(f"Code not found to remove: {device} ch{channel_int}")
                    except (ValueError, TypeError) as err:
                        _LOGGER.error(f"Parse error: {err}")

            self.hass.bus.async_listen("esphome.rf_code_received", rf_code_received)

        # Build list of learned codes for display
        code_count = len(self._rf_codes) // 2
        code_list = ""
        
        if code_count > 0:
            seen_codes = set()
            for code in self._rf_codes:
                device_id = code.get(RF_DEVICE_ID)
                channel = code.get(RF_CHANNEL)
                code_key = f"{device_id}_ch{channel}"
                
                if code_key not in seen_codes:
                    seen_codes.add(code_key)
                    code_list += f"\n  • {device_id} Channel {channel}"
        else:
            code_list = "\n  (none yet)"
        
        return self.async_show_form(
            step_id="learn_codes",
            data_schema=vol.Schema({
                vol.Optional("done", default=False): bool,
                vol.Optional("manual_input", default=False): bool,
            }),
            description_placeholders={
                "device_name": self._device_name or "Device",
                "code_count": str(code_count),
                "code_list": code_list,
            },
        )
    
    async def _async_rerender(self, code_received: bool = False, timeout: bool = False) -> None:
        """Helper to re-render the learn_codes form."""
        user_input = {}
        if code_received:
            user_input["code_received"] = True
        if timeout:
            user_input["timeout"] = True
        
        await self.hass.config_entries.flow.async_configure(
            flow_id=self.flow_id, user_input=user_input
        )

    async def async_step_listen_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Start listening - go directly to codes_learned which handles listening."""
        return await self.async_step_codes_learned()

    async def async_step_codes_learned(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Show learned codes and ask if user wants to continue."""
        _LOGGER.info(f"codes_learned called with user_input: {user_input}")
        
        # Cancel existing timeout if any
        if self._timeout_task:
            _LOGGER.info("Cancelling existing timeout")
            self._timeout_task.cancel()
            self._timeout_task = None
        
        # Check if this is actual user interaction (has "done" key from form submission)
        # vs automatic trigger from code received/timeout
        if user_input is not None and "done" in user_input:
            _LOGGER.info(f"User interaction detected. Done={user_input.get('done')}")
            # User clicked Submit on the form
            if user_input.get("done"):
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
            else:
                # User wants to learn another - restart this step
                _LOGGER.info("User wants to learn another code, restarting")
                return await self.async_step_codes_learned()

        # Set up listener and timeout (only on first call or when learning another)
        if user_input is None or (user_input.get("done") == False and "done" in user_input):
            _LOGGER.info("Setting up RF code listener and 10-second timeout")
            
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
                        
                        # Cancel timeout
                        if self._timeout_task:
                            self._timeout_task.cancel()
                            self._timeout_task = None
                        
                        # Add both ON and OFF codes immediately
                        self._rf_codes.append({RF_DEVICE_ID: device, RF_CHANNEL: channel_int, "state_type": "on"})
                        self._rf_codes.append({RF_DEVICE_ID: device, RF_CHANNEL: channel_int, "state_type": "off"})
                        
                        _LOGGER.info(f"Successfully captured RF code: {device} channel {channel_int}. Triggering re-render.")
                        
                        # Re-render this step with code_received flag
                        self.hass.async_create_task(
                            self.hass.config_entries.flow.async_configure(
                                flow_id=self.flow_id, user_input={"code_received": True}
                            )
                        )
                    except (ValueError, TypeError) as err:
                        _LOGGER.error(f"Error parsing RF code: {err}")

            @callback
            def timeout_handler():
                """Handle timeout - no code received."""
                _LOGGER.warning("Timeout waiting for RF code. Triggering re-render.")
                self._timeout_task = None
                # Re-render this step with timeout flag
                self.hass.async_create_task(
                    self.hass.config_entries.flow.async_configure(
                        flow_id=self.flow_id, user_input={"timeout": True}
                    )
                )

            # Register listener and timeout
            self.hass.bus.async_listen_once("esphome.rf_code_received", rf_code_received)
            self._timeout_task = self.hass.loop.call_later(10, timeout_handler)
            _LOGGER.info("Listener and timeout registered successfully")

        # Build list of learned codes for display
        code_count = len(self._rf_codes) // 2
        codes_list = []
        seen = set()
        for code in self._rf_codes:
            key = (code[RF_DEVICE_ID], code[RF_CHANNEL])
            if key not in seen:
                seen.add(key)
                codes_list.append(f"{code[RF_DEVICE_ID]} ch{code[RF_CHANNEL]}")
        
        codes_display = "\n".join(codes_list) if codes_list else "No codes learned yet"
        
        # Check if this was triggered by timeout
        timeout_msg = ""
        if user_input and user_input.get("timeout"):
            timeout_msg = "\n\n⏱️ No code received (timeout). Try again or finish."
        elif user_input and user_input.get("code_received"):
            timeout_msg = "\n\n✅ Code received!"

        return self.async_show_form(
            step_id="codes_learned",
            data_schema=vol.Schema({
                vol.Required("done", default=False): bool,
                vol.Optional("code_received"): bool,
                vol.Optional("timeout"): bool,
            }),
            description_placeholders={
                "device_name": self._device_name or "Device",
                "code_count": str(code_count),
                "codes_list": codes_display + timeout_msg,
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
                    
                    # Go back to learn_codes
                    return await self.async_step_learn_codes({"code_received": True})
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
        code_count = len(self._rf_codes) // 2
        return self.async_show_form(
            step_id="add_another",
            data_schema=vol.Schema({
                vol.Required("add_another", default=False): bool,
            }),
            description_placeholders={
                "device_name": self._device_name or "Device",
                "code_count": str(code_count),
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
        if user_input is not None:
            code_index = int(user_input["code_index"])
            rf_codes = list(self._config_entry.data.get(CONF_RF_CODES, []))
            
            if 0 <= code_index < len(rf_codes):
                # Get the device_id and channel to remove both ON and OFF
                removed_code = rf_codes[code_index]
                device_id = removed_code[RF_DEVICE_ID]
                channel = removed_code[RF_CHANNEL]
                
                # Remove all codes with same device_id and channel
                rf_codes = [
                    code for code in rf_codes
                    if not (code[RF_DEVICE_ID] == device_id and code[RF_CHANNEL] == channel)
                ]
                
                self.hass.config_entries.async_update_entry(
                    self._config_entry,
                    data={**self._config_entry.data, CONF_RF_CODES: rf_codes},
                )
            
            return self.async_create_entry(title="", data={})

        # Get RF codes grouped by device_id + channel
        rf_codes = self._config_entry.data.get(CONF_RF_CODES, [])
        if not rf_codes:
            return self.async_abort(reason="no_codes")

        # Group codes by device_id + channel
        seen = set()
        options = []
        for idx, code in enumerate(rf_codes):
            key = (code[RF_DEVICE_ID], code[RF_CHANNEL])
            if key not in seen:
                seen.add(key)
                options.append(
                    selector.SelectOptionDict(
                        value=str(idx),
                        label=f"{code[RF_DEVICE_ID]} channel {code[RF_CHANNEL]}",
                    )
                )

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
                "device_name": self._config_entry.data.get(CONF_DEVICE_NAME, "Unknown"),
            },
        )
