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

CONF_THERMAL_ALPHA = "thermal_alpha"

CUSTOM_PROFILE_KEY = "custom"

ORIENTATION_OPTIONS = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]

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

SOUTH_FACTORS = {
    "N": 0.2,
    "NE": 0.4,
    "E": 0.6,
    "SE": 0.8,
    "S": 1.0,
    "SW": 0.8,
    "W": 0.6,
    "NW": 0.4,
}
