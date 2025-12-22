"""Text platform for Virtual MRT."""

from __future__ import annotations

from homeassistant.components.text import (
    TextMode,
    RestoreText,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, CONF_DEVICE_TYPE, TYPE_AGGREGATOR, get_device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up the text entity."""
    config = entry.data
    if config.get(CONF_DEVICE_TYPE) == TYPE_AGGREGATOR:
        return
    device_info = await get_device_info({(DOMAIN, entry.entry_id)}, config[CONF_NAME])

    async_add_entities([VirtualProfileText(hass, entry, device_info)])


class VirtualProfileText(RestoreText):
    """Text entity for naming a profile to save/delete."""

    _attr_has_entity_name = True
    _attr_mode = TextMode.TEXT
    _attr_icon = "mdi:form-textbox"
    translation_key = "profile_name"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_info):
        self.hass = hass
        self._attr_unique_id = f"{entry.entry_id}_profile_name"
        self._attr_device_info = device_info
        self._attr_native_value = ""

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()
        last_data = await self.async_get_last_text_data()
        if last_data:
            self._attr_native_value = last_data.native_value

    def set_value(self, value: str) -> None:
        """Handle synchronous set_value calls (required for service calls)."""
        # Since RestoreText uses _attr_native_value, we update that directly
        self.set_native_value(value)

    def set_native_value(self, value: str) -> None:
        """Set the native value."""
        self._attr_native_value = value

    async def async_set_native_value(self, value: str) -> None:
        """Update the value asynchronously (used by the HA API)."""
        self._attr_native_value = value
        self.async_write_ha_state()
