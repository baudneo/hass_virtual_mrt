"""Select platform for Virtual MRT."""

from __future__ import annotations
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.components.number.const import SERVICE_SET_VALUE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store
from homeassistant.helpers.entity import EntityCategory

from .const import (
    DOMAIN,
    ROOM_PROFILES,
    CUSTOM_PROFILE_KEY,
    CONF_ROOM_PROFILE,
    STORAGE_KEY,
    STORAGE_VERSION,
    STORE_KEY_CUSTOM,
    STORE_KEY_SAVED,
    CONF_CLIMATE_ENTITY,
    CONF_WINDOW_STATE_SENSOR,
    CONF_DOOR_STATE_SENSOR,
    CONF_FAN_ENTITY,
    CONF_MANUAL_AIR_SPEED,
    CONF_RADIANT_TYPE,
    RADIANT_TYPES,
)
from .device_info import get_device_info


_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up the select entity."""
    config = entry.data
    device_info = await get_device_info({(DOMAIN, entry.entry_id)}, config[CONF_NAME])
    store_key = f"{STORAGE_KEY}_{entry.entry_id}"
    store = Store(hass, STORAGE_VERSION, store_key)

    async_add_entities(
        [
            VirtualProfileSelect(hass, entry, device_info, store),
            VirtualRadiantTypeSelect(hass, entry, device_info),
        ]
    )


# --- NEW CLASS ADDED: VirtualRadiantTypeSelect ---
class VirtualRadiantTypeSelect(SelectEntity):
    """Select entity for the type of radiant system, determining response time."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:radiator"
    translation_key = "radiant_type"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_info):
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{CONF_RADIANT_TYPE}"
        self._attr_device_info = device_info

        # Options are the keys from the RADIANT_TYPES map
        self._attr_options = list(RADIANT_TYPES.keys())

        # Get initial state from config, defaulting to low_mass (fastest) if not set
        self._attr_current_option = entry.data.get(CONF_RADIANT_TYPE, "low_mass")

    async def async_select_option(self, option: str) -> None:
        """Handle selection and update the configuration entry."""
        if option not in self._attr_options:
            _LOGGER.error("Invalid radiant type selected: %s", option)
            return

        # 1. Update the internal state of the entity
        self._attr_current_option = option
        self.async_write_ha_state()

        # 2. Update the persistent configuration entry data
        new_data = self._entry.data.copy()
        new_data[CONF_RADIANT_TYPE] = option
        self.hass.config_entries.async_update_entry(self._entry, data=new_data)


class VirtualProfileSelect(SelectEntity):
    """Select entity for the room profile."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:form-select"
    translation_key = "profile"

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, device_info, store: Store
    ):
        self.hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_profile"
        self._attr_device_info = device_info

        self._attr_current_option = entry.data[CONF_ROOM_PROFILE]
        self._store = store

        self._attr_options = list(ROOM_PROFILES.keys()) + [CUSTOM_PROFILE_KEY]
        self._saved_profiles: dict[str, list[float]] = {}
        self._custom_profile_data: list[float] | None = None

        # Entity IDs of the number inputs, to be found
        self.id_f_out = None
        self.id_f_win = None
        self.id_k_loss = None
        self.id_k_solar = None

        self.id_climate = None
        self.id_fan = None
        self.id_window = None
        self.id_door = None
        self.id_manual_speed = None

        self._is_updating = False

    async def async_added_to_hass(self):
        """Find number entities and register listeners."""
        await super().async_added_to_hass()

        # Load all data from store and build options
        await self._load_data_and_build_options()

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

        self.id_climate = registry.async_get_entity_id(
            Platform.CLIMATE, DOMAIN, f"{self._entry.entry_id}_{CONF_CLIMATE_ENTITY}"
        )
        self.id_fan = registry.async_get_entity_id(
            Platform.FAN, DOMAIN, f"{self._entry.entry_id}_{CONF_FAN_ENTITY}"
        )
        self.id_window = registry.async_get_entity_id(
            Platform.BINARY_SENSOR,
            DOMAIN,
            f"{self._entry.entry_id}_{CONF_WINDOW_STATE_SENSOR}",
        )
        self.id_door = registry.async_get_entity_id(
            Platform.BINARY_SENSOR,
            DOMAIN,
            f"{self._entry.entry_id}_{CONF_DOOR_STATE_SENSOR}",
        )
        self.id_manual_speed = registry.async_get_entity_id(
            "number", DOMAIN, f"{self._entry.entry_id}_{CONF_MANUAL_AIR_SPEED}"
        )

        number_entities = [
            self.id_f_out,
            self.id_f_win,
            self.id_k_loss,
            self.id_k_solar,
        ]

        if not all(number_entities):
            _LOGGER.warning("Could not find all number entities for %s", self.entity_id)
            return

        # ONLY Listen for manual changes to the primary profile number entities
        self.async_on_remove(
            async_track_state_change_event(
                self.hass, number_entities, self._handle_number_change
            )
        )

    async def _get_current_number_values(self) -> list[float] | None:
        """Helper to safely read current values from number entities."""
        try:
            # We read states directly since we are not in the main update loop.
            values = [
                float(self.hass.states.get(self.id_f_out).state),
                float(self.hass.states.get(self.id_f_win).state),
                float(self.hass.states.get(self.id_k_loss).state),
                float(self.hass.states.get(self.id_k_solar).state),
            ]
            # Rounding to 2 decimal places to match the stored data/presets,
            # ensuring accurate comparison.
            return [round(v, 2) for v in values]
        except (AttributeError, ValueError):
            return None

    async def _load_data_and_build_options(self) -> None:
        """Load from store and build the _attr_options list."""
        data = await self._store.async_load() or {}

        migrated = False
        if isinstance(data, list):
            _LOGGER.warning("Migrating old custom profile data from list structure.")
            data = {STORE_KEY_CUSTOM: data, STORE_KEY_SAVED: {}}
            migrated = True

        self._custom_profile_data = data.get(STORE_KEY_CUSTOM)
        self._saved_profiles = data.get(STORE_KEY_SAVED, {})

        if migrated:
            await self._store.async_save(data)  # Save the new structure

        # Dynamically build the options list
        self._attr_options = (
            list(ROOM_PROFILES.keys())
            + list(self._saved_profiles.keys())
            + [CUSTOM_PROFILE_KEY]
        )
        _LOGGER.debug("Rebuilt profile options list")

    @callback
    def _handle_number_change(self, event):
        """Handle manual changes to the number entities."""
        if self._is_updating:
            return

        try:
            current_values = [
                float(self.hass.states.get(self.id_f_out).state),
                float(self.hass.states.get(self.id_f_win).state),
                float(self.hass.states.get(self.id_k_loss).state),
                float(self.hass.states.get(self.id_k_solar).state),
            ]
        except (AttributeError, ValueError):
            _LOGGER.debug("Number entity state not ready during check")
            return

        # Check if current values match the selected profile
        current_profile_data: list[float] | None = None
        if self._attr_current_option in ROOM_PROFILES:
            current_profile_data = ROOM_PROFILES[self._attr_current_option]["data"]
        elif self._attr_current_option in self._saved_profiles:
            current_profile_data = self._saved_profiles[self._attr_current_option]
        elif self._attr_current_option == CUSTOM_PROFILE_KEY:
            current_profile_data = self._custom_profile_data

        # If values don't match, or we have no profile, switch to Custom
        if current_values != current_profile_data:
            _LOGGER.debug("Numbers changed, saving to 'custom' and switching profile")
            self._custom_profile_data = current_values

            # Save the new "custom" data to the store
            self.hass.async_create_task(self._save_custom_profile())

            self._attr_current_option = CUSTOM_PROFILE_KEY
            self.async_write_ha_state()

    async def _save_custom_profile(self) -> None:
        """Save just the 'custom' key to the store."""
        data = await self._store.async_load() or {}
        data[STORE_KEY_CUSTOM] = self._custom_profile_data
        await self._store.async_save(data)
        _LOGGER.debug("Updated stored 'custom' profile")

    async def async_find_matching_profile(self) -> str:
        """
        Compares current number entity states against all ROOM_PROFILES
        and returns the key of the matching profile, or CUSTOM_PROFILE_KEY if none match.
        """
        current_values = await self._get_current_number_values()

        if not current_values:
            # If we can't read the current state, default to Custom as we don't know the state
            return CUSTOM_PROFILE_KEY

        # Check against all static profiles
        for key, profile in ROOM_PROFILES.items():
            preset_data = [round(v, 2) for v in profile["data"]]

            # Using == for comparison since both lists are lists of floats
            if current_values == preset_data:
                return key

        # Check against the saved custom profiles (if needed, though post-delete is mainly about defaults)
        for key, values in self._saved_profiles.items():
            saved_data = [round(v, 2) for v in values]
            if current_values == saved_data:
                return key

        return CUSTOM_PROFILE_KEY

    async def async_select_option(self, option: str) -> None:
        """Handle profile selection."""

        preset_data: list[float] | None = None

        # Check all three possible sources for the profile data
        if option in ROOM_PROFILES:
            preset_data = ROOM_PROFILES[option]["data"]
            _LOGGER.debug("Setting number entities to '%s' profile", option)
        elif option in self._saved_profiles:
            preset_data = self._saved_profiles[option]
            _LOGGER.debug("Setting number entities to saved '%s' profile", option)
        elif option == CUSTOM_PROFILE_KEY:
            if self._custom_profile_data:
                preset_data = self._custom_profile_data
                _LOGGER.debug("Setting number entities to stored 'Custom' profile")
            else:
                _LOGGER.warning("Custom profile selected, but no data saved yet.")
                preset_data = None  # Don't change numbers
        else:
            _LOGGER.error("Selected profile '%s' not found", option)
            return

        self._is_updating = True

        if preset_data:
            # Set all number entities to the selected profile's values
            await self.hass.services.async_call(
                "number",
                SERVICE_SET_VALUE,
                {"entity_id": self.id_f_out, "value": preset_data[0]},
                blocking=True,
            )
            await self.hass.services.async_call(
                "number",
                SERVICE_SET_VALUE,
                {"entity_id": self.id_f_win, "value": preset_data[1]},
                blocking=True,
            )
            await self.hass.services.async_call(
                "number",
                SERVICE_SET_VALUE,
                {"entity_id": self.id_k_loss, "value": preset_data[2]},
                blocking=True,
            )
            await self.hass.services.async_call(
                "number",
                SERVICE_SET_VALUE,
                {"entity_id": self.id_k_solar, "value": preset_data[3]},
                blocking=True,
            )

        # Update our own state to the newly selected option
        self._attr_current_option = option
        self.async_write_ha_state()

        self._is_updating = False

    async def async_update_options_and_select(self, new_option_name: str) -> None:
        """
        Called by button entities to refresh the options list
        and set the current option.
        """
        await self._load_data_and_build_options()
        if new_option_name == CUSTOM_PROFILE_KEY:
            # Find the true current profile based on the number entity states
            active_profile = await self.async_find_matching_profile()
            self._attr_current_option = active_profile
        else:
            self._attr_current_option = new_option_name

        self.async_write_ha_state()
