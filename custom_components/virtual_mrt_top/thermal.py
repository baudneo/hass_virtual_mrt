"""Pure helpers for the MRT model (no Home Assistant imports)."""

from __future__ import annotations

import math

DIFFUSE_BASELINE = 0.1
# Below this sun elevation the old (winter-tuned) incidence model is unchanged.
_REFERENCE_ELEVATION_TAN = math.tan(math.radians(20.0))


def solar_incidence_factor(
    sun_azimuth: float, sun_elevation: float | None, window_azimuth: float
) -> float:
    """
    Fraction of GHI that reaches a vertical window (0.1 diffuse floor .. 1.0).

    A vertical surface sees GHI * cos(az_diff) / tan(elevation) of direct beam, so a
    high summer sun delivers far less through a south window than a low winter sun.
    The result is normalised so elevations <= 20 degrees match the original
    cosine-only model (preserving the winter tuning of k_solar).
    """
    if sun_elevation is not None and sun_elevation <= 0:
        return DIFFUSE_BASELINE

    diff = abs(sun_azimuth - window_azimuth) % 360
    if diff > 180:
        diff = 360 - diff
    if diff >= 90:
        return DIFFUSE_BASELINE

    direct = math.cos(math.radians(diff))
    if sun_elevation is not None:
        tan_el = math.tan(math.radians(min(sun_elevation, 89.0)))
        direct *= min(1.0, _REFERENCE_ELEVATION_TAN / tan_el)
    return min(1.0, direct + DIFFUSE_BASELINE)


def smoothing_alpha(alpha: float, dt: float | None, reference_period: float) -> float:
    """
    Convert a per-update EMA alpha into a time-aware one.

    `alpha` is defined for updates arriving every `reference_period` seconds; an
    update after a different gap `dt` gets alpha_eff = 1 - (1 - alpha)^(dt/ref).
    """
    if dt is None or reference_period <= 0 or alpha <= 0 or alpha >= 1:
        return min(1.0, max(0.0, alpha))
    dt = min(max(dt, 1.0), 3600.0)
    return 1.0 - (1.0 - alpha) ** (dt / reference_period)


def sol_air_increment(
    radiation: float, incidence: float, wind_ms: float, absorptance: float = 0.5
) -> float:
    """
    Temperature rise (K) of a sunlit exterior wall above outdoor air (sol-air).

    dT = a * I / h_o with h_o = 17 + 3.6*wind (W/m2K); capped at 8 K because only
    part of the envelope is sunlit and glazing is handled by the solar term.
    """
    irradiance = max(0.0, radiation) * max(0.0, incidence - 0.1)
    h_o = 17.0 + 3.6 * max(0.0, wind_ms)
    return min(8.0, absorptance * irradiance / h_o)


def mrt_weight_in_operative(v_air: float) -> float:
    """Weight of MRT in operative temperature (ISO 7726 / ASHRAE 55 table)."""
    if v_air < 0.2:
        return 0.5
    if v_air < 0.6:
        return 0.4
    return 0.3
