"""Unit normalisation helpers: everything is converted to °C, m/s and hPa."""

from __future__ import annotations

from homeassistant.const import (
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import State
from homeassistant.util.unit_conversion import (
    PressureConverter,
    SpeedConverter,
    TemperatureConverter,
)

_BAD_STATES = ("unknown", "unavailable", "none", "")


def _to_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _convert(converter, value: float | None, unit: str | None, target: str) -> float | None:
    """Convert value to target unit; if the unit is missing/unknown assume it is already target."""
    if value is None:
        return None
    if not unit or unit == target:
        return value
    try:
        return converter.convert(value, unit, target)
    except Exception:  # unsupported unit string
        return value


def state_temp_c(state: State | None) -> float | None:
    """Temperature of a sensor state in °C (honours unit_of_measurement)."""
    if state is None or str(state.state).lower() in _BAD_STATES:
        return None
    return _convert(
        TemperatureConverter,
        _to_float(state.state),
        state.attributes.get("unit_of_measurement"),
        UnitOfTemperature.CELSIUS,
    )


def state_speed_ms(state: State | None) -> float | None:
    """Wind speed of a sensor state in m/s (honours unit_of_measurement)."""
    if state is None or str(state.state).lower() in _BAD_STATES:
        return None
    return _convert(
        SpeedConverter,
        _to_float(state.state),
        state.attributes.get("unit_of_measurement"),
        UnitOfSpeed.METERS_PER_SECOND,
    )


def weather_temp_c(state: State | None, attr: str = "temperature") -> float | None:
    """A temperature attribute of a weather entity in °C (uses temperature_unit)."""
    if state is None:
        return None
    return _convert(
        TemperatureConverter,
        _to_float(state.attributes.get(attr)),
        state.attributes.get("temperature_unit"),
        UnitOfTemperature.CELSIUS,
    )


def weather_speed_ms(state: State | None, attr: str = "wind_speed") -> float | None:
    """Wind speed attribute of a weather entity in m/s (uses wind_speed_unit)."""
    if state is None:
        return None
    return _convert(
        SpeedConverter,
        _to_float(state.attributes.get(attr)),
        state.attributes.get("wind_speed_unit"),
        UnitOfSpeed.METERS_PER_SECOND,
    )


def weather_pressure_hpa(state: State | None) -> float | None:
    """Pressure attribute of a weather entity in hPa (uses pressure_unit)."""
    if state is None:
        return None
    return _convert(
        PressureConverter,
        _to_float(state.attributes.get("pressure")),
        state.attributes.get("pressure_unit"),
        UnitOfPressure.HPA,
    )


def state_pressure_hpa(state: State | None) -> float | None:
    """Pressure of a sensor state in hPa (honours unit_of_measurement)."""
    if state is None or str(state.state).lower() in _BAD_STATES:
        return None
    return _convert(
        PressureConverter,
        _to_float(state.state),
        state.attributes.get("unit_of_measurement"),
        UnitOfPressure.HPA,
    )
