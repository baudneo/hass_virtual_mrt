"""Constants for the Virtual MRT integration."""

DOMAIN = "virtual_mrt_top"

STORAGE_KEY = f"{DOMAIN}_profiles"
STORAGE_VERSION = 1
STORE_KEY_CUSTOM = "custom"
STORE_KEY_SAVED = "saved_profiles"

MAX_SAVED_PROFILES = 100

CONF_ROOM_PROFILE = "room_profile"
CONF_ORIENTATION = "orientation"
CONF_AIR_TEMP_SOURCE = "air_temp_source"
CONF_WEATHER_ENTITY = "weather_entity"
CONF_SOLAR_SENSOR = "solar_sensor"
CONF_SHADING_ENTITY = "shading_entity"

CONF_THERMAL_ALPHA = "thermal_alpha"
CONF_IS_RADIANT = "is_radiant_heating"
CONF_CLIMATE_ENTITY = "climate_entity"
CONF_WINDOW_STATE_SENSOR = "window_state_sensor"
CONF_DOOR_STATE_SENSOR = "door_state_sensor"
CONF_FAN_ENTITY = "fan_entity"
CONF_MANUAL_AIR_SPEED = "manual_air_speed"
CONF_HVAC_AIR_SPEED = "hvac_air_speed"
CONF_RADIANT_SURFACE_TEMP = "radiant_surface_temp"
CONF_RADIANT_TYPE = "radiant_type"
CUSTOM_PROFILE_KEY = "custom"

ORIENTATION_OPTIONS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

# RADIANT_TYPES now defines Speed (alpha) AND Geometry (view_factor)
RADIANT_TYPES = {
    # High Mass (Slow): Floor is huge (40% influence), but slow to change.
    "high_mass": {
        "label": "Concrete Slab / In-Floor (Slow)",
        "alpha": 0.05,
        "view_factor": 0.4,
    },
    # Medium Mass: Staple-up floor or large panel radiators.
    "medium_mass": {
        "label": "Joist / Staple-Up (Medium)",
        "alpha": 0.15,
        "view_factor": 0.3,
    },
    # Low Mass (Fast): Baseboards/Radiators are small (10% influence), but hot and fast.
    "low_mass": {
        "label": "Radiator / Baseboard (Fast)",
        "alpha": 0.40,
        "view_factor": 0.1,
    },
}

# --- DEFAULT AIR SPEED MODELING (m/s) ---
DEFAULT_AIR_SPEED_STILL = 0.1
DEFAULT_AIR_SPEED_HVAC = 0.4
DEFAULT_AIR_SPEED_WINDOW = 0.5
DEFAULT_AIR_SPEED_DOOR = 0.8

DEFAULT_ORIENTATION = "S"
ORIENTATION_DEGREES = {
    "N": 0,
    "NE": 45,
    "E": 90,
    "SE": 135,
    "S": 180,
    "SW": 225,
    "W": 270,
    "NW": 315,
}

# Mapping common fan states (must be lowercase) to air velocity (m/s)
FAN_SPEED_MAP = {
    "low": 0.3,
    "medium": 0.5,
    "high": 0.8,
    "on": 0.4,  # Generic on state
    "1": 0.3,  # Numerical low
    "2": 0.5,
    "3": 0.8,
    "auto": 0.4,  # For fans with auto mode
}

# Profile Data: [f_out, f_win, k_loss, k_solar]
ROOM_PROFILES = {
    "one_wall_large_window": {
        "label": "1 ext wall, large window",
        "data": [0.5, 0.40, 0.14, 1.20],
    },
    "two_wall_large_window": {
        "label": "2 ext walls, large window",
        "data": [0.8, 0.50, 0.16, 1.40],
    },
    "attic": {"label": "Top floor (tilted/high gain)", "data": [0.9, 0.40, 0.20, 1.50]},
    "topfloor_vert_small_window": {
        "label": "Top floor (vert/small win)",
        "data": [0.9, 0.15, 0.23, 0.75],
    },
    "topfloor_vert_medium_window": {
        "label": "Top floor (vert/med win)",
        "data": [0.9, 0.30, 0.22, 1.00],
    },
    "topfloor_two_walls_cavity": {
        "label": "Top floor (2 walls/cavity)",
        "data": [0.95, 0.25, 0.24, 0.95],
    },
    "topfloor_cold_adjacent": {
        "label": "Top floor (cold adjacent)",
        "data": [0.95, 0.35, 0.23, 1.15],
    },
    "two_wall_small_window": {
        "label": "2 ext walls, small window",
        "data": [0.7, 0.30, 0.16, 1.00],
    },
    "one_wall_small_window": {
        "label": "1 ext wall, small window",
        "data": [0.5, 0.20, 0.12, 0.80],
    },
    "basement": {"label": "Basement / semi-basement", "data": [0.4, 0.20, 0.10, 0.60]},
    "one_wall_cold_adjacent": {
        "label": "1 ext wall, cold adjacent",
        "data": [0.6, 0.30, 0.18, 0.80],
    },
    "corner_cold_adjacent": {
        "label": "Corner room, cold adjacent",
        "data": [0.8, 0.40, 0.20, 1.00],
    },
    "interior": {"label": "Interior room", "data": [0.0, 0.00, 0.08, 0.40]},
    "interior_cold_adjacent": {
        "label": "Interior, cold adjacent",
        "data": [0.3, 0.00, 0.12, 0.40],
    },
}
