"""Sensor platform for Virtual MRT."""

from __future__ import annotations
import logging
import math

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

from . import CONF_IS_RADIANT
from .const import (
    DOMAIN,
    CONF_AIR_TEMP_SOURCE,
    CONF_WEATHER_ENTITY,
    CONF_ROOM_PROFILE,
    CONF_ORIENTATION,
    CONF_SOLAR_SENSOR,
    ROOM_PROFILES,
    CONF_THERMAL_ALPHA,
    CONF_CLIMATE_ENTITY,
    CONF_WINDOW_STATE_SENSOR,
    CONF_DOOR_STATE_SENSOR,
    CONF_FAN_ENTITY,
    CONF_MANUAL_AIR_SPEED,
    CONF_HVAC_AIR_SPEED,
    DEFAULT_AIR_SPEED_STILL,
    DEFAULT_AIR_SPEED_HVAC,
    DEFAULT_AIR_SPEED_WINDOW,
    DEFAULT_AIR_SPEED_DOOR,
    FAN_SPEED_MAP,
    CONF_SHADING_ENTITY,
    RADIANT_TYPES,
    CONF_RADIANT_SURFACE_TEMP,
    CONF_RADIANT_TYPE,
    ORIENTATION_DEGREES,
)
from .device_info import get_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up sensors from a config entry."""
    config = entry.data
    device_info = await get_device_info({(DOMAIN, entry.entry_id)}, config[CONF_NAME])
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
        self.entity_climate = self._config.get(CONF_CLIMATE_ENTITY)
        self.entity_fan = self._config.get(CONF_FAN_ENTITY)
        self.entity_window = self._config.get(CONF_WINDOW_STATE_SENSOR)
        self.entity_door = self._config.get(CONF_DOOR_STATE_SENSOR)
        self.entity_shading = self._config.get(CONF_SHADING_ENTITY)
        orient_code = self._config[CONF_ORIENTATION]
        self.orientation_degrees = ORIENTATION_DEGREES.get(orient_code, 180)
        self._radiant_boost_stored = 0.0
        self.is_radiant = self._config.get(CONF_IS_RADIANT, False)
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
        self.id_manual_speed = None
        self.id_hvac_speed = None
        self.id_radiant_type = None
        self.id_radiant_temp = None

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
        self.id_manual_speed = registry.async_get_entity_id(
            "number", DOMAIN, f"{self._entry.entry_id}_{CONF_MANUAL_AIR_SPEED}"
        )
        self.id_hvac_speed = registry.async_get_entity_id(
            "number", DOMAIN, f"{self._entry.entry_id}_{CONF_HVAC_AIR_SPEED}"
        )
        self.id_radiant_temp = registry.async_get_entity_id(
            "number", DOMAIN, f"{self._entry.entry_id}_{CONF_RADIANT_SURFACE_TEMP}"
        )
        self.id_radiant_type = registry.async_get_entity_id(
            "select", DOMAIN, f"{self._entry.entry_id}_{CONF_RADIANT_TYPE}"
        )

        # Core entities to listen to
        entities_to_track = [self.entity_air, self.entity_weather, "sun.sun"]

        # Add optional entity IDs (only if configured)
        if self.entity_solar:
            entities_to_track.append(self.entity_solar)
        if self.entity_climate:
            entities_to_track.append(self.entity_climate)
        if self.entity_fan:
            entities_to_track.append(self.entity_fan)
        if self.entity_window:
            entities_to_track.append(self.entity_window)
        if self.entity_door:
            entities_to_track.append(self.entity_door)
        if self.entity_shading:
            entities_to_track.append(self.entity_shading)

        # Add number entities (if found)
        for num_id in [
            self.id_f_out,
            self.id_f_win,
            self.id_k_loss,
            self.id_k_solar,
            self.id_thermal_alpha,
            self.id_manual_speed,
            self.id_hvac_speed,
            self.id_radiant_temp,
        ]:
            if num_id:
                entities_to_track.append(num_id)

        # Add select entity (if found)
        if self.id_profile_select:
            entities_to_track.append(self.id_profile_select)
        if self.id_radiant_type:
            entities_to_track.append(self.id_radiant_type)

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

    def _get_solar_incidence_factor(self) -> float:
        """Calculates how directly the sun is shining on the window."""
        sun_state = self.hass.states.get("sun.sun")
        if not sun_state:
            return 0.1  # Fallback to diffuse only

        sun_azimuth = sun_state.attributes.get("azimuth", 180)

        # Calculate difference between Sun and Window
        diff = abs(sun_azimuth - self.orientation_degrees)
        if diff > 180:
            diff = 360 - diff

        # If the sun is more than 90 degrees off-axis, only diffuse (skylight).
        if diff >= 90:
            return 0.1

        # Calculate cosine of the angle
        cosine_factor = math.cos(math.radians(diff))

        # Result is Cosine + Diffuse Baseline (clamped to 1.0 max)
        return min(1.0, cosine_factor + 0.1)

    def _get_shading_factor(self) -> float:
        """Calculates solar multiplier based on entity state (0.0 to 1.0)."""
        if not self.entity_shading:
            return 1.0

        state_obj = self.hass.states.get(self.entity_shading)
        if not state_obj or state_obj.state in ["unavailable", "unknown", None]:
            return 1.0

        domain = state_obj.domain
        state = state_obj.state

        # --- CASE 1: COVERS ---
        if domain == "cover":
            current_pos = state_obj.attributes.get("current_position")
            if current_pos is not None:
                try:
                    return float(current_pos) / 100.0
                except ValueError:
                    pass
            return 0.0 if state == "closed" else 1.0

        # --- CASE 2: NUMBERS / SENSORS ---
        if domain in ["input_number", "sensor", "number"]:
            try:
                val = float(state)
                if val > 1.0:
                    return min(1.0, val / 100.0)
                return max(0.0, val)
            except ValueError:
                return 1.0

        # --- CASE 3: BINARY ---
        if state == "on":
            return 1.0
        if state == "off":
            return 0.0

        return 1.0

    def _calculate_v_air(self) -> float:
        """Determines the effective air velocity (m/s) based on priority logic."""
        # Note: This function assumes IDs are valid or None.

        # Read new entity states
        climate_state = (
            self.hass.states.get(self.entity_climate) if self.entity_climate else None
        )
        window_state = (
            self.hass.states.get(self.entity_window) if self.entity_window else None
        )
        door_state = (
            self.hass.states.get(self.entity_door) if self.entity_door else None
        )
        fan_state = self.hass.states.get(self.entity_fan) if self.entity_fan else None

        # Start with default still air speed
        potential_speeds = [DEFAULT_AIR_SPEED_STILL]

        # --- Check Manual Override ---
        manual_speed = self._get_float(self.id_manual_speed, 0.0)
        if manual_speed > 0:
            potential_speeds.append(manual_speed)

        # --- Check Natural Ventilation ---
        if window_state and window_state.state.lower() == "on":
            potential_speeds.append(DEFAULT_AIR_SPEED_WINDOW)

        if door_state and door_state.state.lower() == "on":
            potential_speeds.append(DEFAULT_AIR_SPEED_DOOR)

        # --- Check HVAC (Forced Air) ---
        hvac_speed_setting = self._get_float(self.id_hvac_speed, DEFAULT_AIR_SPEED_HVAC)
        if not self.is_radiant:
            if climate_state:
                attrs = climate_state.attributes
                is_active = attrs.get("hvac_action") not in ["off", "idle", None]
                is_fan_forced = attrs.get("fan_mode") == "on"

                if is_active or is_fan_forced:
                    potential_speeds.append(hvac_speed_setting)

        # --- Check Local Fan Entity ---
        if fan_state and fan_state.state not in ["off", "unavailable", "unknown", None]:
            fan_speed_key = str(fan_state.state).lower()
            fan_speed = FAN_SPEED_MAP.get(fan_speed_key, hvac_speed_setting)
            potential_speeds.append(fan_speed)

        return max(potential_speeds)

    def _update_calc(self):
        """Perform the math and store all intermediate values."""

        # --- 1. ROBUST ENTITY CHECK ---
        # We must verify that ALL required internal entity IDs have been found
        # before we attempt to read their states.
        required_ids = [
            self.id_f_out,
            self.id_f_win,
            self.id_k_loss,
            self.id_k_solar,
            self.id_profile_select,
            self.id_thermal_alpha,
            self.id_manual_speed,
            self.id_hvac_speed,
            self.id_radiant_temp,
            self.id_radiant_type,
        ]

        if not all(required_ids):
            _LOGGER.debug("Entities not yet registered, trying to find them...")
            registry = er.async_get(self.hass)

            # Try to populate missing IDs
            if not self.id_f_out:
                self.id_f_out = registry.async_get_entity_id(
                    "number", DOMAIN, f"{self._entry.entry_id}_f_out"
                )
            if not self.id_f_win:
                self.id_f_win = registry.async_get_entity_id(
                    "number", DOMAIN, f"{self._entry.entry_id}_f_win"
                )
            if not self.id_k_loss:
                self.id_k_loss = registry.async_get_entity_id(
                    "number", DOMAIN, f"{self._entry.entry_id}_k_loss"
                )
            if not self.id_k_solar:
                self.id_k_solar = registry.async_get_entity_id(
                    "number", DOMAIN, f"{self._entry.entry_id}_k_solar"
                )
            if not self.id_profile_select:
                self.id_profile_select = registry.async_get_entity_id(
                    "select", DOMAIN, f"{self._entry.entry_id}_profile"
                )
            if not self.id_thermal_alpha:
                self.id_thermal_alpha = registry.async_get_entity_id(
                    "number", DOMAIN, f"{self._entry.entry_id}_{CONF_THERMAL_ALPHA}"
                )
            if not self.id_manual_speed:
                self.id_manual_speed = registry.async_get_entity_id(
                    "number", DOMAIN, f"{self._entry.entry_id}_{CONF_MANUAL_AIR_SPEED}"
                )
            if not self.id_hvac_speed:
                self.id_hvac_speed = registry.async_get_entity_id(
                    "number", DOMAIN, f"{self._entry.entry_id}_{CONF_HVAC_AIR_SPEED}"
                )
            if not self.id_radiant_temp:
                self.id_radiant_temp = registry.async_get_entity_id(
                    "number",
                    DOMAIN,
                    f"{self._entry.entry_id}_{CONF_RADIANT_SURFACE_TEMP}",
                )
            if not self.id_radiant_type:
                self.id_radiant_type = registry.async_get_entity_id(
                    "select", DOMAIN, f"{self._entry.entry_id}_{CONF_RADIANT_TYPE}"
                )

            # Re-check. If still missing, we cannot proceed.
            # We must use 'self.id_xxx' here to check the instance variables.
            if not (
                self.id_f_out
                and self.id_f_win
                and self.id_k_loss
                and self.id_k_solar
                and self.id_profile_select
                and self.id_thermal_alpha
                and self.id_manual_speed
                and self.id_hvac_speed
                and self.id_radiant_temp
                and self.id_radiant_type
            ):
                _LOGGER.debug(
                    "Could not find all required entities for %s, calculation will be delayed.",
                    self.entity_id,
                )
                return

        # --- Start fresh on attributes
        self._attributes = {}

        # --- Calculate Air Speed (v_air) ---
        v_air = self._calculate_v_air()
        self._attributes["air_speed_ms_convective"] = round(v_air, 2)

        # --- Profile Info ---
        profile_key = self._config[CONF_ROOM_PROFILE]
        if self.id_profile_select:
            profile_state = self.hass.states.get(self.id_profile_select)
            if profile_state and profile_state.state not in ["unknown", "unavailable"]:
                profile_key = profile_state.state
        self._attributes["profile"] = profile_key
        self._attributes["orientation"] = self._config[CONF_ORIENTATION]

        # --- T_air (Input) ---
        t_air = self._get_float(self.entity_air, None)
        if t_air is None:
            return
        self._attributes["t_air"] = t_air

        # --- T_out (Input) ---
        t_out = self._get_attr(self.entity_weather, "temperature")
        if t_out is None:
            return

        t_app = self._get_attr(self.entity_weather, "apparent_temperature")
        t_out_eff = t_out
        t_out_source = "temperature"
        if t_app is not None and t_app < t_out:
            t_out_eff = t_app
            t_out_source = "apparent_temperature"
        self._attributes["t_out_eff"] = round(t_out_eff, 2)
        self._attributes["t_out_eff_source"] = t_out_source

        # --- Dynamic Factors (Inputs) ---
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

        # --- Wind (Input) ---
        wind_speed_ms = self._get_attr(self.entity_weather, "wind_speed", 0.0)
        weather_state_obj = self.hass.states.get(self.entity_weather)
        if (
            weather_state_obj
            and weather_state_obj.attributes.get("wind_speed_unit") == "km/h"
        ):
            wind_speed_ms = wind_speed_ms / 3.6
        wind_speed_kmh = wind_speed_ms * 3.6
        self._attributes["wind_ms"] = round(wind_speed_ms, 2)
        self._attributes["wind_kmh"] = round(wind_speed_kmh, 2)
        self._attributes["wind_source"] = "weather_entity"

        # --- Clouds/UV/Rain (Inputs) ---
        cloud = self._get_attr(self.entity_weather, "cloud_coverage", None)
        cloud_source = "weather_entity"
        if cloud is None:
            cloud = 50.0
            cloud_source = "fallback"
        self._attributes["cloud_coverage"] = cloud
        self._attributes["cloud_source"] = cloud_source
        uv = self._get_attr(self.entity_weather, "uv_index", None)
        uv_source = "weather_entity"
        if uv is None:
            uv = 0.0
            uv_source = "fallback"
        self._attributes["uv_index"] = uv
        self._attributes["uv_source"] = uv_source
        cond = weather_state_obj.state.lower() if weather_state_obj else ""
        is_raining = any(x in cond for x in ["rain", "pour", "snow", "hail"])
        rain_mul = 0.4 if is_raining else 1.0
        rain_source = "condition_string" if is_raining else "dry"
        self._attributes["rain_multiplier"] = rain_mul
        self._attributes["rain_source"] = rain_source
        elevation = self._get_attr("sun.sun", "elevation", 0.0)
        day_fac = max(0, min(1, (elevation + 6.0) / 66.0))
        self._attributes["daylight_factor"] = round(day_fac, 3)

        # --- Radiation (Calc) ---
        rad_source = "heuristic"
        rad_val = 0.0
        if self.entity_solar:
            rad = self._get_float(self.entity_solar, None)
            if rad is not None:
                rad_source = "sensor"
                rad_val = rad
                if rad_val > 1300:
                    _LOGGER.warning(
                        "Solar sensor value (%s W/m²) exceeds physical maximum. Using reported value.",
                        rad_val,
                    )
        if rad_source != "sensor":
            cloud_factor = max(0, 1 - (0.9 * (cloud / 100.0)))
            base = (90 * uv) if uv > 0 else (100 * day_fac)
            est = base * cloud_factor * rain_mul * day_fac
            rad_val = min(1000, est)
            rad_source = "heuristic"
        rad_final = max(0.0, rad_val)
        self._attributes["radiation"] = round(rad_final, 1)
        self._attributes["radiation_source"] = rad_source

        # --- Shading Factor ---
        shading_factor = self._get_shading_factor()
        self._attributes["shading_factor"] = round(shading_factor, 2)

        # --- CALCULATE RADIANT BOOST ---
        surface_setpoint = self._get_float(self.id_radiant_temp, 24.0)
        type_state = self.hass.states.get(self.id_radiant_type)
        type_key = type_state.state if type_state else "high_mass"
        system_props = RADIANT_TYPES.get(type_key, RADIANT_TYPES["high_mass"])
        boost_alpha = system_props["alpha"]
        view_factor = system_props["view_factor"]

        climate_state = (
            self.hass.states.get(self.entity_climate) if self.entity_climate else None
        )
        target_boost = 0.0
        if (
            self.is_radiant
            and climate_state
            and climate_state.attributes.get("hvac_action") == "heating"
        ):
            delta_t = surface_setpoint - t_air
            target_boost = delta_t * view_factor

        new_boost = ((1.0 - boost_alpha) * self._radiant_boost_stored) + (
            boost_alpha * target_boost
        )
        self._radiant_boost_stored = new_boost
        self._attributes["radiant_boost_current"] = round(new_boost, 2)

        # --- Incidence Factor ---
        incidence_factor = self._get_solar_incidence_factor()
        self._attributes["solar_incidence_factor"] = round(incidence_factor, 2)

        # --- MRT Calculation ---
        term_loss = (
            k_loss
            * (t_air - t_out_eff)
            * (f_out + 1.5 * f_win)
            * (1 + 0.02 * wind_speed_ms)
        )
        term_solar = (
            k_solar * (rad_final / 400.0) * incidence_factor * f_win * shading_factor
        )
        mrt_calc = t_air - term_loss + term_solar + new_boost

        self._attributes["loss_term"] = round(term_loss, 3)
        self._attributes["solar_term"] = round(term_solar, 3)
        self._attributes["mrt_unclamped"] = round(mrt_calc, 2)

        # --- Clamping ---
        lower_dyn = max(t_out_eff + 2.0, t_air - 3.0)
        upper_dyn = t_air + 4.0
        mrt_clamped = max(lower_dyn, min(mrt_calc, upper_dyn))
        self._attributes["mrt_clamped"] = round(mrt_clamped, 2)

        # --- Smoothing ---
        if self._mrt_prev is None:
            self._mrt_prev = mrt_clamped

        mrt_final = ((1.0 - alpha) * self._mrt_prev) + (alpha * mrt_clamped)
        self._mrt_prev = mrt_final

        # --- Final Value ---
        self._attr_native_value = round(mrt_final, 2)


class VirtualOperativeTempSensor(SensorEntity):
    # ... (Rest of VirtualOperativeTempSensor remains the same) ...
    """Calculates Operative Temp: (Air + MRT) / 2."""

    _attr_has_entity_name = True
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
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

    def _calculate_convective_weighting(self, v_air: float) -> float:
        """
        Calculates the Radiant Weighting factor (A) based on air speed (v_air)
        using the simplified ASHRAE heat transfer coefficients (hc and hr).

        The final formula is A = hr / (hc + hr).
        """

        # Ensure v_air is non-negative for math.pow
        v_air = max(0.0, v_air)

        # 1. Radiant Heat Transfer Coefficient (hr):
        # Standard value for a seated, sedentary occupant (W/(m^2*K))
        H_R = 4.7

        # 2. Convective Heat Transfer Coefficient (hc):
        # ASHRAE simplified formula for mixed (natural + forced) convection.
        # This formula is hc = 3.1 + 5.6 * (v_air ^ 0.6) for air speed > 0.1 m/s.
        if v_air <= 0.1:
            # Use a slightly lower value for pure natural convection (still air)
            H_C = 3.1
        else:
            # Apply air speed dependency (W/(m^2*K))
            H_C = 3.1 + 5.6 * (v_air**0.6)

        # 3. Final Radiant Weighting Factor (A):
        # A = hr / (hc + hr)
        radiant_weighting_A = H_R / (H_C + H_R)

        return radiant_weighting_A

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

                # --- NEW DYNAMIC T_op CALCULATION ---
                v_air = self._attributes.get(
                    "air_speed_ms_convective", DEFAULT_AIR_SPEED_STILL
                )

                # A = Radiant Weighting Factor
                radiant_weighting_A = self._calculate_convective_weighting(v_air)
                convective_weighting_B = 1.0 - radiant_weighting_A

                operative_temp = (convective_weighting_B * air) + (
                    radiant_weighting_A * mrt
                )
                # --- END NEW DYNAMIC T_op CALCULATION ---

                self._attr_native_value = round(operative_temp, 2)

                # Add/overwrite specific attributes
                self._attributes["mrt_smoothed"] = mrt
                self._attributes["t_air"] = air
                self._attributes["operative_temperature"] = operative_temp
                self._attributes["radiant_weighting_factor"] = round(
                    radiant_weighting_A, 2
                )
                self._attributes["convective_weighting_factor"] = round(
                    convective_weighting_B, 2
                )

                self.async_write_ha_state()
            except ValueError:
                self._attr_native_value = None
        else:
            self._attr_native_value = None
