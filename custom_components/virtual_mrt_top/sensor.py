"""Sensor platform for Virtual MRT."""

from __future__ import annotations
import logging

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers import entity_registry as er

from .const import (
    DOMAIN,
    CONF_AIR_TEMP_SOURCE,
    CONF_WEATHER_ENTITY,
    CONF_ROOM_PROFILE,
    CONF_ORIENTATION,
    CONF_SOLAR_SENSOR,
    ROOM_PROFILES,
    SOUTH_FACTORS,
    CONF_THERMAL_ALPHA,
)
from .device_info import get_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up sensors from a config entry."""

    # Define the device
    device_info = await get_device_info(
        {(DOMAIN, entry.entry_id)}, entry.data[CONF_NAME]
    )

    mrt_sensor = VirtualMRTSensor(hass, entry, device_info)
    op_sensor = VirtualOperativeTempSensor(hass, entry, device_info, mrt_sensor)

    async_add_entities([mrt_sensor, op_sensor])


class VirtualMRTSensor(SensorEntity):
    """Calculates Mean Radiant Temperature."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_suggested_display_precision = 2

    translation_key = "mrt"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_info):
        self.hass = hass
        self._entry = entry
        self._config = entry.data

        self._attr_unique_id = f"{entry.entry_id}_mrt"
        self._attr_device_info = device_info

        # Inputs
        self.entity_air = self._config[CONF_AIR_TEMP_SOURCE]
        self.entity_weather = self._config[CONF_WEATHER_ENTITY]
        self.entity_solar = self._config.get(CONF_SOLAR_SENSOR)
        self.south_factor = SOUTH_FACTORS[self._config[CONF_ORIENTATION]]

        self._attr_native_value = None
        self._mrt_prev = None
        self._attributes = {}
        # Entity IDs of the number inputs, to be found
        self.id_f_out = None
        self.id_f_win = None
        self.id_k_loss = None
        self.id_k_solar = None
        self.id_profile_select = None
        self.id_thermal_alpha = None

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    async def async_added_to_hass(self):
        """Find number entities and register listeners."""
        await super().async_added_to_hass()

        # Find the entity IDs of the number controls
        registry = er.async_get(self.hass)
        self.id_f_out = registry.async_get_entity_id(
            "number", DOMAIN, f"{self._entry.entry_id}_f_out"
        )
        self.id_f_win = registry.async_get_entity_id(
            "number", DOMAIN, f"{self._entry.entry_id}_f_win"
        )
        self.id_k_loss = registry.async_get_entity_id(
            "number", DOMAIN, f"{self._entry.entry_id}_k_loss"
        )
        self.id_k_solar = registry.async_get_entity_id(
            "number", DOMAIN, f"{self._entry.entry_id}_k_solar"
        )
        self.id_profile_select = registry.async_get_entity_id(
            "select", DOMAIN, f"{self._entry.entry_id}_profile"
        )
        self.id_thermal_alpha = registry.async_get_entity_id(
            "number", DOMAIN, f"{self._entry.entry_id}_{CONF_THERMAL_ALPHA}"
        )
        # Core entities to listen to
        entities_to_track = [self.entity_air, self.entity_weather, "sun.sun"]
        if self.entity_solar:
            entities_to_track.append(self.entity_solar)

        # Add number entities (if found)
        for num_id in [
            self.id_f_out,
            self.id_f_win,
            self.id_k_loss,
            self.id_k_solar,
            self.id_thermal_alpha,
        ]:
            if num_id:
                entities_to_track.append(num_id)

        # Add select entity (if found)
        if self.id_profile_select:
            entities_to_track.append(self.id_profile_select)

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, entities_to_track, self._handle_update
            )
        )
        self._update_calc()  # Initial update

    @property
    def icon(self) -> str | None:
        """Icon of the entity"""
        return "mdi:home-thermometer"

    @callback
    def _handle_update(self, event):
        """Handle entity state changes."""
        self._update_calc()
        self.async_write_ha_state()

    def _get_float(self, entity_id, default=0.0):
        """Helper to get float from state."""
        if not entity_id:
            return default
        state = self.hass.states.get(entity_id)
        if not state or state.state in ["unknown", "unavailable"]:
            return default
        try:
            return float(state.state)
        except ValueError:
            return default

    def _get_attr(self, entity_id, attr, default=None):
        """Helper to get attribute."""
        state = self.hass.states.get(entity_id)
        if not state:
            return default
        val = state.attributes.get(attr)
        try:
            return float(val) if val is not None else default
        except ValueError:
            return default

    def _update_calc(self):
        """Perform the math and store all intermediate values."""
        # If we haven't found our entities, try again.
        if not all(
            [
                self.id_f_out,
                self.id_f_win,
                self.id_k_loss,
                self.id_k_solar,
                self.id_profile_select,
            ]
        ):
            _LOGGER.debug("Entities not yet registered, trying to find them...")
            registry = er.async_get(self.hass)
            self.id_f_out = registry.async_get_entity_id(
                "number", DOMAIN, f"{self._entry.entry_id}_f_out"
            )
            self.id_f_win = registry.async_get_entity_id(
                "number", DOMAIN, f"{self._entry.entry_id}_f_win"
            )
            self.id_k_loss = registry.async_get_entity_id(
                "number", DOMAIN, f"{self._entry.entry_id}_k_loss"
            )
            self.id_k_solar = registry.async_get_entity_id(
                "number", DOMAIN, f"{self._entry.entry_id}_k_solar"
            )
            self.id_profile_select = registry.async_get_entity_id(
                "select", DOMAIN, f"{self._entry.entry_id}_profile"
            )
            self.id_thermal_alpha = registry.async_get_entity_id(
                "number", DOMAIN, f"{self._entry.entry_id}_{CONF_THERMAL_ALPHA}"
            )

            # If we STILL haven't found them, log and bail for this update.
            if not all(
                [
                    self.id_f_out,
                    self.id_f_win,
                    self.id_k_loss,
                    self.id_k_solar,
                    self.id_profile_select,
                ]
            ):
                _LOGGER.debug(
                    "Could not find all required entities for %s, calculation will be delayed.",
                    self.entity_id,
                )
                return

        # --- Start fresh on attributes
        self._attributes = {}

        # --- Profile Info
        # Start with the fallback profile from the config entry
        profile_key = self._config[CONF_ROOM_PROFILE]

        # Check if the select entity ID has been found AND it has a valid state
        if self.id_profile_select:  # Check it's not None
            profile_state = self.hass.states.get(self.id_profile_select)
            if profile_state and profile_state.state not in ["unknown", "unavailable"]:
                profile_key = profile_state.state  # Use the live state

        self._attributes["profile"] = profile_key
        self._attributes["orientation"] = self._config[CONF_ORIENTATION]

        # --- T_air (Input)
        t_air = self._get_float(self.entity_air, None)
        if t_air is None:
            return  # Cannot calc yet
        self._attributes["t_air"] = t_air

        # --- T_out (Input)
        t_out = self._get_attr(self.entity_weather, "temperature")
        if t_out is None:
            return  # Cannot calc yet

        t_app = self._get_attr(self.entity_weather, "apparent_temperature")

        t_out_eff = t_out
        t_out_source = "temperature"
        if t_app is not None and t_app < t_out:
            t_out_eff = t_app
            t_out_source = "apparent_temperature"

        self._attributes["t_out_eff"] = round(t_out_eff, 2)
        self._attributes["t_out_eff_source"] = t_out_source

        # --- Dynamic Factors (Inputs)
        config_profile_key = self._config[CONF_ROOM_PROFILE]
        defaults = ROOM_PROFILES[config_profile_key]["data"]
        f_out = self._get_float(self.id_f_out, defaults[0])
        f_win = self._get_float(self.id_f_win, defaults[1])
        k_loss = self._get_float(self.id_k_loss, defaults[2])
        k_solar = self._get_float(self.id_k_solar, defaults[3])
        alpha = self._get_float(self.id_thermal_alpha, 0.3)
        self._attributes["factor_f_out"] = f_out
        self._attributes["factor_f_win"] = f_win
        self._attributes["factor_k_loss"] = k_loss
        self._attributes["factor_k_solar"] = k_solar
        self._attributes["thermal_alpha"] = alpha

        # --- Wind (Input)
        wind_speed_ms = self._get_attr(self.entity_weather, "wind_speed", 0.0)
        # Handle HA default units (m/s or km/h)
        if (
            self.hass.states.get(self.entity_weather).attributes.get("wind_speed_unit")
            == "km/h"
        ):
            wind_speed_ms = wind_speed_ms / 3.6

        wind_speed_kmh = wind_speed_ms * 3.6
        self._attributes["wind_ms"] = round(wind_speed_ms, 2)
        self._attributes["wind_kmh"] = round(wind_speed_kmh, 2)
        self._attributes["wind_source"] = "weather_entity"

        # --- Clouds (Input)
        cloud = self._get_attr(self.entity_weather, "cloud_coverage", None)
        cloud_source = "weather_entity"
        if cloud is None:
            cloud = 50.0  # Fallback
            cloud_source = "fallback"
        self._attributes["cloud_coverage"] = cloud
        self._attributes["cloud_source"] = cloud_source

        # --- UV (Input)
        uv = self._get_attr(self.entity_weather, "uv_index", None)
        uv_source = "weather_entity"
        if uv is None:
            uv = 0.0  # Fallback
            uv_source = "fallback"
        self._attributes["uv_index"] = uv
        self._attributes["uv_source"] = uv_source

        # --- Rain (Input)
        weather_state = self.hass.states.get(self.entity_weather)
        cond = weather_state.state.lower() if weather_state else ""
        is_raining = any(x in cond for x in ["rain", "pour", "snow", "hail"])
        rain_mul = 0.4 if is_raining else 1.0
        rain_source = "condition_string" if is_raining else "dry"
        self._attributes["rain_multiplier"] = rain_mul
        self._attributes["rain_source"] = rain_source

        # --- Sun (Input)
        elevation = self._get_attr("sun.sun", "elevation", 0.0)
        day_fac = max(0, min(1, (elevation + 6.0) / 66.0))
        self._attributes["daylight_factor"] = round(day_fac, 3)

        # --- Radiation (Calc)
        # 1. Check for dedicated sensor
        if self.entity_solar:
            rad = self._get_float(self.entity_solar, None)
            if rad is not None:
                rad_source = "sensor"
                rad_val = rad

                # Log warning if sensor value is implausibly high, but use it.
                if rad_val > 1300:
                    _LOGGER.warning(
                        "Solar sensor value (%s W/m²) exceeds physical maximum (1300 W/m²). Using reported value for calculation.",
                        rad_val,
                    )

        # 2. If no sensor data, use heuristic model
        if rad_source != "sensor":
            cloud_factor = max(0, 1 - (0.9 * (cloud / 100.0)))
            base = (90 * uv) if uv > 0 else (100 * day_fac)
            est = base * cloud_factor * rain_mul * day_fac

            # Apply the 1000 W/m² cap ONLY to the HEURISTIC ESTIMATE
            rad_val = min(1000, est)

            rad_source = "heuristic"

        self._attributes["radiation"] = round(rad_val, 1)
        self._attributes["radiation_source"] = rad_source

        # We ensure rad_val is 0 if sun is down, though day_fac handles this.
        rad_final = max(0.0, rad_val)

        # --- Main Formula Terms (Calc)
        term_loss = (
            k_loss
            * (t_air - t_out_eff)
            * (f_out + 1.5 * f_win)
            * (1 + 0.02 * wind_speed_ms)
        )
        term_solar = k_solar * (rad_final / 400.0) * self.south_factor * f_win
        mrt_calc = t_air - term_loss + term_solar

        self._attributes["loss_term"] = round(term_loss, 3)
        self._attributes["solar_term"] = round(term_solar, 3)
        self._attributes["mrt_unclamped"] = round(mrt_calc, 2)

        # --- Clamping (Calc)
        lower_dyn = max(t_out_eff + 2.0, t_air - 3.0)
        upper_dyn = t_air + 4.0
        mrt_clamped = max(lower_dyn, min(mrt_calc, upper_dyn))
        self._attributes["mrt_clamped"] = round(mrt_clamped, 2)

        # --- Smoothing (Calc)
        if self._mrt_prev is None:
            self._mrt_prev = mrt_clamped
        # OLD
        # mrt_final = 0.7 * self._mrt_prev + 0.3 * mrt_clamped
        mrt_final = ((1.0 - alpha) * self._mrt_prev) + (alpha * mrt_clamped)
        self._mrt_prev = mrt_final

        # --- Final Value
        self._attr_native_value = round(mrt_final, 2)


class VirtualOperativeTempSensor(SensorEntity):
    """Calculates Operative Temp: (Air + MRT) / 2."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    # _attr_name = "Operative Temperature"
    _attr_suggested_display_precision = 2

    translation_key = "operative_temperature"

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device_info,
        mrt_sensor: VirtualMRTSensor,
    ):
        self.hass = hass
        self._attr_unique_id = f"{entry.entry_id}_operative"
        self._attr_device_info = device_info
        self._mrt_sensor = mrt_sensor
        self._air_entity = entry.data[CONF_AIR_TEMP_SOURCE]
        self._attributes = {}

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    async def async_added_to_hass(self):
        """Listen to MRT sensor and Air sensor."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self._mrt_sensor.entity_id, self._air_entity],
                self._handle_update,
            )
        )

    @property
    def icon(self) -> str | None:
        """Icon of the entity"""
        return "mdi:home-thermometer"

    @callback
    def _handle_update(self, event):
        mrt = self._mrt_sensor.native_value
        air_state = self.hass.states.get(self._air_entity)

        if self._mrt_sensor.extra_state_attributes:
            self._attributes = self._mrt_sensor.extra_state_attributes.copy()
        else:
            self._attributes = {}

        if (
            mrt is not None
            and air_state
            and air_state.state not in ["unknown", "unavailable"]
        ):
            try:
                air = float(air_state.state)
                self._attr_native_value = round((air + mrt) / 2, 2)
                self.async_write_ha_state()
            except ValueError:
                self._attr_native_value = None
        else:
            self._attr_native_value = None
