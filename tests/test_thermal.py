import pytest

from custom_components.virtual_mrt_top.thermal import (
    mrt_weight_in_operative,
    smoothing_alpha,
    sol_air_increment,
    solar_incidence_factor,
)


def test_incidence_unchanged_for_low_winter_sun():
    # Low sun due south on a south window: same as the original cos-only model (capped 1.0)
    assert solar_incidence_factor(180, 15, 180) == pytest.approx(1.0)
    assert solar_incidence_factor(180, None, 180) == pytest.approx(1.0)


def test_incidence_much_lower_for_high_summer_sun():
    winter = solar_incidence_factor(180, 20, 180)
    summer = solar_incidence_factor(180, 65, 180)
    assert summer < 0.35 * winter


def test_incidence_diffuse_when_behind_window_or_night():
    assert solar_incidence_factor(0, 30, 180) == pytest.approx(0.1)
    assert solar_incidence_factor(180, -5, 180) == pytest.approx(0.1)


def test_incidence_azimuth_wraparound():
    assert solar_incidence_factor(350, 20, 10) == solar_incidence_factor(10, 20, 350)


def test_smoothing_matches_alpha_at_reference_cadence():
    assert smoothing_alpha(0.3, 30, 30) == pytest.approx(0.3)


def test_smoothing_longer_gap_moves_further():
    assert smoothing_alpha(0.3, 120, 30) > 0.3
    assert smoothing_alpha(0.3, 120, 30) == pytest.approx(1 - 0.7**4)
    assert smoothing_alpha(0.3, None, 30) == 0.3


def test_sol_air_zero_without_sun_and_capped():
    assert sol_air_increment(0, 1.0, 0) == 0
    assert sol_air_increment(1000, 1.0, 0) == 8.0


@pytest.mark.parametrize("v,w", [(0.1, 0.5), (0.3, 0.4), (0.8, 0.3), (2.0, 0.3)])
def test_operative_weight_iso7726(v, w):
    assert mrt_weight_in_operative(v) == w


from custom_components.virtual_mrt_top.thermal import (  # noqa: E402
    OutdoorRunningMean,
    adaptive_comfort_temp,
    adaptive_limits,
)


def test_adaptive_comfort_temp_ashrae55():
    assert adaptive_comfort_temp(20) == pytest.approx(24.0)
    assert adaptive_comfort_temp(10) == pytest.approx(20.9)
    lim = adaptive_limits(24.0)
    assert lim["acceptable_90_high"] == 26.5 and lim["acceptable_80_low"] == 20.5


def test_running_mean_seeds_from_today_then_weights_days():
    m = OutdoorRunningMean()
    assert m.value is None
    # day 1: steady 10 C for 2 hours
    m.update(1, 0, 10)
    m.update(1, 3600, 10)
    m.update(1, 7200, 10)
    assert m.value == pytest.approx(10)       # seeding from today's mean
    assert m.rm is None
    # day 2 begins: day 1 closes -> rm = 10
    m.update(2, 86400, 20)
    assert m.rm == pytest.approx(10)
    m.update(2, 86400 + 3600, 20)
    # day 3: day 2 (mean 20) closes -> rm = 0.2*20 + 0.8*10 = 12
    m.update(3, 2 * 86400, 20)
    assert m.rm == pytest.approx(12)


def test_running_mean_restore_roundtrip():
    m = OutdoorRunningMean()
    m.restore({"rm": 15.5, "day": 100})
    assert m.value == 15.5 and m.as_dict() == {"rm": 15.5, "day": 100}
    m.restore({"rm": "garbage", "day": None})
    assert m.rm is None
