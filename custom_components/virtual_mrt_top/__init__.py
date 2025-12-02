"""The Virtual MRT/T_op integration."""

from __future__ import annotations

import logging
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR
from homeassistant.loader import async_get_integration

from .const import (
    DOMAIN,
    STORAGE_KEY,
    DEFAULT_AIR_SPEED_STILL,
    CONF_HVAC_AIR_SPEED,
    CONF_DOOR_STATE_SENSOR,
    CONF_WINDOW_STATE_SENSOR,
    CONF_FAN_ENTITY,
    CONF_CLIMATE_ENTITY,
    CONF_MANUAL_AIR_SPEED,
    DEFAULT_AIR_SPEED_HVAC,
    CONF_SHADING_ENTITY,
    CONF_RADIANT_SURFACE_TEMP,
    CONF_RADIANT_TYPE,
    CONF_IS_RADIANT,
)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.TEXT,
    Platform.BUTTON,
]

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Virtual MRT from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Ensure all component domains are loaded before setting up platforms
    for platform_domain in PLATFORMS:
        try:
            await async_get_integration(hass, platform_domain)
        except ImportError:
            _LOGGER.error(
                "Failed to pre-load integration %s, setup cannot continue",
                platform_domain,
            )
            return False

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # --- CHANGED: Register update listener with async_on_unload ---
    # entry.add_update_listener returns a callable that removes the listener.
    # entry.async_on_unload registers that callable to run when the entry unloads.
    entry.async_on_unload(entry.add_update_listener(async_update_listener))
    # -------------------------------------------------------------

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # --- CHANGED: Removed invalid 'remove_update_listener' call ---
    # The listener is now automatically removed by async_on_unload above.

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old entry to a new format version."""
    _LOGGER.info("Migrating Virtual MRT entry from version %s", entry.version)

    if entry.version == 1:
        new_data = entry.data.copy()
        new_data[CONF_CLIMATE_ENTITY] = None
        new_data[CONF_FAN_ENTITY] = None
        new_data[CONF_WINDOW_STATE_SENSOR] = None
        new_data[CONF_DOOR_STATE_SENSOR] = None
        new_data[CONF_SHADING_ENTITY] = None
        new_data[CONF_HVAC_AIR_SPEED] = DEFAULT_AIR_SPEED_HVAC
        new_data[CONF_MANUAL_AIR_SPEED] = DEFAULT_AIR_SPEED_STILL
        new_data[CONF_RADIANT_TYPE] = "low_mass"
        new_data[CONF_RADIANT_SURFACE_TEMP] = None

        # We don't return True yet; we let it fall through to V3 migration logic if needed
        entry.version = 2

    # Handle V2 -> V3 (Adding Radiant Boolean)
    if entry.version == 2:
        # Ensure we work with the data (either from V1 migration or existing V2)
        new_data = entry.data.copy() if "new_data" not in locals() else new_data

        new_data[CONF_IS_RADIANT] = False  # Default to Forced Air

        hass.config_entries.async_update_entry(entry, data=new_data, version=3)
        _LOGGER.info("Migration to version 3 successful for entry %s", entry.entry_id)
        return True

    return True


async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of a config entry (cleanup logic)."""
    store_key = f"{STORAGE_KEY}_{entry.entry_id}"
    store_path = hass.config.path(STORAGE_DIR, store_key)

    def delete_store_file():
        if os.path.exists(store_path):
            try:
                os.remove(store_path)
                return True
            except OSError as err:
                _LOGGER.error("Failed to delete storage file %s: %s", store_path, err)
                return False
        return True

    success = await hass.async_add_executor_job(delete_store_file)

    if not success:
        _LOGGER.error("Failed to clean up persistent data for %s", entry.entry_id)
        return False

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
