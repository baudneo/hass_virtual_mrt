"""Config flow for Virtual MRT integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
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
    CONF_OUTDOOR_TEMP_SENSOR,
    CONF_OUTDOOR_HUMIDITY_SENSOR,
    CONF_WIND_SPEED_SENSOR,
    CONF_CLIMATE_ENTITY,
    CONF_WINDOW_STATE_SENSOR,
    CONF_DOOR_STATE_SENSOR,
    CONF_FAN_ENTITY,
    CONF_MANUAL_AIR_SPEED,
    CONF_SHADING_ENTITY,
    DEFAULT_ORIENTATION,
    CONF_IS_RADIANT,
    CONF_RH_SENSOR,
    CONF_WALL_SURFACE_SENSOR,
    DEFAULT_AIR_SPEED_STILL,
    CONF_PRESSURE_SENSOR,
    CONF_MIN_UPDATE_INTERVAL,
    DEFAULT_MIN_UPDATE_INTERVAL,
    CONF_DEVICE_TYPE,
    TYPE_AGGREGATOR,
    CONF_SOURCE_ENTITIES,
    TYPE_ROOM,
    CONF_ROOM_AREA,
)


def _flatten_input(user_input: dict) -> dict:
    """
    Helper: Flatten nested section dictionaries into the top level.
    e.g. {'sensors_section': {'rh_sensor': 'x'}} -> {'rh_sensor': 'x'}
    """
    if not user_input:
        return {}

    flat = {}
    for key, value in user_input.items():
        if isinstance(value, dict) and key.endswith("_section"):
            flat.update(value)
        else:
            flat[key] = value
    return flat


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Virtual MRT."""

    VERSION = 3
    MINOR_VERSION = 0

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return OptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input=None):
        """Handle the initial step (Menu)."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["room_setup", "aggregator_setup"]
        )

    async def async_step_aggregator_setup(self, user_input=None):
        """Handle the setup for a Zone Aggregator."""
        if user_input is not None:
            # Aggregator doesn't use sections, so no flattening needed yet
            data = {
                CONF_NAME: user_input[CONF_NAME],
                CONF_DEVICE_TYPE: TYPE_AGGREGATOR,
                "source_devices": user_input["source_devices"]
            }
            return self.async_create_entry(title=user_input[CONF_NAME], data=data)

        return self.async_show_form(
            step_id="aggregator_setup",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME): str,
                vol.Required("source_devices"): selector.DeviceSelector(
                    selector.DeviceSelectorConfig(
                        multiple=True,
                        integration=DOMAIN
                    )
                ),
            })
        )

    async def async_step_room_setup(self, user_input=None):
        """Handle the standard Room setup."""
        if user_input is not None:
            # --- FIX: FLATTEN INPUT BEFORE SAVING ---
            flat_input = _flatten_input(user_input)

            flat_input[CONF_DEVICE_TYPE] = TYPE_ROOM
            return self.async_create_entry(title=flat_input[CONF_NAME], data=flat_input)

        profile_keys = list(ROOM_PROFILES.keys())

        return self.async_show_form(
            step_id="room_setup",
            data_schema=vol.Schema(
                {
                    # --- SECTION 1: CORE (Always Visible) ---
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
                    vol.Required(CONF_ROOM_AREA, default=15.0): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=1.0, max=500.0, step=0.1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="m²"
                        )
                    ),
                    vol.Required(CONF_MIN_UPDATE_INTERVAL, default=DEFAULT_MIN_UPDATE_INTERVAL): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0, max=300, step=5, unit_of_measurement="seconds",
                            mode=selector.NumberSelectorMode.BOX
                        )
                    ),
                    vol.Required(
                        CONF_IS_RADIANT, default=False
                    ): selector.BooleanSelector(),
                    # --- SECTION 2: OPTIONAL SENSORS ---
                    vol.Optional("sensors_section"): section(
                        vol.Schema(
                            {
                                vol.Optional(
                                    CONF_SOLAR_SENSOR
                                ): selector.EntitySelector(
                                    selector.EntitySelectorConfig(domain="sensor")
                                ),
                                vol.Optional(CONF_RH_SENSOR): selector.EntitySelector(
                                    selector.EntitySelectorConfig(
                                        domain="sensor", device_class="humidity"
                                    )
                                ),
                                vol.Optional(
                                    CONF_WALL_SURFACE_SENSOR
                                ): selector.EntitySelector(
                                    selector.EntitySelectorConfig(
                                        domain="sensor", device_class="temperature"
                                    )
                                ),
                                vol.Optional(
                                    CONF_PRESSURE_SENSOR
                                ): selector.EntitySelector(
                                    selector.EntitySelectorConfig(
                                        domain="sensor",
                                        device_class=[
                                            "atmospheric_pressure",
                                            "pressure",
                                        ],
                                    )
                                ),
                                vol.Optional(
                                    CONF_OUTDOOR_TEMP_SENSOR
                                ): selector.EntitySelector(
                                    selector.EntitySelectorConfig(
                                        domain="sensor", device_class="temperature"
                                    )
                                ),
                                vol.Optional(
                                    CONF_OUTDOOR_HUMIDITY_SENSOR
                                ): selector.EntitySelector(
                                    selector.EntitySelectorConfig(
                                        domain="sensor", device_class="humidity"
                                    )
                                ),
                                vol.Optional(
                                    CONF_WIND_SPEED_SENSOR
                                ): selector.EntitySelector(
                                    selector.EntitySelectorConfig(
                                        domain="sensor", device_class="wind_speed"
                                    )
                                ),
                            }
                        )
                    ),
                    # --- SECTION 3: CONVECTION & AIRFLOW ---
                    vol.Optional("convection_section"): section(
                        vol.Schema(
                            {
                                vol.Optional(
                                    CONF_CLIMATE_ENTITY
                                ): selector.EntitySelector(
                                    selector.EntitySelectorConfig(
                                        domain=Platform.CLIMATE
                                    )
                                ),
                                vol.Optional(CONF_FAN_ENTITY): selector.EntitySelector(
                                    selector.EntitySelectorConfig(domain=Platform.FAN)
                                ),
                                vol.Optional(
                                    CONF_WINDOW_STATE_SENSOR
                                ): selector.EntitySelector(
                                    selector.EntitySelectorConfig(
                                        domain=Platform.BINARY_SENSOR
                                    )
                                ),
                                vol.Optional(
                                    CONF_DOOR_STATE_SENSOR
                                ): selector.EntitySelector(
                                    selector.EntitySelectorConfig(
                                        domain=Platform.BINARY_SENSOR
                                    )
                                ),
                                vol.Optional(
                                    CONF_MANUAL_AIR_SPEED,
                                    default=DEFAULT_AIR_SPEED_STILL,
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
                        )
                    ),
                    # --- SECTION 4: ADVANCED ---
                    vol.Optional("advanced_section"): section(
                        vol.Schema(
                            {
                                vol.Optional(
                                    CONF_SHADING_ENTITY
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
                        )
                    ),
                }
            ),
        )


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handles options flow for the component."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        pass

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        # -----------------------------------------------------------
        # BRANCH 1: AGGREGATOR OPTIONS
        # -----------------------------------------------------------
        if self.config_entry.data.get(CONF_DEVICE_TYPE) == TYPE_AGGREGATOR:
            if user_input is not None:
                # Update aggregator configuration
                new_data = self.config_entry.data.copy()
                new_data.update(user_input)
                self.hass.config_entries.async_update_entry(self.config_entry, data=new_data)
                return self.async_create_entry(title="", data=None)

            # Show Aggregator Form (Edit included devices)
            current_devices = self.config_entry.data.get("source_devices", [])
            return self.async_show_form(
                step_id="init",
                data_schema=vol.Schema({
                    vol.Required("source_devices", default=current_devices): selector.DeviceSelector(
                        selector.DeviceSelectorConfig(
                            multiple=True,
                            integration=DOMAIN
                        )
                    ),
                })
            )

        # -----------------------------------------------------------
        # BRANCH 2: ROOM OPTIONS (Existing Logic)
        # -----------------------------------------------------------
        if user_input is not None:
            # Flatten inputs from sections
            flat_input = _flatten_input(user_input)

            # Merge new options with old data
            new_data = self.config_entry.data.copy()
            new_data.update(flat_input)

            self.hass.config_entries.async_update_entry(
                self.config_entry, data=new_data
            )
            return self.async_create_entry(title="", data=None)

        # --- DATA RETRIEVAL HELPER ---
        def _get_data(string_key, constant_key, default=None):
            val = self.config_entry.data.get(string_key)
            if val is None:
                val = self.config_entry.data.get(constant_key)
            if val is None:
                return default
            return val

        # Retrieve current values
        # NOTE: We keep required sensor sources here so users can update them.
        air_temp = _get_data("air_temp_source", CONF_AIR_TEMP_SOURCE)
        orientation = _get_data("orientation", CONF_ORIENTATION, DEFAULT_ORIENTATION)
        weather = _get_data("weather_entity", CONF_WEATHER_ENTITY)

        solar = _get_data("solar_sensor", CONF_SOLAR_SENSOR)
        rh = _get_data("rh_sensor", CONF_RH_SENSOR)

        climate = _get_data("climate_entity", CONF_CLIMATE_ENTITY)
        fan = _get_data("fan_entity", CONF_FAN_ENTITY)
        window = _get_data("window_state_sensor", CONF_WINDOW_STATE_SENSOR)
        door = _get_data("door_state_sensor", CONF_DOOR_STATE_SENSOR)
        manual_speed = _get_data("manual_air_speed", CONF_MANUAL_AIR_SPEED, DEFAULT_AIR_SPEED_STILL)
        shading = _get_data("shading_entity", CONF_SHADING_ENTITY)

        is_radiant = _get_data("is_radiant_heating", CONF_IS_RADIANT, False)
        wall_sensor = _get_data("wall_surface_sensor", CONF_WALL_SURFACE_SENSOR)
        out_hum = _get_data("outdoor_humidity_sensor", CONF_OUTDOOR_HUMIDITY_SENSOR)
        out_temp = _get_data("outdoor_temp_sensor", CONF_OUTDOOR_TEMP_SENSOR)
        wind = _get_data("wind_speed_sensor", CONF_WIND_SPEED_SENSOR)
        pressure = _get_data("pressure_sensor", CONF_PRESSURE_SENSOR)

        min_interval = _get_data("min_update_interval", CONF_MIN_UPDATE_INTERVAL, DEFAULT_MIN_UPDATE_INTERVAL)
        room_area = _get_data("room_area", CONF_ROOM_AREA, 15.0)

        schema = {
            # --- CORE ---
            vol.Required("air_temp_source", default=air_temp): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor", device_class="temperature"
                )
            ),
            vol.Required("weather_entity", default=weather): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="weather")
            ),
            vol.Required("orientation", default=orientation): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=ORIENTATION_OPTIONS, mode=SelectSelectorMode.DROPDOWN
                )
            ),
            vol.Required(CONF_ROOM_AREA, default=room_area): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=1.0, max=500.0, step=0.1, mode=selector.NumberSelectorMode.BOX, unit_of_measurement="m²"
                )
            ),
            vol.Optional(CONF_MIN_UPDATE_INTERVAL, default=min_interval): selector.NumberSelector(
                selector.NumberSelectorConfig(
                    min=0, max=300, step=5, unit_of_measurement="seconds",
                    mode=selector.NumberSelectorMode.BOX
                )
            ),
            vol.Required(
                "is_radiant_heating", default=is_radiant
            ): selector.BooleanSelector(),
            # --- SECTION: OPTIONAL SENSORS ---
            vol.Optional("sensors_section"): section(
                vol.Schema(
                    {
                        vol.Optional(
                            "solar_sensor", description={"suggested_value": solar}
                        ): selector.EntitySelector(
                            selector.EntitySelectorConfig(domain="sensor")
                        ),
                        vol.Optional(
                            "rh_sensor", description={"suggested_value": rh}
                        ): selector.EntitySelector(
                            selector.EntitySelectorConfig(
                                domain="sensor", device_class="humidity"
                            )
                        ),
                        vol.Optional(
                            "wall_surface_sensor",
                            description={"suggested_value": wall_sensor},
                        ): selector.EntitySelector(
                            selector.EntitySelectorConfig(
                                domain="sensor", device_class="temperature"
                            )
                        ),
                        vol.Optional(
                            "pressure_sensor", description={"suggested_value": pressure}
                        ): selector.EntitySelector(
                            selector.EntitySelectorConfig(
                                domain="sensor",
                                device_class=["atmospheric_pressure", "pressure"],
                            )
                        ),
                        vol.Optional(
                            "outdoor_temp_sensor",
                            description={"suggested_value": out_temp},
                        ): selector.EntitySelector(
                            selector.EntitySelectorConfig(
                                domain="sensor", device_class="temperature"
                            )
                        ),
                        vol.Optional(
                            "outdoor_humidity_sensor",
                            description={"suggested_value": out_hum},
                        ): selector.EntitySelector(
                            selector.EntitySelectorConfig(
                                domain="sensor", device_class="humidity"
                            )
                        ),
                        vol.Optional(
                            "wind_speed_sensor", description={"suggested_value": wind}
                        ): selector.EntitySelector(
                            selector.EntitySelectorConfig(
                                domain="sensor", device_class="wind_speed"
                            )
                        ),
                    }
                )
            ),
            # --- SECTION: CONVECTION ---
            vol.Optional("convection_section"): section(
                vol.Schema(
                    {
                        vol.Optional(
                            "climate_entity", description={"suggested_value": climate}
                        ): selector.EntitySelector(
                            selector.EntitySelectorConfig(domain=Platform.CLIMATE)
                        ),
                        vol.Optional(
                            "fan_entity", description={"suggested_value": fan}
                        ): selector.EntitySelector(
                            selector.EntitySelectorConfig(domain=Platform.FAN)
                        ),
                        vol.Optional(
                            "window_state_sensor",
                            description={"suggested_value": window},
                        ): selector.EntitySelector(
                            selector.EntitySelectorConfig(domain=Platform.BINARY_SENSOR)
                        ),
                        vol.Optional(
                            "door_state_sensor", description={"suggested_value": door}
                        ): selector.EntitySelector(
                            selector.EntitySelectorConfig(domain=Platform.BINARY_SENSOR)
                        ),
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
                    }
                )
            ),
            # --- SECTION: ADVANCED ---
            vol.Optional("advanced_section"): section(
                vol.Schema(
                    {
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
                )
            ),
        }

        return self.async_show_form(step_id="init", data_schema=vol.Schema(schema))