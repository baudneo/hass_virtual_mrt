"""Smoke test: run the MRT calculation end-to-end against a fake hass."""

from types import SimpleNamespace

import pytest
from homeassistant.core import State

from custom_components.virtual_mrt_top.const import DOMAIN
from custom_components.virtual_mrt_top.sensor import VirtualMRTSensor


def _make(states, radiant=False, climate=None):
    data = {
        "air_temp_source": "sensor.air",
        "weather_entity": "weather.home",
        "room_profile": "one_wall_large_window",
        "orientation": "S",
        "is_radiant_heating": radiant,
        "climate_entity": climate,
    }
    entry = SimpleNamespace(data=data, entry_id="e1")
    hass = SimpleNamespace(states=SimpleNamespace(get=lambda eid: states.get(eid)))
    s = VirtualMRTSensor(hass, entry, {})
    # skip the registry lookups: pretend the helper entities exist and read as defaults
    for attr in (
        "id_f_out", "id_f_win", "id_k_loss", "id_k_solar", "id_profile_select",
        "id_thermal_alpha", "id_manual_speed", "id_hvac_speed", "id_radiant_temp",
        "id_radiant_type",
    ):
        setattr(s, attr, f"number.{attr}")
    return s


def _states(t_out, unit="°C", sun_el=30, sun_az=180, **extra):
    st = {
        "sensor.air": State("sensor.air", "21", {"unit_of_measurement": "°C"}),
        "weather.home": State(
            "weather.home", "sunny",
            {"temperature": t_out, "temperature_unit": unit, "humidity": 50,
             "wind_speed": 10, "wind_speed_unit": "km/h", "cloud_coverage": 0},
        ),
        "sun.sun": State("sun.sun", "above_horizon", {"azimuth": sun_az, "elevation": sun_el}),
    }
    st.update(extra)
    return st


def test_winter_mrt_below_air():
    s = _make(_states(-10))
    s._update_calc()
    assert s.native_value < 21
    assert s.extra_state_attributes["wind_ms"] == pytest.approx(2.78, abs=0.01)


def test_summer_mrt_above_air_and_uses_sol_air():
    s = _make(_states(34, sun_el=60))
    s._update_calc()
    assert s.native_value > 21
    assert s.extra_state_attributes["t_out_eff_source"] == "dry_bulb_plus_sol_air"


def test_fahrenheit_weather_is_converted():
    s = _make(_states(14, unit="°F"))  # 14 F = -10 C
    s._update_calc()
    assert s.extra_state_attributes["outdoor_temp"] == pytest.approx(-10, abs=0.01)


def test_radiant_with_climate_list_does_not_crash_and_has_no_forced_air():
    climate = State("climate.floor", "heat", {"hvac_action": "heating"})
    st = _states(-5, **{"climate.floor": climate})
    s = _make(st, radiant=True, climate=["climate.floor"])
    s._update_calc()
    assert s.extra_state_attributes["air_speed_ms_convective"] == pytest.approx(0.1)
    assert s.extra_state_attributes["is_heating"] is True


def test_climate_off_with_fan_mode_is_ignored_and_action_inferred():
    off = State("climate.ms", "off", {"fan_mode": "low"})
    hot = State("climate.hot", "heat", {"current_temperature": 18, "temperature": 22})
    s = _make(_states(0, **{"climate.ms": off, "climate.hot": hot}),
              climate=["climate.ms", "climate.hot"])
    info = s._get_aggregate_climate_state()
    assert info["is_heating"] is True
    assert info["is_fan_active"] is False


def test_missing_air_temp_goes_unknown():
    st = _states(0)
    s = _make(st)
    s._update_calc()
    assert s.native_value is not None
    st["sensor.air"] = State("sensor.air", "unavailable")
    s._update_calc()
    assert s.native_value is None


def test_radiant_cooling_uses_cooling_setpoint_and_cools():
    climate = State("climate.slab", "cool", {"hvac_action": "cooling"})
    st = _states(32, **{
        "climate.slab": climate,
        "number.id_radiant_temp": State("number.id_radiant_temp", "26"),
        "number.id_radiant_cool_temp": State("number.id_radiant_cool_temp", "18"),
        "number.id_radiant_type": State("number.id_radiant_type", "0"),
    })
    s = _make(st, radiant=True, climate=["climate.slab"])
    s._update_calc()
    # chilled surface (18) below room air (21) -> negative boost, not the heating setpoint
    assert s.extra_state_attributes["radiant_boost_current"] < 0

