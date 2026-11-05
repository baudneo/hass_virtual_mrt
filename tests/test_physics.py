"""Tests for the pure physics helpers and unit normalisation."""

import math

import pytest
from homeassistant.core import State

from custom_components.virtual_mrt_top.psychrometrics import Psychrometrics as P
from custom_components.virtual_mrt_top import units


def test_frost_point_equals_dew_point_above_zero():
    assert P.calculate_frost_point(20, 10) == 10


def test_frost_point_above_dew_point_below_zero():
    # Known value: dew point -10 C -> frost point about -8.9 C
    fp = P.calculate_frost_point(-5, -10)
    assert -10 < fp < -8
    assert fp == pytest.approx(-8.87, abs=0.05)


def test_dew_point_at_saturation_equals_air_temp():
    assert P.calculate_dew_point(20, 100) == pytest.approx(20, abs=0.01)


def test_pmv_matches_iso7730_reference():
    # ISO 7730 Annex D: 22 C, v=0.10 m/s, 60% RH, 1.2 met, 0.5 clo -> PMV about -0.75
    assert P.calculate_pmv(22, 22, 0.1, 60, 1.2, 0.5) == pytest.approx(-0.75, abs=0.05)


def test_pmv_hot_is_positive_cold_is_negative():
    assert P.calculate_pmv(30, 30, 0.1, 50, 1.2, 0.5) > 1.5
    assert P.calculate_pmv(14, 14, 0.1, 50, 1.2, 0.5) < -1.5


def test_enthalpy_guard_on_degenerate_pressure():
    assert math.isfinite(P.calculate_enthalpy(20, 50, 10.0))


def test_state_temp_converts_fahrenheit():
    st = State("sensor.t", "68", {"unit_of_measurement": "°F"})
    assert units.state_temp_c(st) == pytest.approx(20.0)


def test_state_temp_unavailable():
    assert units.state_temp_c(State("sensor.t", "unavailable")) is None


@pytest.mark.parametrize(
    "unit,value,expected",
    [("km/h", 36, 10.0), ("m/s", 10, 10.0), ("mph", 22.369, 10.0), ("kn", 19.438, 10.0)],
)
def test_weather_wind_units(unit, value, expected):
    st = State("weather.x", "sunny", {"wind_speed": value, "wind_speed_unit": unit})
    assert units.weather_speed_ms(st) == pytest.approx(expected, abs=0.01)


def test_weather_pressure_inhg():
    st = State("weather.x", "sunny", {"pressure": 29.92, "pressure_unit": "inHg"})
    assert units.weather_pressure_hpa(st) == pytest.approx(1013.2, abs=0.5)
