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
