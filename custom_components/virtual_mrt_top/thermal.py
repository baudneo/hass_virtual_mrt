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


# --- Adaptive comfort (ASHRAE 55 adaptive model / EN 16798 running mean) ---

ADAPTIVE_MIN_RM = 10.0
ADAPTIVE_MAX_RM = 33.5
RUNNING_MEAN_ALPHA = 0.8  # EN 16798-1 weighting of previous days


def adaptive_comfort_temp(t_running_mean: float) -> float:
    """Neutral operative temperature (C) from the prevailing outdoor temperature."""
    return 0.31 * t_running_mean + 17.8


def adaptive_limits(t_comf: float) -> dict[str, float]:
    """ASHRAE 55 acceptability limits: 90% (+-2.5 K) and 80% (+-3.5 K)."""
    return {
        "acceptable_90_low": round(t_comf - 2.5, 2),
        "acceptable_90_high": round(t_comf + 2.5, 2),
        "acceptable_80_low": round(t_comf - 3.5, 2),
        "acceptable_80_high": round(t_comf + 3.5, 2),
    }


class OutdoorRunningMean:
    """
    Exponentially weighted running mean of daily mean outdoor temperature.

    Trm_today = (1 - a) * T_yesterday_mean + a * Trm_yesterday  (a = 0.8).
    Daily means are time-weighted from the samples fed to `update`.
    """

    MAX_GAP_S = 6 * 3600  # don't let one stale sample dominate a whole day

    def __init__(self, alpha: float = RUNNING_MEAN_ALPHA) -> None:
        self.alpha = alpha
        self.rm: float | None = None
        self.day: int | None = None
        self._sum = 0.0
        self._weight = 0.0
        self._last_ts: float | None = None
        self._last_temp: float | None = None

    def update(self, day: int, ts: float, temp: float) -> None:
        """Feed an outdoor temperature sample (`day` is any per-day key, e.g. ordinal)."""
        if self.day is None:
            self.day = day
        elif day != self.day:
            self._close_day()
            self.day = day
            self._sum = 0.0
            self._weight = 0.0
            # Don't attribute the overnight gap to the new day
            self._last_ts = None
            self._last_temp = None
        if self._last_ts is not None and self._last_temp is not None:
            dt = min(ts - self._last_ts, self.MAX_GAP_S)
            if dt > 0:
                self._sum += self._last_temp * dt
                self._weight += dt
        self._last_ts = ts
        self._last_temp = temp

    def _today_mean(self) -> float | None:
        if self._weight > 0:
            return self._sum / self._weight
        return self._last_temp

    def _close_day(self) -> None:
        mean = self._today_mean()
        if mean is None:
            return
        self.rm = mean if self.rm is None else (1 - self.alpha) * mean + self.alpha * self.rm

    @property
    def value(self) -> float | None:
        """Best current estimate (falls back to today's mean while seeding)."""
        return self.rm if self.rm is not None else self._today_mean()

    def as_dict(self) -> dict:
        return {"rm": self.rm, "day": self.day}

    def restore(self, data: dict) -> None:
        try:
            rm = data.get("rm")
            self.rm = float(rm) if rm is not None else None
            day = data.get("day")
            self.day = int(day) if day is not None else None
        except (TypeError, ValueError):
            self.rm, self.day = None, None
