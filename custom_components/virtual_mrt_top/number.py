"""Number platform for Virtual MRT."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberMode,
    RestoreNumber,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import (
    DOMAIN,
    CONF_ROOM_PROFILE,
    ROOM_PROFILES,
    CONF_THERMAL_ALPHA,
    CONF_MANUAL_AIR_SPEED,
    CONF_HVAC_AIR_SPEED,
    CONF_RADIANT_SURFACE_TEMP,
)
from .device_info import get_device_info


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up number entities."""
    config = entry.data

    # Get the default values from the selected profile
    profile_key = config[CONF_ROOM_PROFILE]
    defaults = ROOM_PROFILES[profile_key]["data"]  # [f_out, f_win, k_loss, k_solar]
    device_info = await get_device_info({(DOMAIN, entry.entry_id)}, config[CONF_NAME])
    entities = [
        VirtualFactorNumber(
            entry,
            device_info,
            "f_out",
            "exterior_envelope_ratio",
            "mdi:wall",
            defaults[0],
            0.0,
            2.0,
        ),
        VirtualFactorNumber(
            entry,
            device_info,
            "f_win",
            "window_share",
            "mdi:window-closed",
            defaults[1],
            0.0,
            1.0,
        ),
        VirtualFactorNumber(
            entry,
            device_info,
            "k_loss",
            "insulation_loss_factor",
            "mdi:snowflake-thermometer",
            defaults[2],
            0.0,
            1.0,
        ),
        VirtualFactorNumber(
            entry,
            device_info,
            "k_solar",
            "solar_gain_factor",
            "mdi:sun-wireless",
            defaults[3],
            0.0,
            2.0,
        ),
        VirtualThermalAlphaNumber(
            entry, device_info, CONF_THERMAL_ALPHA, "thermal_alpha", 0.3, 0.05, 0.95
        ),
        VirtualAirSpeedNumber(
            entry, device_info, CONF_MANUAL_AIR_SPEED, "manual_air_speed", 0.1, 0.0, 2.0
        ),
        VirtualAirSpeedNumber(
            entry, device_info, CONF_HVAC_AIR_SPEED, "hvac_air_speed", 0.4, 0.0, 2.0
        ),
        VirtualSurfaceTargetTempNumber(
            entry,
            device_info,
            CONF_RADIANT_SURFACE_TEMP,
            "radiant_surface_temp",
            26.0,
            0.0,
            85.0,
        ),
    ]

    async_add_entities(entities)


class VirtualFactorNumber(RestoreNumber):
    """A number entity that restores its value on restart."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        entry: ConfigEntry,
        device_info,
        key,
        translation_key,
        icon,
        default_val,
        min_val,
        max_val,
    ):
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self.translation_key = translation_key
        self._attr_device_info = device_info
        self._icon = icon

        self._default_val = default_val
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step = 0.01
        self._attr_native_value = default_val

    @property
    def icon(self) -> str | None:
        return self._icon

    @icon.setter
    def icon(self, value):
        self._icon = value

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()
        last_data = await self.async_get_last_number_data()
        if last_data is not None:
            self._attr_native_value = last_data.native_value

    async def async_set_native_value(self, value: float) -> None:
        """Update the value."""
        self._attr_native_value = value
        self.async_write_ha_state()


class VirtualThermalAlphaNumber(RestoreNumber):
    """A number entity for setting the smoothing factor (alpha)."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:speedometer-slow"

    def __init__(
        self,
        entry: ConfigEntry,
        device_info,
        key,
        translation_key,
        default_val,
        min_val,
        max_val,
    ):
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"

        self.translation_key = translation_key
        self._attr_device_info = device_info

        self._default_val = default_val
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step = 0.01
        self._attr_native_value = default_val

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()
        last_data = await self.async_get_last_number_data()
        if last_data is not None:
            self._attr_native_value = last_data.native_value

    async def async_set_native_value(self, value: float) -> None:
        """Update the value."""
        # Clamp value to be sure, although the UI should prevent it
        value = min(0.95, max(0.05, value))
        self._attr_native_value = value
        self.async_write_ha_state()


class VirtualSurfaceTargetTempNumber(RestoreNumber):
    """A number entity for setting surface target temperature in the local unit (default: °C)."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:thermometer-lines"
    _attr_native_unit_of_measurement = "°C"

    def __init__(
        self,
        entry: ConfigEntry,
        device_info,
        key,
        translation_key,
        default_val,
        min_val,
        max_val,
    ):
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"

        self.translation_key = translation_key
        self._attr_device_info = device_info

        self._default_val = default_val
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step = 0.1
        self._attr_native_value = default_val

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()
        last_data = await self.async_get_last_number_data()
        if last_data is not None:
            self._attr_native_value = last_data.native_value

    async def async_set_native_value(self, value: float) -> None:
        """Update the value."""
        self._attr_native_value = value
        self.async_write_ha_state()


class VirtualAirSpeedNumber(RestoreNumber):
    """A number entity for setting air speed (m/s)."""

    _attr_has_entity_name = True
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:tailwind"
    _attr_native_unit_of_measurement = "m/s"

    def __init__(
        self,
        entry: ConfigEntry,
        device_info,
        key,
        translation_key,
        default_val,
        min_val,
        max_val,
    ):
        self._key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"

        self.translation_key = translation_key
        self._attr_device_info = device_info

        self._default_val = default_val
        self._attr_native_min_value = min_val
        self._attr_native_max_value = max_val
        self._attr_native_step = 0.1
        self._attr_native_value = default_val

    async def async_added_to_hass(self) -> None:
        """Restore last state."""
        await super().async_added_to_hass()
        last_data = await self.async_get_last_number_data()
        if last_data is not None:
            self._attr_native_value = last_data.native_value

    async def async_set_native_value(self, value: float) -> None:
        """Update the value, clamping to minimum of 0.0."""
        value = max(0.0, value)
        self._attr_native_value = value
        self.async_write_ha_state()
