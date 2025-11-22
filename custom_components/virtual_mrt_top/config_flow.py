"""Config flow for Virtual MRT integration."""

from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.selector import SelectSelectorMode

from .const import (
    DOMAIN,
    CONF_ROOM_PROFILE,
    ROOM_PROFILES,
    CONF_ORIENTATION,
    ORIENTATION_OPTIONS,
    CONF_AIR_TEMP_SOURCE,
    CONF_WEATHER_ENTITY,
    CONF_SOLAR_SENSOR,
)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Virtual MRT."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        profile_keys = list(ROOM_PROFILES.keys())

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_AIR_TEMP_SOURCE): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="sensor", device_class="temperature"
                        )
                    ),
                    vol.Required(CONF_WEATHER_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="weather")
                    ),
                    vol.Required(
                        CONF_ROOM_PROFILE, default="one_wall_large_window"
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=profile_keys,
                            mode=SelectSelectorMode.DROPDOWN,
                            translation_key="room_profile",
                        )
                    ),
                    vol.Required(
                        CONF_ORIENTATION, default="S"
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=ORIENTATION_OPTIONS,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(CONF_SOLAR_SENSOR): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> OptionsFlowHandler:
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handles options flow for the component."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            # We must merge new options with old data
            # This ensures CONF_AIR_TEMP_SOURCE and CONF_ROOM_PROFILE are preserved
            new_data = self.config_entry.data.copy()
            new_data.update(user_input)

            # This is a bit of a trick: we update the main config entry data
            # instead of just creating options. This is cleaner for this integration.
            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            # The __init__.py update listener will handle the reload
            return self.async_create_entry(title="", data=None)

        # Get current values to pre-populate the form
        orientation = self.config_entry.data.get(CONF_ORIENTATION, "S")
        weather = self.config_entry.data.get(CONF_WEATHER_ENTITY)
        solar = self.config_entry.data.get(CONF_SOLAR_SENSOR)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        "orientation", default=orientation
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=ORIENTATION_OPTIONS,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Required(
                        "weather_entity", default=weather
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="weather")
                    ),
                    vol.Optional(
                        "solar_sensor", default=solar
                    ): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="sensor")
                    ),
                }
            ),
        )
