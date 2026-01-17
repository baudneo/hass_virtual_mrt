"""Sensor platform for Virtual MRT."""

from __future__ import annotations

import logging
import math
import time

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
    EntityCategory,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTemperature, CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event, async_call_later

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
    CONF_MIN_UPDATE_INTERVAL,
    CONF_DEVICE_TYPE,
    TYPE_AGGREGATOR,
    CONF_ROOM_AREA,
    DEFAULT_ROOM_AREA,
    DEFAULT_CEILING_HEIGHT,
    CONF_FLOOR_LEVEL,
    CONF_CEILING_HEIGHT,
    get_device_info,
    CONF_CALIBRATION_RH_SENSOR,
    CONF_PRECIPITATION_SENSOR,
    CONF_UV_INDEX_SENSOR,
    CONF_IS_HVAC_ZONE, DEFAULT_ROOM_FLOOR, DEFAULT_ZONE_AREA,
    CONF_EXTERIOR_WALL_AREA,
    CONF_WINDOW_AREA,
    CONF_WINDOW_U_VALUE,
    DEFAULT_WINDOW_U_VALUE,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up sensors from a config entry."""
    config = entry.data
    device_type = config.get(
        CONF_DEVICE_TYPE, "room"
    )  # Default to room for old configs
    device_info = await get_device_info({(DOMAIN, entry.entry_id)}, config[CONF_NAME])

    # --- BRANCH 1: AGGREGATOR ---
    if device_type == TYPE_AGGREGATOR:
        async_add_entities([VirtualZoneAggregator(hass, entry, device_info)])
        return
    # --- BRANCH 2: ROOM SENSOR SET ---
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
                VirtualHeatFluxSensor(hass, entry, device_info, mrt_sensor),
                VirtualPMVSensor(hass, entry, device_info, mrt_sensor),
                VirtualMoistureExcessSensor(hass, entry, device_info),
            ]
        )
    if config.get(CONF_WALL_SURFACE_SENSOR):
        entities.append(VirtualCalibrationSensor(hass, entry, device_info))
    async_add_entities(entities)


class VirtualMRTSensorOLD(SensorEntity):
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
        self.entity_rain = self._config.get(CONF_PRECIPITATION_SENSOR)
        self.entity_uv = self._config.get(CONF_UV_INDEX_SENSOR)
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

        self._min_update_interval = self._config.get(CONF_MIN_UPDATE_INTERVAL, 30.0)
        self._last_update_time = 0.0
        self._cancel_scheduled_update = None

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
        if self.entity_rain:
            entities_to_track.append(self.entity_rain)
        if self.entity_uv:
            entities_to_track.append(self.entity_uv)

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
        """Handle entity state changes with Rate Limiting."""
        now = time.time()
        time_since = now - self._last_update_time

        # 1. If interval is 0, update instantly (No throttle)
        if self._min_update_interval <= 0:
            self._perform_update()
            return

        # 2. If enough time has passed, update immediately
        if time_since >= self._min_update_interval:
            self._perform_update()
        else:
            # 3. If too soon, schedule an update for the end of the interval
            # We cancel any existing timer so we don't stack updates
            if self._cancel_scheduled_update:
                self._cancel_scheduled_update()
                self._cancel_scheduled_update = None

            delay = self._min_update_interval - time_since
            self._cancel_scheduled_update = async_call_later(
                self.hass, delay, self._scheduled_update_callback
            )

    @callback
    def _scheduled_update_callback(self, _):
        """Called when the rate-limit timer expires."""
        self._cancel_scheduled_update = None
        self._perform_update()

    def _perform_update(self):
        """Actually run the calc and write state."""
        self._last_update_time = time.time()
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

    def _calculate_local_apparent_temp(
        self, t_out: float, wind_ms: float
    ) -> float | None:
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
        # --- UV Logic ---
        uv = None
        uv_source = "fallback"

        # 1. Try Dedicated Sensor
        if self.entity_uv:
            uv = self._get_float(self.entity_uv, None)
            if uv is not None:
                uv_source = "sensor"

        # 2. Try Weather Entity
        if uv is None:
            uv = self._get_attr(self.entity_weather, "uv_index", None)
            if uv is not None:
                uv_source = "weather_entity"

        # 3. Fallback
        if uv is None:
            uv = 0.0

        self._attributes["uv_index"] = uv
        self._attributes["uv_source"] = uv_source

        # --- RAIN LOGIC ---
        is_raining = False
        rain_source = "unknown"

        # 1. Try Dedicated Sensor (Rate > 0)
        if self.entity_rain:
            rain_rate = self._get_float(self.entity_rain, None)
            if rain_rate is not None:
                is_raining = rain_rate > 0.0
                rain_source = "sensor"

        # 2. Try Weather Entity State (String match)
        if rain_source == "unknown":
            weather_state_obj = self.hass.states.get(self.entity_weather)
            cond = weather_state_obj.state.lower() if weather_state_obj else ""
            is_raining = any(x in cond for x in ["rain", "pour", "snow", "hail"])
            rain_source = "weather_entity_condition_string" if weather_state_obj else "fallback"

        rain_mul = 0.4 if is_raining else 1.0
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

        # --- Estimated Wall Surface Temp ---
        # Theoretical inner surface temp of the exterior wall
        # T_surf = T_air - (Delta_T * k_loss)
        # We use t_out_eff to account for wind chill cooling the exterior
        if t_air is not None and t_out_eff is not None:
            t_wall_est = t_air - ((t_air - t_out_eff) * k_loss)
            self._attributes["estimated_wall_surface_temp"] = round(t_wall_est, 1)

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
        self._room_area = entry.data.get(CONF_ROOM_AREA, DEFAULT_ROOM_AREA)
        self._floor_level = entry.data.get(CONF_FLOOR_LEVEL, 1)
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
                self._attributes["room_area_m2"] = self._room_area
                self._attributes["mrt_smoothed"] = mrt
                self._attributes["t_air"] = air
                self._attributes["operative_temperature"] = operative_temp
                self._attributes["radiant_weighting_factor"] = round(
                    radiant_weighting_A, 2
                )
                self._attributes["convective_weighting_factor"] = round(
                    convective_weighting_B, 2
                )
                self._attributes["floor_level"] = self._floor_level

                self.async_write_ha_state()
            except ValueError:
                self._attr_native_value = None
        else:
            self._attr_native_value = None


class Psychrometrics:
    """Helper for thermodynamic calculations."""

    @staticmethod
    def calculate_pmv(t_air, t_mrt, v_air, rh, met, clo):
        """
        Calculate PMV (Predicted Mean Vote) using ISO 7730 / ASHRAE 55.
        """
        # 1. Convert Inputs
        ta = t_air
        tr = t_mrt
        vel = max(0.1, v_air)  # Min velocity for stability
        rh_frac = rh / 100.0

        # Metabolism: 1 met = 58.15 W/m2
        m = met * 58.15

        # External Work (assume 0 for home/office)
        w = 0.0

        # Internal Heat Production
        mw = m - w

        # Clothing Insulation: 1 clo = 0.155 m2K/W
        icl = clo * 0.155

        # Clothing Area Factor (fcl)
        if icl <= 0.078:
            fcl = 1.0 + (1.29 * icl)
        else:
            fcl = 1.05 + (0.645 * icl)

        # Vapor Pressure (Pa)
        # Use existing helper but convert hPa -> Pa
        vp_hpa = Psychrometrics.calculate_vapor_pressure(ta) * rh_frac
        pa = vp_hpa * 100.0

        # 2. Iterative Calculation for Clothing Surface Temp (t_cl)
        # Starting guess: t_cl = t_air
        t_cl = ta
        t_abs = ta + 273.15
        tr_abs = tr + 273.15

        # Iteration variables
        hc = 12.1 * math.sqrt(vel)  # Convective heat transfer coef
        n_iter = 0
        eps = 0.00015  # Stopping tolerance

        while n_iter < 150:
            t_cl_old = t_cl
            t_cl_abs = t_cl + 273.15

            # Radiative Heat Transfer
            # h_r = 4 * sigma * f_cl ... simplified for linearization
            # We compute terms directly in balance equation below

            # Convection coeff (hc) depends on T_cl vs T_air (Natural vs Forced)
            hc_forced = 12.1 * math.sqrt(vel)
            hc_natural = 2.38 * abs(t_cl - ta) ** 0.25
            hc = max(hc_forced, hc_natural)

            # Heat Balance Equation terms
            # Radiation Term: 3.96*10^-8 * fcl * (Tcl^4 - Tr^4)
            rad = 3.96 * 10**-8 * fcl * (t_cl_abs**4 - tr_abs**4)

            # Convection Term: fcl * hc * (Tcl - Ta)
            conv = fcl * hc * (t_cl - ta)

            # T_cl new estimate
            # T_cl = 35.7 - 0.028(M-W) - I_cl * (Rad + Conv)
            t_cl_new = (35.7 - 0.028 * mw) - (icl * (rad + conv))

            # Dampening
            t_cl = (t_cl_new + t_cl_old) / 2.0

            if abs(t_cl - t_cl_old) < eps:
                break
            n_iter += 1

        # 3. Calculate Heat Loss Components (ISO 7730)
        # Skin diffusion
        hl1 = 3.05 * 0.001 * (5733 - (6.99 * mw) - pa)
        # Sweat (Latent)
        if mw > 58.15:
            hl2 = 0.42 * (mw - 58.15)
        else:
            hl2 = 0.0
        # Latent Respiration
        hl3 = 1.7 * 0.00001 * m * (5867 - pa)
        # Dry Respiration
        hl4 = 0.0014 * m * (34 - ta)
        # Radiation
        hl5 = 3.96 * 10**-8 * fcl * ((t_cl + 273.15) ** 4 - tr_abs**4)
        # Convection
        hl6 = fcl * hc * (t_cl - ta)

        # 4. Final PMV Calc
        ts = 0.303 * math.exp(-0.036 * m) + 0.028
        pmv = ts * (mw - hl1 - hl2 - hl3 - hl4 - hl5 - hl6)

        return max(-3.5, min(3.5, pmv))  # Clamp to valid range

    @staticmethod
    def calculate_humidity_ratio(vp_actual: float, pressure_hpa: float) -> float:
        """
        Calculate Mixing Ratio (W) in g_water / kg_dry_air.
        """
        # W = 0.622 * e / (P - e)
        # Result is kg/kg, multiply by 1000 for g/kg
        if (pressure_hpa - vp_actual) <= 0:
            return 0.0
        w = 0.622 * vp_actual / (pressure_hpa - vp_actual)
        return w * 1000.0

    @staticmethod
    def calculate_air_density(
        t_air: float, vp_actual: float, pressure_hpa: float
    ) -> float:
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

    def _update_value(self, t, rh, pressure):  # Accept extra arg
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

        # Lookups for Outdoor data
        self.entity_outdoor_temp = entry.data.get(CONF_OUTDOOR_TEMP_SENSOR)
        self.entity_outdoor_hum = entry.data.get(CONF_OUTDOOR_HUMIDITY_SENSOR)

    async def async_added_to_hass(self):
        """Register listeners (extending base)."""
        # Base tracks Indoor T, Indoor RH, Pressure, Weather
        # We override to include outdoor sensors in the listener list
        entities = [self.entity_air, self.entity_rh]
        if self.entity_pressure:
            entities.append(self.entity_pressure)
        elif self.entity_weather:
            entities.append(self.entity_weather)

        # Track dedicated outdoor sensors if they exist
        if self.entity_outdoor_temp:
            entities.append(self.entity_outdoor_temp)
        if self.entity_outdoor_hum:
            entities.append(self.entity_outdoor_hum)

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, entities, self._handle_update
            )
        )
        self._handle_update(None)

    def _get_float_state(self, entity_id):
        """Helper to safely get float state."""
        if not entity_id: return None
        state = self.hass.states.get(entity_id)
        if state and state.state not in ["unknown", "unavailable"]:
            try:
                return float(state.state)
            except ValueError:
                pass
        return None

    def _update_value(self, t, rh, pressure):
        # 1. Calculate Indoor Enthalpy
        h_in = Psychrometrics.calculate_enthalpy(t, rh, pressure)
        self._attr_native_value = round(h_in, 2)

        # 2. Get Outdoor Data (Priority: Dedicated Sensors -> Weather Fallback)
        t_out = self._get_float_state(self.entity_outdoor_temp)
        rh_out = self._get_float_state(self.entity_outdoor_hum)
        source_type = "dedicated_sensors"

        # Fallback to Weather Entity if dedicated sensors are missing or unavailable
        if t_out is None or rh_out is None:
            w_state = self.hass.states.get(self.entity_weather)
            if w_state:
                # Only overwrite if we didn't find the specific sensor value
                if t_out is None:
                    t_out = w_state.attributes.get("temperature")
                if rh_out is None:
                    rh_out = w_state.attributes.get("humidity")
                source_type = "weather_entity"

        # 3. Calculate Outdoor Enthalpy & Compare
        if t_out is not None and rh_out is not None:
            try:
                # Ensure values are floats (weather attrs might be ints)
                t_out = float(t_out)
                rh_out = float(rh_out)

                h_out = Psychrometrics.calculate_enthalpy(t_out, rh_out, pressure)

                self._attributes["outdoor_enthalpy"] = round(h_out, 2)
                self._attributes["outdoor_source"] = source_type

                # Difference: Positive means Inside has MORE energy (Open windows to cool)
                # Negative means Inside has LESS energy (Keep windows closed to stay cool)
                diff = h_in - h_out
                self._attributes["enthalpy_difference"] = round(diff, 2)

                # Simple recommendation state
                if diff > 1.0:
                    self._attributes["economizer_status"] = "Free Cooling Available"
                elif diff < -1.0:
                    self._attributes["economizer_status"] = "Unfavorable (Keep Closed)"
                else:
                    self._attributes["economizer_status"] = "Neutral"

            except (ValueError, TypeError):
                pass


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
    Calculates Mold Risk.
    Prioritizes physical Surface Humidity measurement if available.
    Falls back to calculating estimated humidity at the wall surface using T_out/k_loss.
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
        self.entity_cal_rh = entry.data.get(CONF_CALIBRATION_RH_SENSOR)  # <--- New Input
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
        if self.entity_cal_rh:  # <--- Track New Sensor
            entities_to_track.append(self.entity_cal_rh)
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
        # --- 1. TRY DIRECT MEASUREMENT (The Gold Standard) ---
        if self.entity_cal_rh:
            direct_rh = self._get_float_state(self.entity_cal_rh, None)
            if direct_rh is not None:
                self._attr_native_value = round(direct_rh, 1)
                self._attributes["calculation_method"] = "measured_surface_humidity"
                self._set_risk_level(direct_rh)
                # We still calculate the rest for context attributes, but the State is real.
                # (Optional: return early if you don't care about theoretical attributes)

        # --- 2. PREPARE DATA FOR CALCULATION ---
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

        # A. Try Physical Sensor
        if self.entity_wall_sensor:
            val = self._get_float_state(self.entity_wall_sensor, None)
            if val is not None:
                t_surface = val

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

        # --- 3. DECIDE FINAL OUTPUT ---
        # If we didn't have a direct sensor, use the calculated value
        if self._attr_native_value is None or self._attributes.get("calculation_method") != "measured_surface_humidity":
            self._attr_native_value = round(surface_rh, 1)

            if self.entity_wall_sensor and self._get_float_state(self.entity_wall_sensor, None) is not None:
                self._attributes["calculation_method"] = "calculated_using_wall_temp_sensor"
            else:
                self._attributes["calculation_method"] = "calculated_using_k_loss"

            self._set_risk_level(surface_rh)

        # Attributes
        self._attributes["outdoor_temp"] = t_out
        self._attributes["wall_surface_temp"] = round(t_surface, 1)
        self._attributes["theoretical_surface_rh"] = round(surface_rh, 1)

    def _set_risk_level(self, rh_val):
        """Helper to set icon and risk text based on RH."""
        if rh_val < 60:
            self._attributes["risk_level"] = "Low"
            self._attr_icon = "mdi:shield-check"
        elif rh_val < 80:
            self._attributes["risk_level"] = "Warning"
            self._attr_icon = "mdi:alert-box-outline"
        else:
            self._attributes["risk_level"] = "Critical"
            self._attr_icon = "mdi:alert-decagram"


class VirtualCalibrationSensor(SensorEntity):
    """
    Diagnostic sensor that calculates the theoretical k_loss based on
    measured wall temperatures.

    NEW: Now also validates the calibration seal by comparing Absolute Humidity.
    """

    _attr_has_entity_name = True
    _attr_name = "Estimated Insulation Factor"
    _attr_icon = "mdi:ruler-square-compass"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = (
        EntityCategory.DIAGNOSTIC
    )  # Keeps it out of the main dashboard

    # We don't set a unit because it's a factor (ratio), but we could use "k"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_info):
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_calibration_k"
        self._attr_device_info = device_info

        self.entity_air = entry.data[CONF_AIR_TEMP_SOURCE]
        self.entity_rh = entry.data.get(CONF_RH_SENSOR)  # Room RH
        self.entity_weather = entry.data[CONF_WEATHER_ENTITY]
        self.entity_wall = entry.data[CONF_WALL_SURFACE_SENSOR]  # Wall Temp
        self.entity_cal_rh = entry.data.get(CONF_CALIBRATION_RH_SENSOR)  # Wall RH

        # Attributes to help the user debug
        self._attributes = {}

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_added_to_hass(self):
        """Track sensors."""
        entities = [self.entity_air, self.entity_weather, self.entity_wall, "sun.sun"]
        if self.entity_cal_rh:
            entities.append(self.entity_cal_rh)
        if self.entity_rh:
            entities.append(self.entity_rh)

        self.async_on_remove(
            async_track_state_change_event(
                self.hass,
                entities,
                self._handle_update,
            )
        )
        self._handle_update(None)

    def _get_float_state(self, entity_id, default=None):
        if not entity_id: return default
        state = self.hass.states.get(entity_id)
        if state and state.state not in ["unknown", "unavailable"]:
            try:
                return float(state.state)
            except ValueError:
                pass
        return default

    @callback
    def _handle_update(self, event):
        # 1. Check Sun (Must be down for valid reading)
        sun = self.hass.states.get("sun.sun")
        is_daytime = sun and sun.state == "above_horizon"

        # 2. Get Temperatures
        try:
            t_air = self._get_float_state(self.entity_air)
            t_wall = self._get_float_state(self.entity_wall)

            # Get Outdoor Temp (Prefer raw temp for calibration as wind chill
            # effects are complex, but using T_out allows pure U-value estimation)
            w_state = self.hass.states.get(self.entity_weather)
            t_out = float(w_state.attributes.get("temperature"))

            if t_air is None or t_wall is None: raise ValueError
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
            "valid_conditions": False,
        }

        # --- NEW: RH Validation Logic ---
        rh_air = self._get_float_state(self.entity_rh)
        rh_wall = self._get_float_state(self.entity_cal_rh)

        if rh_air is not None and rh_wall is not None:
            # Calculate Absolute Humidity for both
            vp_sat_air = Psychrometrics.calculate_vapor_pressure(t_air)
            vp_actual_air = vp_sat_air * (rh_air / 100.0)

            vp_sat_wall = Psychrometrics.calculate_vapor_pressure(t_wall)
            vp_actual_wall = vp_sat_wall * (rh_wall / 100.0)

            # Volumetric Abs Humidity (g/m3) approx
            abs_hum_air = (1000.0 * vp_actual_air * 100.0) / (461.5 * (t_air + 273.15))
            abs_hum_wall = (1000.0 * vp_actual_wall * 100.0) / (461.5 * (t_wall + 273.15))

            # Theoretical Wall RH (if trapped air was perfect)
            # VP_actual should be constant (vp_actual_air), but VP_sat drops
            if vp_sat_wall > 0:
                predicted_wall_rh = min(100.0, (vp_actual_air / vp_sat_wall) * 100.0)
            else:
                predicted_wall_rh = 100.0

            abs_diff = abs_hum_wall - abs_hum_air

            self._attributes["measured_surface_rh"] = rh_wall
            self._attributes["predicted_surface_rh"] = round(predicted_wall_rh, 1)
            self._attributes["abs_humidity_room"] = round(abs_hum_air, 2)
            self._attributes["abs_humidity_surface"] = round(abs_hum_wall, 2)
            self._attributes["abs_humidity_bias"] = round(abs_diff, 2)

            if abs(abs_diff) < 0.5:
                self._attributes["seal_quality"] = "Excellent (Airtight)"
            elif abs(abs_diff) < 1.0:
                self._attributes["seal_quality"] = "Good (Minor Leakage)"
            else:
                self._attributes["seal_quality"] = "Poor (Leaky Seal or Ingress)"

        # 4. Validity Checks
        if is_daytime:
            self._attributes["status"] = "Invalid: Sun is up"
            self._attr_native_value = None  # Or keep last known
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
    _attr_device_class = SensorDeviceClass.IRRADIANCE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1
    translation_key = "heat_flux"
    _attr_unique_id_suffix = "heat_flux"
    _attr_icon = "mdi:transfer-down"

    def __init__(self, hass, entry, device_info, mrt_sensor):
        super().__init__(hass, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_{self._attr_unique_id_suffix}"
        self.mrt_sensor = mrt_sensor

        # Lookups for required inputs
        self.id_k_loss = None
        self.entity_wall_sensor = entry.data.get(CONF_WALL_SURFACE_SENSOR)
        self.entity_outdoor_temp = entry.data.get(CONF_OUTDOOR_TEMP_SENSOR)
        self.wall_area_gross = entry.data.get(CONF_EXTERIOR_WALL_AREA)
        self.window_area = entry.data.get(CONF_WINDOW_AREA, 0.0)
        self.window_u = entry.data.get(CONF_WINDOW_U_VALUE, DEFAULT_WINDOW_U_VALUE)
        self.floor_area = entry.data.get(CONF_ROOM_AREA, DEFAULT_ROOM_AREA)

    async def async_added_to_hass(self):
        """Register listeners."""
        await super().async_added_to_hass()
        registry = er.async_get(self.hass)
        self.id_k_loss = registry.async_get_entity_id(
            "number", DOMAIN, f"{self._entry.entry_id}_k_loss"
        )

        entities = [self.entity_weather, self.mrt_sensor.entity_id]
        if self.id_k_loss:
            entities.append(self.id_k_loss)
        if self.entity_wall_sensor:
            entities.append(self.entity_wall_sensor)
        if self.entity_outdoor_temp:
            entities.append(self.entity_outdoor_temp)

        self.async_on_remove(
            async_track_state_change_event(self.hass, entities, self._handle_update)
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

    def _calculate_dynamic_film_coefficient(self):
        """
        Calculate h_film = h_radiative + h_convective
        Standard ASHRAE 55 / ISO 7730 models.
        Returns: (h_value, reason_string)
        """
        # 1. Get Air Speed from MRT Sensor (Central Source of Truth)
        v_air = 0.1  # Default Still Air
        if self.mrt_sensor.extra_state_attributes:
            v_air = self.mrt_sensor.extra_state_attributes.get(
                "air_speed_ms_convective", 0.1
            )

        # 2. Radiative Coefficient (h_r)
        # Linearized estimate for typical room temps (20C) and emissivity (0.9)
        h_r = 4.7

        # 3. Convective Coefficient (h_c)
        # ASHRAE Formula: h_c = 3.1 + 5.6 * v_air^0.6
        if v_air <= 0.1:
            h_c = 3.1  # Baseline for natural convection
            reason = "Natural Convection (Still Air)"
        else:
            h_c = 3.1 + 5.6 * pow(v_air, 0.6)
            reason = f"Forced Convection (Air Speed: {v_air:.2f} m/s)"

        return (h_r + h_c), reason

    def _update_value(
        self, t_air, rh, pressure=None
    ):  # pressure unused here but keeps signature
        # 1. Get Outdoor Temp
        t_out = None
        if self.entity_outdoor_temp:
            t_out = self._get_float_state(self.entity_outdoor_temp, None)
        if t_out is None:
            w_state = self.hass.states.get(self.entity_weather)
            if w_state:
                t_out = w_state.attributes.get("temperature")
        if t_out is None:
            t_out = t_air - 10

        # 2. Determine Wall Surface Temp (for Opaque Wall)
        t_surface = None
        if self.entity_wall_sensor:
            val = self._get_float_state(self.entity_wall_sensor, None)
            if val is not None:
                t_surface = val

        if t_surface is None:
            k_loss = self._get_float_state(self.id_k_loss, 0.14)
            t_surface = t_air - ((t_air - t_out) * k_loss)

        # 3. Calculate Opaque Wall Flux
        h_film, h_reason = self._calculate_dynamic_film_coefficient()
        delta_t_surface = t_air - t_surface
        heat_flux_wall = max(0.0, h_film * delta_t_surface)

        self._attr_native_value = round(heat_flux_wall, 1)

        # --- 4. NEW: Calculate Total Watts (Split Method) ---

        # Determine Areas
        if self.wall_area_gross is not None:
            # User provided specific geometry
            area_gross = float(self.wall_area_gross)
            area_win = float(self.window_area)
            area_opaque = max(0.0, area_gross - area_win)
            calc_mode = "geometry_inputs"
        else:
            # Fallback: Assume Wall Area = Floor Area, No Windows
            area_opaque = float(self.floor_area)
            area_win = 0.0
            calc_mode = "fallback_to_floor_area"

        # A. Opaque Wall Loss (Watts) = Flux * Area
        loss_opaque = heat_flux_wall * area_opaque

        # B. Window Loss (Watts) = U * Area * DeltaT
        # Note: We use simple U-value physics here: Q = U * A * (T_in - T_out)
        delta_t_air_out = max(0.0, t_air - t_out)
        loss_window = self.window_u * area_win * delta_t_air_out

        total_watts = loss_opaque + loss_window

        # Attributes
        self._attributes["wall_surface_temp"] = round(t_surface, 1)
        self._attributes["outdoor_temp"] = t_out
        self._attributes["film_coefficient_h"] = round(h_film, 2)
        self._attributes["film_coefficient_type"] = h_reason

        # New Power Attributes
        self._attributes["total_heat_loss_watts"] = round(total_watts, 1)
        self._attributes["loss_opaque_watts"] = round(loss_opaque, 1)
        self._attributes["loss_window_watts"] = round(loss_window, 1)
        self._attributes["calculation_mode"] = calc_mode
        self._attributes["area_opaque_m2"] = round(area_opaque, 2)
        self._attributes["area_window_m2"] = round(area_win, 2)

        # R-Value Estimation (Keep existing logic, applies to opaque wall)
        if delta_t_air_out > 5.0 and heat_flux_wall > 0.5:
            r_si = delta_t_air_out / heat_flux_wall
            r_imperial = r_si * 5.678
            u_val = 1.0 / r_si
            self._attributes["estimated_r_value_imperial"] = round(r_imperial, 1)
            self._attributes["estimated_rsi"] = round(r_si, 2)
            self._attributes["estimated_u_value"] = round(u_val, 3)
        else:
            self._attributes["estimated_r_value_imperial"] = "N/A (Delta T too low)"


class VirtualPMVSensor(SensorEntity):
    """
    Calculates Predicted Mean Vote (PMV) for thermal comfort.
    Inputs: Air Temp, MRT, Humidity, Air Speed, Clothing, Metabolism.
    """

    _attr_has_entity_name = True
    _attr_name = "Thermal Comfort (PMV)"
    _attr_native_unit_of_measurement = "PMV"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    translation_key = "pmv"
    _attr_unique_id_suffix = "pmv"
    _attr_icon = "mdi:human-handsup"

    def __init__(self, hass, entry, device_info, mrt_sensor):
        self.hass = hass
        self._entry = entry
        self._attr_device_info = device_info
        self._attr_unique_id = f"{entry.entry_id}_{self._attr_unique_id_suffix}"

        self.mrt_sensor = mrt_sensor  # Reference to the main MRT object

        # Lookups
        self.id_clo = None
        self.id_met = None
        self._attributes = {}

    async def async_added_to_hass(self):
        """Register listeners."""
        registry = er.async_get(self.hass)
        self.id_clo = registry.async_get_entity_id(
            "number", DOMAIN, f"{self._entry.entry_id}_clothing"
        )
        self.id_met = registry.async_get_entity_id(
            "number", DOMAIN, f"{self._entry.entry_id}_metabolism"
        )

        # Listen to the MRT sensor (which updates when T_air, V_air, etc change)
        # We piggyback on MRT updates to trigger PMV updates
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, [self.mrt_sensor.entity_id], self._handle_update
            )
        )
        # Also listen to Clo/Met changes
        entities = []
        if self.id_clo:
            entities.append(self.id_clo)
        if self.id_met:
            entities.append(self.id_met)

        if entities:
            self.async_on_remove(
                async_track_state_change_event(self.hass, entities, self._handle_update)
            )

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

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

    @callback
    def _handle_update(self, event):
        # 1. Gather all 6 Variables
        # We can pull T_air, V_air, MRT directly from the MRT sensor's attributes
        # to ensure we are using the exact same synchronized physics snapshot.

        mrt_state = self.hass.states.get(self.mrt_sensor.entity_id)
        if not mrt_state or mrt_state.state in ["unknown", "unavailable"]:
            self._attr_native_value = None
            return

        try:
            t_mrt = float(mrt_state.state)
            attrs = mrt_state.attributes

            t_air = attrs.get("t_air")
            v_air = attrs.get("air_speed_ms_convective", 0.1)

            # Humidity (We need to find the RH sensor again or pass it)
            # For simplicity, we can look up the RH sensor from config
            rh_entity = self._entry.data.get(CONF_RH_SENSOR)
            rh = 50.0  # Default
            if rh_entity:
                rh = self._get_float_state(rh_entity, 50.0)

            # Personal Factors
            clo = self._get_float_state(self.id_clo, 0.6)  # Default 0.6 (light sweater)
            met = self._get_float_state(self.id_met, 1.1)  # Default 1.1 (typing)

            if t_air is None:
                return

            # 2. Calculate PMV
            pmv = Psychrometrics.calculate_pmv(t_air, t_mrt, v_air, rh, met, clo)

            # 3. Calculate PPD (% Dissatisfied)
            # PPD = 100 - 95 * exp(-0.03353*PMV^4 - 0.2179*PMV^2)
            ppd = 100.0 - 95.0 * math.exp(-0.03353 * pow(pmv, 4) - 0.2179 * pow(pmv, 2))

            self._attr_native_value = round(pmv, 2)
            self._attributes["ppd_percent"] = round(ppd, 1)
            self._attributes["clothing_clo"] = clo
            self._attributes["metabolic_met"] = met

            # Interpreted State (Text)
            if abs(pmv) < 0.5:
                self._attributes["comfort_category"] = "Neutral (Comfortable)"
            elif 0.5 <= pmv < 1.5:
                self._attributes["comfort_category"] = "Slightly Warm"
            elif pmv >= 1.5:
                self._attributes["comfort_category"] = "Hot"
            elif -1.5 < pmv <= -0.5:
                self._attributes["comfort_category"] = "Slightly Cool"
            elif pmv <= -1.5:
                self._attributes["comfort_category"] = "Cold"

            self.async_write_ha_state()

        except ValueError:
            self._attr_native_value = None


class VirtualMoistureExcessSensor(VirtualPsychroBase):
    """
    Calculates Moisture Excess (Indoor Mixing Ratio - Outdoor Mixing Ratio).
    Positive values indicate internal moisture generation (cooking, showers, breathing).
    Used to control HRV Boost independently of Temperature.
    """

    _attr_name = "Moisture Excess"
    _attr_native_unit_of_measurement = "g/kg"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    translation_key = "moisture_excess"
    _attr_unique_id_suffix = "moisture_excess"
    _attr_icon = "mdi:water-plus"

    def __init__(self, hass, entry, device_info):
        super().__init__(hass, entry, device_info)
        self._attr_unique_id = f"{entry.entry_id}_{self._attr_unique_id_suffix}"

        # Lookups for Outdoor data
        self.entity_outdoor_temp = entry.data.get(CONF_OUTDOOR_TEMP_SENSOR)
        self.entity_outdoor_hum = entry.data.get(CONF_OUTDOOR_HUMIDITY_SENSOR)

    async def async_added_to_hass(self):
        """Register listeners (extending base)."""
        # Base tracks Indoor T, Indoor RH, Pressure, Weather
        await super().async_added_to_hass()

        # We also need to track dedicated outdoor sensors if they exist
        entities = []
        if self.entity_outdoor_temp:
            entities.append(self.entity_outdoor_temp)
        if self.entity_outdoor_hum:
            entities.append(self.entity_outdoor_hum)

        if entities:
            self.async_on_remove(
                async_track_state_change_event(self.hass, entities, self._handle_update)
            )

    def _get_float_state(self, entity_id, default=None):
        if not entity_id:
            return default
        state = self.hass.states.get(entity_id)
        if state and state.state not in ["unknown", "unavailable"]:
            try:
                return float(state.state)
            except ValueError:
                pass
        return default

    def _update_value(self, t_in, rh_in, pressure):
        # 1. Calculate Indoor Mixing Ratio (W_in)
        vp_in = Psychrometrics.calculate_vapor_pressure(t_in) * (rh_in / 100.0)
        w_in = Psychrometrics.calculate_humidity_ratio(vp_in, pressure)

        # 2. Get Outdoor Conditions
        t_out = self._get_float_state(self.entity_outdoor_temp)
        rh_out = self._get_float_state(self.entity_outdoor_hum)

        # Fallback to Weather Entity
        if t_out is None or rh_out is None:
            w_state = self.hass.states.get(self.entity_weather)
            if w_state:
                if t_out is None:
                    t_out = w_state.attributes.get("temperature")
                if rh_out is None:
                    rh_out = w_state.attributes.get("humidity")

        # If still missing data, we can't calculate excess
        if t_out is None or rh_out is None:
            self._attr_native_value = None
            return

        # 3. Calculate Outdoor Mixing Ratio (W_out)
        vp_sat_out = Psychrometrics.calculate_vapor_pressure(t_out)
        vp_out = vp_sat_out * (rh_out / 100.0)
        w_out = Psychrometrics.calculate_humidity_ratio(vp_out, pressure)

        # 4. Calculate Excess
        excess = w_in - w_out

        self._attr_native_value = round(excess, 2)

        # Attributes for debugging
        self._attributes["indoor_mixing_ratio"] = round(w_in, 2)
        self._attributes["outdoor_mixing_ratio"] = round(w_out, 2)

        # Classification
        if excess < 0.5:
            self._attributes["status"] = "Neutral (Balanced)"
        elif excess < 1.5:
            self._attributes["status"] = "Moderate Load (Occupied)"
        else:
            self._attributes["status"] = "High Load (Cooking/Shower/Humidifier)"


class VirtualZoneAggregator(SensorEntity):
    """
    Aggregates multiple Virtual MRT devices (Rooms OR other Zones).
    Calculates: Area-Weighted Avg T_op, and Total Zone Heat Loss (Watts).
    """
    _attr_has_entity_name = True
    _attr_name = "Zone Weighted Temperature"
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:home-group"

    translation_key = "zone_temperature"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_info):
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_aggregator"
        device_info["model"] = "Virtual Room Aggregator"
        self._attr_device_info = device_info

        # We store Device IDs, but we need to resolve them to Entity IDs at runtime
        self.source_device_ids = entry.data.get("source_devices", [])
        self.monitored_entities = set()
        self._ceiling_height = entry.data.get(CONF_CEILING_HEIGHT, DEFAULT_CEILING_HEIGHT)
        self._is_hvac_zone = entry.data.get(CONF_IS_HVAC_ZONE, False)
        self._attributes = {}

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return self._attributes

    async def async_added_to_hass(self):
        """Resolve devices to entities and start listening."""
        registry = er.async_get(self.hass)

        for device_id in self.source_device_ids:
            entries = registry.entities.get_entries_for_device_id(device_id)
            for entry in entries:
                # 1. Look for Standard Rooms (Operative Temp)
                if entry.domain == "sensor" and entry.translation_key == "operative_temperature":
                    self.monitored_entities.add(entry.entity_id)

                # 2. Look for Standard Rooms (Heat Flux)
                if entry.domain == "sensor" and entry.translation_key == "heat_flux":
                    self.monitored_entities.add(entry.entity_id)

                # 3. Look for Child Aggregators (Nested Zones)
                if entry.domain == "sensor" and entry.translation_key == "zone_temperature":
                    self.monitored_entities.add(entry.entity_id)

        # Listen to these discovered entities
        if self.monitored_entities:
            self.async_on_remove(
                async_track_state_change_event(
                    self.hass, list(self.monitored_entities), self._handle_update
                )
            )
            self._handle_update(None)

    def _get_float(self, state):
        try:
            return float(state)
        except (ValueError, TypeError):
            return None

    @callback
    def _handle_update(self, event):
        """Calculate Area-Weighted Averages."""
        # Data structure: {device_id: {'temp': X, 'area': Y, 'flux': Z, 'watts': W}}
        device_data = {}
        registry = er.async_get(self.hass)

        t_out = None
        t_eff = None

        for entity_id in self.monitored_entities:
            state_obj = self.hass.states.get(entity_id)
            if not state_obj or state_obj.state in ["unknown", "unavailable"]:
                continue

            entry = registry.async_get(entity_id)
            if not entry: continue
            dev_id = entry.device_id

            # Initialize entry if new (use current entity name as placeholder)
            if dev_id not in device_data:
                name = state_obj.name or entry.original_name or entity_id
                device_data[dev_id] = {'area': DEFAULT_ROOM_AREA, 'floor': DEFAULT_ROOM_FLOOR, 'name': name}

            val = self._get_float(state_obj.state)

            # --- Capture Outdoor Temp (for Stack Effect) ---
            if t_out is None:
                if "t_out_eff" in state_obj.attributes:
                    t_eff = state_obj.attributes["t_out_eff"]
                if "outdoor_temp" in state_obj.attributes:
                    t_out = state_obj.attributes["outdoor_temp"]

            # --- CASE A: Standard Room (Operative Temp) ---
            if entry.translation_key == "operative_temperature":
                device_data[dev_id]['temp'] = val
                device_data[dev_id]['area'] = float(state_obj.attributes.get("room_area_m2", DEFAULT_ROOM_AREA))
                device_data[dev_id]['floor'] = int(state_obj.attributes.get("floor_level", DEFAULT_ROOM_FLOOR))
                # FIX: Force name to be the Temperature Sensor name (so it doesn't say "Heat Flux")
                device_data[dev_id]['name'] = state_obj.name

                # Capture Air Temp for Aggregation
                t_air = self._get_float(state_obj.attributes.get("t_air"))
                if t_air is not None:
                    device_data[dev_id]['air_temp'] = t_air

            # --- CASE B: Standard Room (Heat Flux) ---
            elif entry.translation_key == "heat_flux":
                device_data[dev_id]['flux'] = val
                # NEW: Try to get pre-calculated Total Watts from the sensor attributes
                precalc_watts = state_obj.attributes.get("total_heat_loss_watts")
                if precalc_watts is not None:
                    device_data[dev_id]['watts'] = float(precalc_watts)

            # --- CASE C: Nested Aggregator (Zone Temp) ---
            elif entry.translation_key == "zone_temperature":
                device_data[dev_id]['temp'] = val
                # Map "Total Zone Area" -> "Area" for weighting
                device_data[dev_id]['area'] = float(state_obj.attributes.get("total_zone_area_m2", DEFAULT_ZONE_AREA))
                # FIX: Force name to be the Zone Sensor name
                device_data[dev_id]['name'] = state_obj.name

                # Map "Total Heat Loss" -> Direct Watts (Pre-calculated by child)
                device_data[dev_id]['watts'] = float(state_obj.attributes.get("total_heat_loss_watts", 0.0))

                # Capture Air Temp from child aggregator
                t_air = self._get_float(state_obj.attributes.get("avg_air_temp"))
                if t_air is not None:
                    device_data[dev_id]['air_temp'] = t_air

                # Floor Level?
                if "floor_level" in state_obj.attributes:
                    device_data[dev_id]['floor'] = int(state_obj.attributes["floor_level"])

        # --- Aggregation Logic ---
        floors = {}
        temps_for_spread = []
        total_area = 0.0
        weighted_temp_sum = 0.0
        weighted_air_sum = 0.0
        total_air_area = 0.0
        total_watts_loss = 0.0
        valid_temp_count = 0

        for dev_id, data in device_data.items():
            area = data.get('area', DEFAULT_ROOM_AREA)

            # 1. Weighted Temp (Operative)
            if 'temp' in data:
                val = data['temp']
                weighted_temp_sum += (val * area)
                total_area += area
                valid_temp_count += 1

                # Store for HVAC Spread Calc
                temps_for_spread.append((val, data.get('name', 'Unknown')))

                # Store for Stack Effect
                if 'floor' in data:
                    f_lvl = data['floor']
                    if f_lvl not in floors: floors[f_lvl] = []
                    floors[f_lvl].append(val)

            # 2. Weighted Air Temp
            if 'air_temp' in data:
                weighted_air_sum += (data['air_temp'] * area)
                total_air_area += area

            # 3. Watts
            if 'watts' in data:
                total_watts_loss += data['watts']
            elif 'flux' in data:
                total_watts_loss += (data['flux'] * area)

        # --- Output Core Stats ---
        if total_area > 0 and valid_temp_count > 0:
            avg_temp = weighted_temp_sum / total_area
            self._attr_native_value = round(avg_temp, 2)
            self._attributes["avg_operative_temp"] = round(avg_temp, 2)
            self._attributes["total_zone_area_m2"] = round(total_area, 1)
            self._attributes["total_heat_loss_watts"] = round(total_watts_loss, 0)
            self._attributes["active_sources"] = valid_temp_count
        else:
            self._attr_native_value = None

        if total_air_area > 0:
            self._attributes["avg_air_temp"] = round(weighted_air_sum / total_air_area, 2)

        if t_eff is not None:
            self._attributes["outdoor_temp"] = t_eff
            self._attributes["outdoor_temp_source"] = "Effective Outdoor Temp"
        elif t_out is not None:
            self._attributes["outdoor_temp"] = t_out
            self._attributes["outdoor_temp_source"] = "Standard Outdoor Temp"
        t_out_candidate = t_eff or t_out

        def calculate_spread(temp_list):
            if not temp_list: return
            min_t = min(temp_list, key=lambda x: x[0])
            max_t = max(temp_list, key=lambda x: x[0])
            spread = max_t[0] - min_t[0]

            self._attributes["zone_temp_spread"] = round(spread, 2)
            self._attributes["coldest_room"] = min_t[1]
            self._attributes["hottest_room"] = max_t[1]

            if spread > 2.0:
                self._attributes["balance_status"] = "Unbalanced (>2°C Spread)"
            else:
                self._attributes["balance_status"] = "Balanced"

        # --- MODE A: HVAC ZONE (Balancing Stats) ---
        if self._is_hvac_zone:
            self._attributes["aggregator_mode"] = "HVAC Zone"
            self._attributes.pop("stack_effect_pressure_pa", None)
            self._attributes.pop("stratification_delta", None)

            calculate_spread(temps_for_spread)

        # --- MODE B: VERTICAL STACK (Physics Stats) ---
        else:
            self._attributes["aggregator_mode"] = "Vertical Stack / Floor"

            unique_floors = sorted(list(floors.keys()))
            self._attributes["floors_included"] = unique_floors

            # Case 1: Single Floor Aggregator (Treat like a Zone for Spread)
            if len(unique_floors) == 1:
                self._attributes["floor_level"] = unique_floors[0]
                # We clear stack stats but ADD spread stats
                self._attributes.pop("stratification_delta", None)
                self._attributes.pop("stack_effect_pressure_pa", None)
                calculate_spread(temps_for_spread)

            # Case 2: Multi-Floor Aggregator (Treat like a Stack)
            elif len(unique_floors) >= 2:
                # We clear spread stats (less relevant across floors) but ADD stack stats
                self._attributes.pop("zone_temp_spread", None)
                self._attributes.pop("balance_status", None)

                min_floor = unique_floors[0]
                max_floor = unique_floors[-1]
                t_bottom = sum(floors[min_floor]) / len(floors[min_floor])
                t_top = sum(floors[max_floor]) / len(floors[max_floor])

                stratification = t_top - t_bottom
                height_diff = (max_floor - min_floor + 1) * self._ceiling_height

                stack_pressure = 0.0
                if t_out_candidate is not None:
                    term_out = 1.0 / (t_out_candidate + 273.15)
                    term_in = 1.0 / (((t_top + t_bottom) / 2) + 273.15)
                    stack_pressure = 3465 * height_diff * (term_out - term_in)

                self._attributes["stratification_delta"] = round(stratification, 2)
                self._attributes["stack_effect_pressure_pa"] = round(stack_pressure, 1)
                self._attributes["stack_height_m"] = round(height_diff, 1)

                # Imperial Calc
                total_feet = height_diff * 3.28084
                feet_part = int(total_feet)
                inches_part = round((total_feet - feet_part) * 12)
                if inches_part == 12:
                    feet_part += 1
                    inches_part = 0
                self._attributes["stack_height_imperial"] = f"{feet_part}' {inches_part}\""

        # FIX: Use thread-safe update scheduler instead of direct write
        self.schedule_update_ha_state()


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
        self.entity_rain = self._config.get(CONF_PRECIPITATION_SENSOR)
        self.entity_uv = self._config.get(CONF_UV_INDEX_SENSOR)
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

        self._min_update_interval = self._config.get(CONF_MIN_UPDATE_INTERVAL, 30.0)
        self._last_update_time = 0.0
        self._cancel_scheduled_update = None

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

        # Only look for these if radiant heating is enabled
        if self.is_radiant:
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
        if self.entity_rain:
            entities_to_track.append(self.entity_rain)
        if self.entity_uv:
            entities_to_track.append(self.entity_uv)

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
        """Handle entity state changes with Rate Limiting."""
        now = time.time()
        time_since = now - self._last_update_time

        # 1. If interval is 0, update instantly (No throttle)
        if self._min_update_interval <= 0:
            self._perform_update()
            return

        # 2. If enough time has passed, update immediately
        if time_since >= self._min_update_interval:
            self._perform_update()
        else:
            # 3. If too soon, schedule an update for the end of the interval
            # We cancel any existing timer so we don't stack updates
            if self._cancel_scheduled_update:
                self._cancel_scheduled_update()
                self._cancel_scheduled_update = None

            delay = self._min_update_interval - time_since
            self._cancel_scheduled_update = async_call_later(
                self.hass, delay, self._scheduled_update_callback
            )

    @callback
    def _scheduled_update_callback(self, _):
        """Called when the rate-limit timer expires."""
        self._cancel_scheduled_update = None
        self._perform_update()

    def _perform_update(self):
        """Actually run the calc and write state."""
        self._last_update_time = time.time()
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

    def _calculate_local_apparent_temp(
            self, t_out: float, wind_ms: float
    ) -> float | None:
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

    def _update_calc(self):
        """Perform the math and store all intermediate values."""

        # --- 1. ROBUST ENTITY CHECK ---
        # We must verify that ALL required internal entity IDs have been found
        # before we attempt to read their states.

        # Start with common entities
        required_ids = [
            self.id_f_out,
            self.id_f_win,
            self.id_k_loss,
            self.id_k_solar,
            self.id_profile_select,
            self.id_thermal_alpha,
            self.id_manual_speed,
            self.id_hvac_speed,
        ]

        # Conditional Check: Only require Radiant IDs if radiant is enabled
        if self.is_radiant:
            required_ids.append(self.id_radiant_temp)
            required_ids.append(self.id_radiant_type)

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

            # Populate Radiant IDs if needed
            if self.is_radiant:
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
            # We must use 'required_ids' check again with updated values

            # Rebuild check list
            check_list = [
                self.id_f_out,
                self.id_f_win,
                self.id_k_loss,
                self.id_k_solar,
                self.id_profile_select,
                self.id_thermal_alpha,
                self.id_manual_speed,
                self.id_hvac_speed,
            ]
            if self.is_radiant:
                check_list.append(self.id_radiant_temp)
                check_list.append(self.id_radiant_type)

            if not all(check_list):
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
        # --- UV Logic ---
        uv = None
        uv_source = "fallback"

        # 1. Try Dedicated Sensor
        if self.entity_uv:
            uv = self._get_float(self.entity_uv, None)
            if uv is not None:
                uv_source = "sensor"

        # 2. Try Weather Entity
        if uv is None:
            uv = self._get_attr(self.entity_weather, "uv_index", None)
            if uv is not None:
                uv_source = "weather_entity"

        # 3. Fallback
        if uv is None:
            uv = 0.0

        self._attributes["uv_index"] = uv
        self._attributes["uv_source"] = uv_source

        # --- RAIN LOGIC ---
        is_raining = False
        rain_source = "unknown"

        # 1. Try Dedicated Sensor (Rate > 0)
        if self.entity_rain:
            rain_rate = self._get_float(self.entity_rain, None)
            if rain_rate is not None:
                is_raining = rain_rate > 0.0
                rain_source = "sensor"

        # 2. Try Weather Entity State (String match)
        if rain_source == "unknown":
            weather_state_obj = self.hass.states.get(self.entity_weather)
            cond = weather_state_obj.state.lower() if weather_state_obj else ""
            is_raining = any(x in cond for x in ["rain", "pour", "snow", "hail"])
            rain_source = "weather_entity_condition_string" if weather_state_obj else "fallback"

        rain_mul = 0.4 if is_raining else 1.0
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
        new_boost = 0.0
        if self.is_radiant:
            surface_setpoint = self._get_float(self.id_radiant_temp, 24.0)

            # Get type safely
            type_key = "high_mass"
            if self.id_radiant_type:
                type_state = self.hass.states.get(self.id_radiant_type)
                if type_state:
                    type_key = type_state.state

            system_props = RADIANT_TYPES.get(type_key, RADIANT_TYPES["high_mass"])
            boost_alpha = system_props["alpha"]
            view_factor = system_props["view_factor"]

            climate_state = (
                self.hass.states.get(self.entity_climate) if self.entity_climate else None
            )
            target_boost = 0.0
            if (
                    climate_state
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

        # --- Estimated Wall Surface Temp ---
        # Theoretical inner surface temp of the exterior wall
        # T_surf = T_air - (Delta_T * k_loss)
        # We use t_out_eff to account for wind chill cooling the exterior
        if t_air is not None and t_out_eff is not None:
            t_wall_est = t_air - ((t_air - t_out_eff) * k_loss)
            self._attributes["estimated_wall_surface_temp"] = round(t_wall_est, 1)

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
