"""The Virtual MRT/T_op integration."""

from __future__ import annotations

import logging
import os

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import STORAGE_DIR
from homeassistant.loader import async_get_integration

from .const import DOMAIN, STORAGE_KEY

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
    # This prevents a blocking 'import_module' call in the event loop
    # by pre-loading the 'select' domain (sensor/number are usually loaded)
    for platform_domain in PLATFORMS:
        try:
            # This asynchronously gets the integration (domain) and
            # performs the import in an executor thread.
            await async_get_integration(hass, platform_domain)
        except ImportError:
            _LOGGER.error(
                "Failed to pre-load integration %s, setup cannot continue",
                platform_domain,
            )
            return False
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Add an update listener for the Options Flow
    entry.add_update_listener(async_update_listener)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Remove the update listener when unloading
    entry.remove_update_listener(async_update_listener)
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    # Reload the integration when options are changed
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of a config entry (cleanup logic)."""

    # 1. Get the unique key for the storage file used by this device
    store_key = f"{STORAGE_KEY}_{entry.entry_id}"

    # 2. Get the file path within the .storage directory
    store_path = hass.config.path(STORAGE_DIR, store_key)

    # 3. Use the executor to perform the synchronous file deletion safely
    def delete_store_file():
        """Synchronous file deletion in the executor."""
        if os.path.exists(store_path):
            _LOGGER.debug("Deleting persistent storage file: %s", store_path)
            try:
                os.remove(store_path)
                return True
            except OSError as err:
                _LOGGER.error("Failed to delete storage file %s: %s", store_path, err)
                return False
        return True  # File doesn't exist, so cleanup is successful

    # 4. Schedule the deletion and wait for it
    success = await hass.async_add_executor_job(delete_store_file)

    if not success:
        _LOGGER.error("Failed to clean up persistent data for %s", entry.entry_id)
        return False

    # 5. Unload all platforms after cleanup is done
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
