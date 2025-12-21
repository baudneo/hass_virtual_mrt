"""Sensor platform for Virtual MRT."""

from __future__ import annotations

import logging
import math

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
    EntityCategory
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

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
    CONF_RH_SENSOR,
    CONF_WALL_SURFACE_SENSOR,
    CONF_WIND_SPEED_SENSOR,
    CONF_OUTDOOR_TEMP_SENSOR,
    CONF_OUTDOOR_HUMIDITY_SENSOR,
    CONF_PRESSURE_SENSOR,
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
    entities = [mrt_sensor, op_sensor]
    if config.get(CONF_RH_SENSOR):
        entities.extend(
            [
                VirtualDewPointSensor(hass, entry, device_info),
                VirtualFrostPointSensor(hass, entry, device_info),
                VirtualAbsoluteHumiditySensor(hass, entry, device_info),
                VirtualEnthalpySensor(hass, entry, device_info),
                VirtualHumidexSensor(hass, entry, device_info),
                VirtualPerceptionSensor(hass, entry, device_info),
                VirtualMoldRiskSensor(hass, entry, device_info),
                VirtualHeatFluxSensor(hass, entry, device_info),
            ]
        )
    if config.get(CONF_WALL_SURFACE_SENSOR):
        entities.append(VirtualCalibrationSensor(hass, entry, device_info))
    async_add_entities(entities)


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
        self.entity_wall_sensor = self._config.get(CONF_WALL_SURFACE_SENSOR)
        self.entity_outdoor_temp = self._config.get(CONF_OUTDOOR_TEMP_SENSOR)
        self.entity_outdoor_hum = self._config.get(CONF_OUTDOOR_HUMIDITY_SENSOR)
        self.entity_wind_speed = self._config.get(CONF_WIND_SPEED_SENSOR)
        orient_code = self._config[CONF_ORIENTATION]
        self.orientation_degrees = ORIENTATION_DEGREES.get(orient_code, 180)
        self._radiant_boost_stored = 0.0
        self.is_radiant = self._config.get(CONF_IS_RADIANT, False)

        self._attr_native_value = None
        self._mrt_prev = None
        self._attributes = {}
        self._last_update_time = 0.0
        self._min_update_interval = 60.0  # Seconds

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
        if self.entity_wall_sensor:
            entities_to_track.append(self.entity_wall_sensor)
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
        if self.entity_outdoor_temp:
            entities_to_track.append(self.entity_outdoor_temp)
        if self.entity_outdoor_hum:
            entities_to_track.append(self.entity_outdoor_hum)
        if self.entity_wind_speed:
            entities_to_track.append(self.entity_wind_speed)

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

    def _calculate_local_apparent_temp(self, t_out: float, wind_ms: float) -> float | None:
        """
        Calculates Apparent Temperature (AAT) using local sensors.
        Formula covers both Wind Chill and Humidity effects.
        AT = Ta + 0.33*e - 0.70*ws - 4.00
        """
        # 1. Get Outdoor Humidity (Local > Weather > Fail)
        rh_out = self._get_float(self.entity_outdoor_hum, None)
        if rh_out is None:
            w_state = self.hass.states.get(self.entity_weather)
            if w_state:
                rh_out = w_state.attributes.get("humidity")

        if rh_out is None:
            return None  # Cannot calculate without humidity

        # 2. Calculate Vapor Pressure (hPa)
        # Use the static helper from Psychrometrics
        vp_sat = Psychrometrics.calculate_vapor_pressure(t_out)
        vp_actual = vp_sat * (rh_out / 100.0)

        # 3. Apply AAT Formula
        # Note: wind_ms is raw here; in strict meteorology it's avg'd, but raw is fine.
        app_temp = t_out + (0.33 * vp_actual) - (0.70 * wind_ms) - 4.00

        return app_temp

    def _calculate_local_apparent_temp_OLD(
        self, t_out: float, wind_ms: float
    ) -> float | None:
        """
        Calculates Apparent Temperature (Feels Like) using local sensors.
        Approximation of Australian Apparent Temp formula (Steadman),
        which covers both Wind Chill and Humidity effects reasonably well.
        AT = Ta + 0.33*e - 0.70*ws - 4.00
        """
        # 1. Get Outdoor Humidity (Local or Weather)
        rh_out = self._get_float(self.entity_outdoor_hum, None)

        if rh_out is None:
            # Fallback to weather entity humidity
            w_state = self.hass.states.get(self.entity_weather)
            if w_state:
                rh_out = w_state.attributes.get("humidity")

        if rh_out is None:
            return None  # Cannot calculate without humidity

        # 2. Calculate Vapor Pressure (e) in hPa
        # Using the Psychrometrics helper we defined earlier
        vp_sat = Psychrometrics.calculate_vapor_pressure(t_out)
        vp_actual = vp_sat * (rh_out / 100.0)

        # 3. Apply Formula
        # AT = Ta + 0.33*e - 0.70*ws - 4.00
        # Note: Wind speed must be m/s.
        app_temp = t_out + (0.33 * vp_actual) - (0.70 * wind_ms) - 4.00

        return app_temp

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
        t_out = self._get_float(self.entity_outdoor_temp, None)
        if t_out is None:
            t_out = self._get_attr(self.entity_weather, "temperature")
        if t_out is None:
            # If we have absolutely no data, we can't run the physics model safely.
            return

        # --- Wind (Input) ---
        wind_speed_ms = self._get_float(self.entity_wind_speed, None)
        if wind_speed_ms is None:
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

        # We want the "Feels Like" temp because that drives heat loss better than dry bulb.
        # Try to calculate locally first (Most Accurate)
        t_app = self._calculate_local_apparent_temp(t_out, wind_speed_ms)
        t_out_source = "calculated_local_aat"

        if t_app is None:
            # Fallback to weather entity attribute
            t_app = self._get_attr(self.entity_weather, "apparent_temperature")
            t_out_source = "weather_entity_attr"

        # Use the lower of the two (Conservative for heating: Wind Chill matters)
        # If T_app is missing, just use T_out
        if t_app is not None and t_app < t_out:
            t_out_eff = t_app
        else:
            t_out_eff = t_out
            t_out_source = "dry_bulb_clamped"


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


class Psychrometrics:
    """Helper for thermodynamic calculations."""

    @staticmethod
    def calculate_humidity_ratio(vp_actual: float, pressure_hpa: float) -> float:
        """
        Calculate Mixing Ratio (W) in g_water / kg_dry_air.
        """
        # W = 0.622 * e / (P - e)
        # Result is kg/kg, multiply by 1000 for g/kg
        if (pressure_hpa - vp_actual) <= 0: return 0.0
        w = 0.622 * vp_actual / (pressure_hpa - vp_actual)
        return w * 1000.0

    @staticmethod
    def calculate_air_density(t_air: float, vp_actual: float, pressure_hpa: float) -> float:
        """
        Calculate Moist Air Density in kg/m³.
        """
        # Gas Constants
        R_d = 287.058  # Dry Air J/(kg·K)
        R_v = 461.495  # Water Vapor J/(kg·K)

        t_kelvin = t_air + 273.15
        p_total_pa = pressure_hpa * 100.0
        e_pa = vp_actual * 100.0
        p_dry_pa = p_total_pa - e_pa

        # density = (Pd / (Rd * T)) + (Pv / (Rv * T))
        rho = (p_dry_pa / (R_d * t_kelvin)) + (e_pa / (R_v * t_kelvin))
        return rho

    @staticmethod
    def calculate_vapor_pressure(t_air: float) -> float:
        """Calculate saturation vapor pressure (hPa) using Magnus formula."""
        return 6.112 * math.exp((17.67 * t_air) / (t_air + 243.5))

    @staticmethod
    def calculate_dew_point(t_air: float, rh: float) -> float:
        """Calculate Dew Point (°C)."""
        if rh <= 0:
            return -50.0  # Safety
        a = 17.27
        b = 237.7
        # Alpha parameter
        alpha = ((a * t_air) / (b + t_air)) + math.log(rh / 100.0)
        return (b * alpha) / (a - alpha)

    @staticmethod
    def calculate_frost_point(t_air: float, dew_point: float) -> float:
        """
        Calculate Frost Point (°C).
        Above 0°C, Frost Point = Dew Point.
        Below 0°C, Frost Point > Dew Point (saturation over ice).
        """
        if dew_point > 0:
            return dew_point
        # Simple approximation: T_fp = T_dp + (T_air - T_dp) / 10 (Simplified, but actual formula is complex iterative)
        # Better: Use a distinct formula for vapor pressure over ice.
        # Ideally, just use T_dp for user simplicity unless strict physics required.
        # Let's use the standard T_dp + Correction for sub-zero.
        return dew_point - (0.1 * (t_air - dew_point))  # Heuristic adjustment

    @staticmethod
    def calculate_enthalpy(
        t_air: float, rh: float, pressure_hpa: float = 1013.25
    ) -> float:
        """
        Calculate Air Enthalpy (kJ/kg).
        Requires Pressure in hPa (mbar).
        """
        vp_sat = Psychrometrics.calculate_vapor_pressure(t_air)
        vp_actual = vp_sat * (rh / 100.0)

        # Humidity Ratio (W) calculation depends on Pressure!
        # W = 0.622 * e / (P - e)
        # If P is lower (altitude), W is higher.
        w = 0.622 * vp_actual / (pressure_hpa - vp_actual)

        # H = 1.006*T + W*(2501 + 1.86*T)
        return (1.006 * t_air) + (w * (2501 + 1.86 * t_air))

    @staticmethod
    def calculate_humidex(t_air: float, dew_point: float) -> float:
        """Calculate Humidex (°C)."""
        # Humidex = T + 0.5555 * (e - 10)
        # e = vapor pressure in hPa (mbar)

        # Calculate e from dewpoint (inverse Magnus)
        e = 6.11 * math.exp(5417.7530 * ((1 / 273.16) - (1 / (273.15 + dew_point))))

        return t_air + 0.5555 * (e - 10)


class VirtualPsychroBase(SensorEntity):
    """Base class for sensors dependent on Air Temp and RH."""

    _attr_has_entity_name = True

    def __init__(self, hass, entry, device_info):
        self.hass = hass
        self._entry = entry
        self._attr_device_info = device_info
        self.entity_air = entry.data[CONF_AIR_TEMP_SOURCE]
        self.entity_rh = entry.data[CONF_RH_SENSOR]
        self.entity_pressure = entry.data.get(CONF_PRESSURE_SENSOR)
        self.entity_weather = entry.data[CONF_WEATHER_ENTITY]
        self._attributes = {}

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    async def async_added_to_hass(self):
        # Track air, rh, and optionally pressure or weather
        entities = [self.entity_air, self.entity_rh]
        if self.entity_pressure:
            entities.append(self.entity_pressure)
        elif self.entity_weather:
            entities.append(self.entity_weather)

        self.async_on_remove(
            async_track_state_change_event(self.hass, entities, self._handle_update)
        )
        self._handle_update(None)

    def _get_pressure(self) -> float:
        """
        Get absolute station pressure in hPa.

        Priority:
        1. Dedicated Sensor (Assumed to be Absolute/Station Pressure).
        2. Weather Entity (Assumed to be Sea-Level Pressure) -> Corrected for Elevation.
        3. Default (1013.25) -> Corrected for Elevation.
        """
        pressure_val = None
        is_sea_level = False

        # 1. Dedicated Sensor (Trust as Absolute)
        if self.entity_pressure:
            state = self.hass.states.get(self.entity_pressure)
            if state and state.state not in ["unknown", "unavailable"]:
                try:
                    # Return immediately - assume local sensor reads actual local pressure
                    return float(state.state)
                except ValueError:
                    pass

        # 2. Weather Entity (Assume Sea Level)
        if self.entity_weather:
            state = self.hass.states.get(self.entity_weather)
            if state:
                pres = state.attributes.get("pressure")
                if pres is not None:
                    pressure_val = float(pres)
                    is_sea_level = True  # Mark for correction

        # 3. Default Fallback
        if pressure_val is None:
            pressure_val = 1013.25
            is_sea_level = True

        # 4. Apply Elevation Correction if needed
        # If the source is Sea Level (Weather or Default), we must adjust down to Station Pressure.
        if is_sea_level:
            elevation = self.hass.config.elevation or 0
            if elevation > 0:
                # Standard Barometric Formula to convert Sea Level -> Station
                # P_station = P_sea * (1 - (0.0065 * h) / (T_std + 0.0065*h + 273.15)) ^ 5.257
                # Simplified ISA approximation (using T_std=15C):
                # Factor = (1 - (0.0000225577 * elevation)) ^ 5.25588
                correction_factor = (1 - (0.0000225577 * elevation)) ** 5.25588
                pressure_val = pressure_val * correction_factor

        return round(pressure_val, 2)

    @callback
    def _handle_update(self, event):
        t_state = self.hass.states.get(self.entity_air)
        rh_state = self.hass.states.get(self.entity_rh)

        if (
            not t_state
            or not rh_state
            or t_state.state in ["unknown", "unavailable"]
            or rh_state.state in ["unknown", "unavailable"]
        ):
            self._attr_native_value = None
            return

        try:
            t = float(t_state.state)
            rh = float(rh_state.state)
            pressure = self._get_pressure()

            self._attributes = {
                "input_air_temp": t,
                "input_relative_humidity": rh,
                "input_pressure_hpa": pressure,
            }

            self._update_value(t, rh, pressure)  # Pass pressure
            self.async_write_ha_state()
        except ValueError:
            self._attr_native_value = None

    def _update_value(self, t, rh, pressure):
        raise NotImplementedError


class VirtualDewPointSensor(VirtualPsychroBase):
    _attr_name = "Dew Point"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_suggested_display_precision = 1
    translation_key = "dew_point"
    _attr_unique_id_suffix = "dew_point"

    def __init__(self, hass, entry, device_info):
        super().__init__(hass, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_{self._attr_unique_id_suffix}"

    def _update_value(self, t, rh, pressure): # Accept extra arg
        self._attr_native_value = round(Psychrometrics.calculate_dew_point(t, rh), 1)


class VirtualFrostPointSensor(VirtualPsychroBase):
    _attr_name = "Frost Point"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_suggested_display_precision = 1
    translation_key = "frost_point"
    _attr_unique_id_suffix = "frost_point"

    def __init__(self, hass, entry, device_info):
        super().__init__(hass, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_{self._attr_unique_id_suffix}"

    def _update_value(self, t, rh, pressure):
        dp = Psychrometrics.calculate_dew_point(t, rh)
        self._attributes["calculated_dew_point"] = round(dp, 2)  # Show intermediate
        self._attr_native_value = round(Psychrometrics.calculate_frost_point(t, dp), 1)


class VirtualAbsoluteHumiditySensor(VirtualPsychroBase):
    _attr_name = "Absolute Humidity"
    _attr_native_unit_of_measurement = "g/m³"
    _attr_suggested_display_precision = 2
    translation_key = "absolute_humidity"
    _attr_unique_id_suffix = "abs_humidity"
    _attr_icon = "mdi:water"
    _attr_device_class = SensorDeviceClass.ABSOLUTE_HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hass, entry, device_info):
        super().__init__(hass, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_{self._attr_unique_id_suffix}"

    def _update_value(self, t, rh, pressure):
        # 1. Standard Volumetric Humidity (g/m³) - Pressure Independent approx
        # abs_hum = (6.112 * e^(...) * rh * 2.1674) / (273.15 + T)
        vp_sat = Psychrometrics.calculate_vapor_pressure(t)
        vp_actual = vp_sat * (rh / 100.0)
        t_kelvin = t + 273.15

        # Volumetric Abs Humidity (g/m³)
        val_volumetric = (1000.0 * vp_actual * 100.0) / (461.5 * t_kelvin)
        self._attr_native_value = round(val_volumetric, 2)

        # 2. Engineering Metrics (Pressure Dependent)
        mixing_ratio = Psychrometrics.calculate_humidity_ratio(vp_actual, pressure)
        air_density = Psychrometrics.calculate_air_density(t, vp_actual, pressure)

        self._attributes["humidity_ratio_g_kg"] = round(mixing_ratio, 2)
        self._attributes["air_density_kg_m3"] = round(air_density, 3)
        self._attributes["vapor_pressure_hpa"] = round(vp_actual, 2)


class VirtualEnthalpySensor(VirtualPsychroBase):
    _attr_name = "Air Enthalpy"
    _attr_native_unit_of_measurement = "kJ/kg"
    _attr_suggested_display_precision = 2
    translation_key = "enthalpy"
    _attr_unique_id_suffix = "enthalpy"
    _attr_icon = "mdi:chart-bell-curve"

    def __init__(self, hass, entry, device_info):
        super().__init__(hass, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_{self._attr_unique_id_suffix}"

    def _update_value(self, t, rh, pressure):
        # Pass the dynamic pressure to the math helper
        self._attr_native_value = round(Psychrometrics.calculate_enthalpy(t, rh, pressure), 2)


class VirtualHumidexSensor(VirtualPsychroBase):
    _attr_name = "Humidex"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_suggested_display_precision = 1
    translation_key = "humidex"
    _attr_unique_id_suffix = "humidex"

    def __init__(self, hass, entry, device_info):
        super().__init__(hass, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_{self._attr_unique_id_suffix}"

    def _update_value(self, t, rh, pressure):
        dp = Psychrometrics.calculate_dew_point(t, rh)
        self._attributes["calculated_dew_point"] = round(dp, 2)
        self._attr_native_value = round(Psychrometrics.calculate_humidex(t, dp), 1)


class VirtualPerceptionSensor(VirtualPsychroBase):
    _attr_name = "Thermal Perception"
    _attr_device_class = SensorDeviceClass.ENUM
    translation_key = "perception"
    _attr_unique_id_suffix = "perception"
    _attr_options = [
        "comfortable",
        "noticeable_discomfort",
        "evident_discomfort",
        "intense_discomfort",
        "dangerous_discomfort",
        "heat_stroke_imminent",
    ]
    _attr_icon = "mdi:emoticon-happy"

    def __init__(self, hass, entry, device_info):
        super().__init__(hass, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_{self._attr_unique_id_suffix}"

    def _update_value(self, t, rh, pressure):
        dp = Psychrometrics.calculate_dew_point(t, rh)
        humidex = Psychrometrics.calculate_humidex(t, dp)

        self._attributes["calculated_dew_point"] = round(dp, 2)
        self._attributes["calculated_humidex"] = round(humidex, 1)

        if humidex < 30:
            self._attr_native_value = "comfortable"
            self._attr_icon = "mdi:emoticon-happy"
        elif humidex < 35:
            self._attr_native_value = "noticeable_discomfort"
            self._attr_icon = "mdi:emoticon-neutral"
        elif humidex < 40:
            self._attr_native_value = "evident_discomfort"
            self._attr_icon = "mdi:emoticon-sad"
        elif humidex < 46:
            self._attr_native_value = "intense_discomfort"
            self._attr_icon = "mdi:emoticon-cry"
        elif humidex < 54:
            self._attr_native_value = "dangerous_discomfort"
            self._attr_icon = "mdi:alert"
        else:
            self._attr_native_value = "heat_stroke_imminent"
            self._attr_icon = "mdi:alert-octagon"


class VirtualMoldRiskSensor(VirtualPsychroBase):
    """
    Calculates Mold Risk based on the estimated humidity at the wall surface.
    Uses k_loss and T_out to model the wall temperature drop.
    """

    _attr_name = "Mold Risk"
    _attr_native_unit_of_measurement = "%"  # Reporting 'Surface RH' as the risk metric
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    translation_key = "mold_risk"
    _attr_unique_id_suffix = "mold_risk"
    _attr_icon = "mdi:bacteria-outline"

    def __init__(self, hass, entry, device_info):
        super().__init__(hass, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_{self._attr_unique_id_suffix}"

        # We need to look up k_loss dynamically
        self.id_k_loss = None
        self.entity_weather = entry.data[CONF_WEATHER_ENTITY]
        self.entity_wall_sensor = entry.data.get(CONF_WALL_SURFACE_SENSOR)
        self.entity_outdoor_temp = entry.data.get(CONF_OUTDOOR_TEMP_SENSOR)

    async def async_added_to_hass(self):
        """Register listeners (extending base to find k_loss)."""
        await super().async_added_to_hass()

        # Find the k_loss number entity for this device
        registry = er.async_get(self.hass)
        self.id_k_loss = registry.async_get_entity_id(
            "number", DOMAIN, f"{self._entry.entry_id}_k_loss"
        )
        entities_to_track = [self.entity_weather]
        if self.id_k_loss:
            entities_to_track.append(self.id_k_loss)
        if self.entity_wall_sensor:
            entities_to_track.append(self.entity_wall_sensor)
        if self.entity_outdoor_temp:
            entities_to_track.append(self.entity_outdoor_temp)

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, entities_to_track, self._handle_update
            )
        )

    def _get_float_state(self, entity_id, default=0.0):
        if not entity_id:
            return default
        state = self.hass.states.get(entity_id)
        if state and state.state not in ["unknown", "unavailable"]:
            try:
                return float(state.state)
            except ValueError:
                pass
        return default

    def _update_value(self, t_air, rh, pressure):
        # 1. Get Outdoor Temp (Priority: Sensor -> Weather -> Fallback)
        t_out = None

        # Try dedicated sensor
        if self.entity_outdoor_temp:
            t_out = self._get_float_state(self.entity_outdoor_temp, None)

        # Try weather entity
        if t_out is None:
            w_state = self.hass.states.get(self.entity_weather)
            if w_state:
                t_out = w_state.attributes.get("temperature")

        # Fallback to indoor temp (implies Delta T = 0)
        if t_out is None:
            t_out = t_air

        # 2. Determine Wall Surface Temperature (T_surface)
        t_surface = None
        calc_method = "calculated_k_loss"

        # A. Try Physical Sensor
        if self.entity_wall_sensor:
            val = self._get_float_state(self.entity_wall_sensor, None)
            if val is not None:
                t_surface = val
                calc_method = "physical_sensor"

        # B. Fallback to Calculation
        if t_surface is None:
            k_loss = self._get_float_state(self.id_k_loss, 0.14)

            delta_t = t_air - t_out
            wall_temp_drop = 0.0
            if delta_t > 0:
                # Formula: T_surf = T_air - (Delta_T * k_loss)
                wall_temp_drop = delta_t * k_loss

            t_surface = t_air - wall_temp_drop

            self._attributes["insulation_factor_k"] = k_loss

        # 3. Calculate Relative Humidity at the Surface (Surface RH)
        # This is the critical step: What is the RH of the ROOM AIR when it touches the COLD WALL?

        # Room Vapor Pressure (Water content in the air mass)
        vp_room = Psychrometrics.calculate_vapor_pressure(t_air) * (rh / 100.0)

        # Saturation Vapor Pressure at the cold wall surface (Max water it can hold)
        vp_sat_surface = Psychrometrics.calculate_vapor_pressure(t_surface)

        # Calculate Surface RH
        if vp_sat_surface == 0:
            surface_rh = 100.0
        else:
            surface_rh = (vp_room / vp_sat_surface) * 100.0

        surface_rh = min(100.0, max(0.0, surface_rh))

        self._attr_native_value = round(surface_rh, 1)

        # Attributes
        self._attributes["outdoor_temp"] = t_out
        self._attributes["wall_surface_temp"] = round(t_surface, 1)
        self._attributes["calculation_method"] = calc_method

        # Set Risk Levels
        if surface_rh < 60:
            self._attributes["risk_level"] = "Low"
            self._attr_icon = "mdi:shield-check"
        elif surface_rh < 80:
            self._attributes["risk_level"] = "Warning"
            self._attr_icon = "mdi:alert-box-outline"
        else:
            self._attributes["risk_level"] = "Critical"
            self._attr_icon = "mdi:alert-decagram"

class VirtualCalibrationSensor(SensorEntity):
    """
    Diagnostic sensor that calculates the theoretical k_loss based on
    measured wall temperatures.
    """
    _attr_has_entity_name = True
    _attr_name = "Estimated Insulation Factor"
    _attr_icon = "mdi:ruler-square-compass"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC # Keeps it out of the main dashboard

    # We don't set a unit because it's a factor (ratio), but we could use "k"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_info):
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_calibration_k"
        self._attr_device_info = device_info

        self.entity_air = entry.data[CONF_AIR_TEMP_SOURCE]
        self.entity_weather = entry.data[CONF_WEATHER_ENTITY]
        self.entity_wall = entry.data[CONF_WALL_SURFACE_SENSOR]

        # Attributes to help the user debug
        self._attributes = {}

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_added_to_hass(self):
        """Track sensors."""
        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                [self.entity_air, self.entity_weather, self.entity_wall, "sun.sun"],
                self._handle_update
            )
        )
        self._handle_update(None)

    @callback
    def _handle_update(self, event):
        # 1. Check Sun (Must be down for valid reading)
        sun = self.hass.states.get("sun.sun")
        is_daytime = sun and sun.state == "above_horizon"

        # 2. Get Temperatures
        try:
            t_air = float(self.hass.states.get(self.entity_air).state)
            t_wall = float(self.hass.states.get(self.entity_wall).state)

            # Get Outdoor Temp (Prefer raw temp for calibration as wind chill
            # effects are complex, but using T_out allows pure U-value estimation)
            w_state = self.hass.states.get(self.entity_weather)
            t_out = float(w_state.attributes.get("temperature"))
        except (ValueError, AttributeError, TypeError):
            self._attr_native_value = None
            self.async_write_ha_state()
            return

        # 3. Calculate Delta T (Indoor - Outdoor)
        # We need a significant drop to get a valid reading. > 10°C is good practice.
        delta_t_total = t_air - t_out

        self._attributes = {
            "t_air": t_air,
            "t_wall": t_wall,
            "t_out": t_out,
            "delta_t": round(delta_t_total, 1),
            "valid_conditions": False
        }

        # 4. Validity Checks
        if is_daytime:
            self._attributes["status"] = "Invalid: Sun is up"
            self._attr_native_value = None # Or keep last known
        elif delta_t_total < 10:
            self._attributes["status"] = "Invalid: Low Delta T (<10°C)"
            self._attr_native_value = None
        else:
            # 5. The Math
            # Temp Drop across the room air film + wall = T_air - T_out
            # Temp Drop inside the room = T_air - T_wall
            # Factor k = (T_air - T_wall) / (T_air - T_out)

            # Note: This is an approximation assuming the "2.5" multiplier
            # used in the Mold Sensor logic is implicit in the k_loss definition.
            # However, for the raw k_loss input, we simply want the ratio of heat lost.

            # If our model is: T_surf = T_air - (Delta_T * k_loss * 2.5)
            # Then: T_air - T_surf = Delta_T * k_loss * 2.5
            # And: k_loss = (T_air - T_surf) / (Delta_T * 2.5)

            drop_internal = t_air - t_wall

            if drop_internal < 0:
                # Wall is warmer than air? (Heating is hitting sensor?)
                self._attributes["status"] = "Invalid: Wall warmer than air"
                self._attr_native_value = None
            else:
                # Calculate k based on the formula used in the Mold Sensor
                calc_k = drop_internal / (delta_t_total * 2.5)

                # Clamp to realistic bounds
                final_k = min(1.0, max(0.0, calc_k))

                self._attr_native_value = round(final_k, 3)
                self._attributes["status"] = "Valid Calculation"
                self._attributes["valid_conditions"] = True

        self.async_write_ha_state()


class VirtualHeatFluxSensor(VirtualPsychroBase):
    """
    Calculates Heat Flux (Energy Loss) through the wall in W/m².
    Also estimates the effective R-Value/U-Value of the assembly.
    """
    _attr_name = "Wall Heat Flux"
    _attr_native_unit_of_measurement = "W/m²"
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    translation_key = "heat_flux"
    _attr_unique_id_suffix = "heat_flux"
    _attr_icon = "mdi:transfer-down"

    def __init__(self, hass, entry, device_info):
        super().__init__(hass, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_{self._attr_unique_id_suffix}"

        # Lookups for required inputs
        self.id_k_loss = None
        self.entity_wall_sensor = entry.data.get(CONF_WALL_SURFACE_SENSOR)
        self.entity_outdoor_temp = entry.data.get(CONF_OUTDOOR_TEMP_SENSOR)

    async def async_added_to_hass(self):
        """Register listeners."""
        await super().async_added_to_hass()
        registry = er.async_get(self.hass)
        self.id_k_loss = registry.async_get_entity_id(
            "number", DOMAIN, f"{self._entry.entry_id}_k_loss"
        )

        entities = [self.entity_weather]
        if self.id_k_loss: entities.append(self.id_k_loss)
        if self.entity_wall_sensor: entities.append(self.entity_wall_sensor)
        if self.entity_outdoor_temp: entities.append(self.entity_outdoor_temp)

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, entities, self._handle_update
            )
        )

    def _get_float_state(self, entity_id, default=0.0):
        if not entity_id: return default
        state = self.hass.states.get(entity_id)
        if state and state.state not in ["unknown", "unavailable"]:
            try:
                return float(state.state)
            except ValueError:
                pass
        return default

    def _update_value(self, t_air, rh, pressure=None):  # pressure unused here but keeps signature
        # 1. Get Outdoor Temp
        t_out = None
        if self.entity_outdoor_temp:
            t_out = self._get_float_state(self.entity_outdoor_temp, None)
        if t_out is None:
            w_state = self.hass.states.get(self.entity_weather)
            if w_state: t_out = w_state.attributes.get("temperature")
        if t_out is None: t_out = t_air - 10  # Fail safe default

        # 2. Determine Wall Surface Temp
        t_surface = None
        if self.entity_wall_sensor:
            val = self._get_float_state(self.entity_wall_sensor, None)
            if val is not None: t_surface = val

        if t_surface is None:
            k_loss = self._get_float_state(self.id_k_loss, 0.14)
            t_surface = t_air - ((t_air - t_out) * k_loss)

        # 3. Calculate Flux
        # Standard ASHRAE Film Coefficient (h_i) for vertical surfaces = 8.29 W/m²K
        h_film = 8.29

        delta_t_surface = t_air - t_surface

        # Flux = h * delta_T
        # We clamp at 0 because walls don't usually generate heat (unless radiant, but that's complex)
        heat_flux = max(0.0, h_film * delta_t_surface)

        self._attr_native_value = round(heat_flux, 1)

        # 4. Estimate Insulation Quality (R-Value / U-Value)
        # Only valid if there is a significant temp difference (>5C)
        delta_t_total = t_air - t_out
        if delta_t_total > 5.0 and heat_flux > 0.5:
            # R_total = Delta_T_Total / Flux
            r_si = delta_t_total / heat_flux
            u_val = 1.0 / r_si

            # Conversions
            r_imperial = r_si * 5.678  # Convert RSI to R-Value (US/Can)

            self._attributes["estimated_r_value_imperial"] = round(r_imperial, 1)
            self._attributes["estimated_rsi"] = round(r_si, 2)
            self._attributes["estimated_u_value"] = round(u_val, 3)
        else:
            self._attributes["estimated_r_value_imperial"] = "N/A (Delta T too low)"

        self._attributes["wall_surface_temp"] = round(t_surface, 1)
        self._attributes["outdoor_temp"] = t_out
