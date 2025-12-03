"""Config flow for Virtual MRT integration."""

from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries

from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import callback
from homeassistant.helpers import selector
from homeassistant.helpers.selector import SelectSelectorMode

from . import DEFAULT_AIR_SPEED_STILL
from .const import (
    DOMAIN,
    CONF_ROOM_PROFILE,
    ROOM_PROFILES,
    CONF_ORIENTATION,
    ORIENTATION_OPTIONS,
    CONF_AIR_TEMP_SOURCE,
    CONF_WEATHER_ENTITY,
    CONF_SOLAR_SENSOR,
    CONF_CLIMATE_ENTITY,
    CONF_WINDOW_STATE_SENSOR,
    CONF_DOOR_STATE_SENSOR,
    CONF_FAN_ENTITY,
    CONF_MANUAL_AIR_SPEED,
    CONF_SHADING_ENTITY,
    DEFAULT_ORIENTATION,
    CONF_IS_RADIANT,
)

OPTIONAL_ENTITY_SCHEMA = vol.All(vol.Any(str, None), selector.EntitySelector)


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Virtual MRT."""

    VERSION = 2
    MINOR_VERSION = 0

    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        if user_input is not None:
            return self.async_create_entry(title=user_input[CONF_NAME], data=user_input)

        profile_keys = list(ROOM_PROFILES.keys())

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    # --- CORE INPUTS ---
                    vol.Required(CONF_NAME): str,
                    vol.Required(CONF_AIR_TEMP_SOURCE): selector.EntitySelector(
                        selector.EntitySelectorConfig(
                            domain="sensor", device_class="temperature"
                        )
                    ),
                    vol.Required(CONF_WEATHER_ENTITY): selector.EntitySelector(
                        selector.EntitySelectorConfig(domain="weather")
                    ),
                    # --- PROFILE & ORIENTATION ---
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
                        CONF_ORIENTATION, default=DEFAULT_ORIENTATION
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=ORIENTATION_OPTIONS,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    # --- OPTIONAL ENTITIES (Using Helper for Robust Validation) ---
                    vol.Optional(CONF_SOLAR_SENSOR): OPTIONAL_ENTITY_SCHEMA(
                        selector.EntitySelectorConfig(domain=Platform.SENSOR)
                    ),
                    vol.Optional(CONF_CLIMATE_ENTITY): OPTIONAL_ENTITY_SCHEMA(
                        selector.EntitySelectorConfig(domain=Platform.CLIMATE)
                    ),
                    vol.Required(
                        CONF_IS_RADIANT, default=False
                    ): selector.BooleanSelector(),
                    vol.Optional(CONF_FAN_ENTITY): OPTIONAL_ENTITY_SCHEMA(
                        selector.EntitySelectorConfig(domain=Platform.FAN)
                    ),
                    vol.Optional(CONF_WINDOW_STATE_SENSOR): OPTIONAL_ENTITY_SCHEMA(
                        selector.EntitySelectorConfig(domain=Platform.BINARY_SENSOR)
                    ),
                    vol.Optional(CONF_DOOR_STATE_SENSOR): OPTIONAL_ENTITY_SCHEMA(
                        selector.EntitySelectorConfig(domain=Platform.BINARY_SENSOR)
                    ),
                    vol.Optional(
                        CONF_SHADING_ENTITY,
                    ): OPTIONAL_ENTITY_SCHEMA(
                        selector.EntitySelectorConfig(
                            domain=[
                                Platform.COVER,
                                Platform.BINARY_SENSOR,
                                Platform.SENSOR,
                                Platform.NUMBER,
                            ]
                        )
                    ),
                    vol.Optional(
                        CONF_MANUAL_AIR_SPEED, default=DEFAULT_AIR_SPEED_STILL
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0.0,
                            max=1.5,
                            step=0.1,
                            mode=selector.NumberSelectorMode.BOX,
                            unit_of_measurement="m/s",
                        )
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
        pass  # Base class handles config_entry assignment

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            # We must merge new options with old data
            new_data = self.config_entry.data.copy()
            new_data.update(user_input)

            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            return self.async_create_entry(title="", data=None)

        def _get_data(string_key, constant_key, default=None):
            val = self.config_entry.data.get(string_key)
            if val is None:
                val = self.config_entry.data.get(constant_key)
            if val is None:
                return default
            return val

        # Retrieve current values
        air_temp = _get_data("air_temp_source", CONF_AIR_TEMP_SOURCE)
        orientation = _get_data("orientation", CONF_ORIENTATION, DEFAULT_ORIENTATION)
        weather = _get_data("weather_entity", CONF_WEATHER_ENTITY)
        solar = _get_data("solar_sensor", CONF_SOLAR_SENSOR)

        climate = _get_data("climate_entity", CONF_CLIMATE_ENTITY)
        fan = _get_data("fan_entity", CONF_FAN_ENTITY)
        window = _get_data("window_state_sensor", CONF_WINDOW_STATE_SENSOR)
        door = _get_data("door_state_sensor", CONF_DOOR_STATE_SENSOR)
        manual_speed = _get_data(
            "manual_air_speed", CONF_MANUAL_AIR_SPEED, DEFAULT_AIR_SPEED_STILL
        )
        shading = _get_data("shading_entity", CONF_SHADING_ENTITY)
        is_radiant = _get_data(CONF_IS_RADIANT, CONF_IS_RADIANT, False)

        schema = {
            # Required fields still need 'default'
            vol.Required("air_temp_source", default=air_temp): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=Platform.SENSOR, device_class="temperature"
                )
            ),
            vol.Required("orientation", default=orientation): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=ORIENTATION_OPTIONS,
                    mode=SelectSelectorMode.DROPDOWN,
                )
            ),
            vol.Required("weather_entity", default=weather): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=Platform.WEATHER)
            ),
            # Optional fields using 'suggested_value'
            vol.Optional(
                "solar_sensor", description={"suggested_value": solar}
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=Platform.SENSOR)
            ),
            vol.Optional(
                "climate_entity", description={"suggested_value": climate}
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=Platform.CLIMATE)
            ),
            vol.Required(
                CONF_IS_RADIANT, description={"suggested_value": is_radiant}
            ): selector.BooleanSelector(),
            vol.Optional(
                "fan_entity", description={"suggested_value": fan}
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=Platform.FAN)
            ),
            vol.Optional(
                "window_state_sensor", description={"suggested_value": window}
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=Platform.BINARY_SENSOR)
            ),
            vol.Optional(
                "door_state_sensor", description={"suggested_value": door}
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=Platform.BINARY_SENSOR)
            ),
            # Number selector is safe with 'default' since it has a fallback of 0.1
            vol.Optional(
                "manual_air_speed", default=manual_speed
            ): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0.0,
                    max=1.5,
                    step=0.1,
                    mode=selector.NumberSelectorMode.BOX,
                    unit_of_measurement="m/s",
                )
            ),
            vol.Optional(
                "shading_entity", description={"suggested_value": shading}
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain=[
                        Platform.COVER,
                        Platform.BINARY_SENSOR,
                        Platform.SENSOR,
                        Platform.NUMBER,
                    ]
                )
            ),
        }

        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))
