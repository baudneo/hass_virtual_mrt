"""Button platform for Virtual MRT."""

from __future__ import annotations

import logging

from homeassistant.components.button import (
    ButtonEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    ROOM_PROFILES,
    CUSTOM_PROFILE_KEY,
    STORAGE_KEY,
    STORAGE_VERSION,
    STORE_KEY_SAVED,
    MAX_SAVED_PROFILES,
)
from .device_info import get_device_info

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up the button entities."""
    config = entry.data
    device_info = await get_device_info({(DOMAIN, entry.entry_id)}, config[CONF_NAME])

    # Each button gets access to the same storage file
    store_key = f"{STORAGE_KEY}_{entry.entry_id}"
    store = Store(hass, STORAGE_VERSION, store_key)

    async_add_entities(
        [
            SaveProfileButton(hass, entry, device_info, store),
            DeleteProfileButton(hass, entry, device_info, store),
        ]
    )


class BaseProfileButton(ButtonEntity):
    """Base class for profile buttons."""

    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        device_info,
        store: Store,
    ):
        self.hass = hass
        self._entry = entry
        self._attr_device_info = device_info
        self._store = store

    @property
    def _entity_registry(self) -> er.EntityRegistry:
        """Helper to get the entity registry."""
        return er.async_get(self.hass)

    def _get_sibling_entity_id(self, platform: str, key: str) -> str | None:
        """Find a sibling entity from the same device."""
        return self._entity_registry.async_get_entity_id(
            platform, DOMAIN, f"{self._entry.entry_id}_{key}"
        )

    async def _get_profile_name(self) -> str:
        """Get the value from the text.profile_name entity, ensuring a string is returned."""
        text_entity_id = self._get_sibling_entity_id("text", "profile_name")

        if not text_entity_id:
            _LOGGER.error("Save/Delete failed: Profile Name Text Entity ID not found.")
            return ""

        state = self.hass.states.get(text_entity_id)

        if state and state.state not in ["unavailable", "unknown", "None", None, ""]:
            return state.state.strip()

        _LOGGER.error(
            "Save/Delete failed: Profile Name Text Entity state is invalid or empty. State read: %s",
            state.state if state else "None",
        )
        return ""

    async def _get_current_number_values(self) -> list[float] | None:
        """Get the current values from the number entities."""
        try:
            values = [
                float(
                    self.hass.states.get(
                        self._get_sibling_entity_id("number", "f_out")
                    ).state
                ),
                float(
                    self.hass.states.get(
                        self._get_sibling_entity_id("number", "f_win")
                    ).state
                ),
                float(
                    self.hass.states.get(
                        self._get_sibling_entity_id("number", "k_loss")
                    ).state
                ),
                float(
                    self.hass.states.get(
                        self._get_sibling_entity_id("number", "k_solar")
                    ).state
                ),
            ]
            return values
        except (AttributeError, ValueError, TypeError):
            _LOGGER.error("Could not read all number entity states")
            return None


class SaveProfileButton(BaseProfileButton):
    """Button to save the current number values as a new profile."""

    _attr_icon = "mdi:content-save"
    translation_key = "save_profile"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, *args):
        super().__init__(*args)
        self._attr_unique_id = f"{self._entry.entry_id}_save_profile"

    async def async_press(self) -> None:
        """Handle the button press."""
        name = await self._get_profile_name()

        # --- Validation 1: Check Name ---
        if not name or name.strip() == "":
            _LOGGER.error("Cannot save profile: name is empty")
            return

        name = name.strip()

        if name.lower() == CUSTOM_PROFILE_KEY or name in ROOM_PROFILES:
            _LOGGER.error("Cannot save profile: '%s' is a reserved name", name)
            return

        # --- Validation 2: Check Values ---
        values = await self._get_current_number_values()
        if not values:
            _LOGGER.error("Could not save profile: number values are invalid")
            return

        # --- Load and Check Limit ---
        data = await self._store.async_load() or {}
        data.setdefault(STORE_KEY_SAVED, {})

        saved_profiles = data.get(STORE_KEY_SAVED, {})

        if name not in saved_profiles and len(saved_profiles) >= MAX_SAVED_PROFILES:
            _LOGGER.error(
                "Cannot save profile '%s': Maximum limit of %s profiles reached.",
                name,
                MAX_SAVED_PROFILES,
            )
            # We can also raise a HomeAssistantError here to show a notification to the user
            raise HomeAssistantError(
                f"Profile limit reached ({MAX_SAVED_PROFILES}). Delete old profiles to save a new one."
            )
            return

        # Sanity check
        if not (0.0 <= values[1] <= 1.0):  # f_win (index 1)
            _LOGGER.warning("Saving profile with unusual f_win: %s", values[1])
        if not (0.0 <= values[2] <= 2.0):  # k_loss (index 2)
            _LOGGER.warning("Saving profile with unusual k_loss: %s", values[2])

        # --- Save to Store ---
        data[STORE_KEY_SAVED][name] = values
        await self._store.async_save(data)

        _LOGGER.info("Saved new profile: '%s'", name)

        # --- Refresh Select Entity ---
        select_entity_id = self._get_sibling_entity_id("select", "profile")
        if select_entity_id:
            select_entity = self.hass.data["select"].get_entity(select_entity_id)
            if select_entity:
                # Refresh options and select the newly saved profile
                await select_entity.async_update_options_and_select(name)


class DeleteProfileButton(BaseProfileButton):
    """Button to delete a saved profile."""

    _attr_icon = "mdi:delete"
    translation_key = "delete_profile"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, *args):
        super().__init__(*args)
        self._attr_unique_id = f"{self._entry.entry_id}_delete_profile"

    async def async_press(self) -> None:
        """Handle the button press."""
        name = await self._get_profile_name()

        # --- Validation ---
        if not name or name.strip() == "":
            _LOGGER.error("Cannot delete profile: name is empty")
            return

        name = name.strip()

        if name.lower() == CUSTOM_PROFILE_KEY or name in ROOM_PROFILES:
            _LOGGER.error(
                "Cannot delete profile: '%s' is a default/reserved profile", name
            )
            return

        # --- Delete from Store ---
        data = await self._store.async_load() or {}
        if name not in data.get(STORE_KEY_SAVED, {}):
            _LOGGER.error(
                "Cannot delete profile: '%s' not found in saved profiles", name
            )
            return

        del data[STORE_KEY_SAVED][name]
        await self._store.async_save(data)

        _LOGGER.info("Deleted profile: '%s'", name)
        # clear the profile name textbox, after successful deletion
        text_entity_id = self._get_sibling_entity_id("text", "profile_name")
        if text_entity_id:
            await self.hass.services.async_call(
                "text",
                "set_value",
                {"entity_id": text_entity_id, "value": ""},
                blocking=True,
            )

        # --- Refresh Select Entity ---
        select_entity_id = self._get_sibling_entity_id("select", "profile")
        if select_entity_id:
            select_entity = self.hass.data["select"].get_entity(select_entity_id)
            if select_entity:
                await select_entity.async_update_options_and_select(CUSTOM_PROFILE_KEY)
