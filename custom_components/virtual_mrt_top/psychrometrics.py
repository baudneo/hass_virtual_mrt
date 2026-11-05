"""Pure psychrometric / thermal-comfort math (no Home Assistant imports)."""

from __future__ import annotations

import math


class Psychrometrics:
    """Helper for thermodynamic calculations."""

    @staticmethod
    def calculate_pmv(t_air, t_mrt, v_air, rh, met, clo):
        """
        Calculate PMV (Predicted Mean Vote) using ISO 7730 / ASHRAE 55.
        """
        # 1. Convert Inputs
        ta = t_air
        tr = t_mrt
        vel = max(0.1, v_air)  # Min velocity for stability
        rh_frac = rh / 100.0

        # Metabolism: 1 met = 58.15 W/m2
        m = met * 58.15

        # External Work (assume 0 for home/office)
        w = 0.0

        # Internal Heat Production
        mw = m - w

        # Clothing Insulation: 1 clo = 0.155 m2K/W
        icl = clo * 0.155

        # Clothing Area Factor (fcl)
        if icl <= 0.078:
            fcl = 1.0 + (1.29 * icl)
        else:
            fcl = 1.05 + (0.645 * icl)

        # Vapor Pressure (Pa)
        # Use existing helper but convert hPa -> Pa
        vp_hpa = Psychrometrics.calculate_vapor_pressure(ta) * rh_frac
        pa = vp_hpa * 100.0

        # 2. Iterative Calculation for Clothing Surface Temp (t_cl)
        # Starting guess: t_cl = t_air
        t_cl = ta
        t_abs = ta + 273.15
        tr_abs = tr + 273.15

        # Iteration variables
        hc = 12.1 * math.sqrt(vel)  # Convective heat transfer coef
        n_iter = 0
        eps = 0.00015  # Stopping tolerance

        while n_iter < 150:
            t_cl_old = t_cl
            t_cl_abs = t_cl + 273.15

            # Radiative Heat Transfer
            # h_r = 4 * sigma * f_cl ... simplified for linearization
            # We compute terms directly in balance equation below

            # Convection coeff (hc) depends on T_cl vs T_air (Natural vs Forced)
            hc_forced = 12.1 * math.sqrt(vel)
            hc_natural = 2.38 * abs(t_cl - ta) ** 0.25
            hc = max(hc_forced, hc_natural)

            # Heat Balance Equation terms
            # Radiation Term: 3.96*10^-8 * fcl * (Tcl^4 - Tr^4)
            rad = 3.96 * 10**-8 * fcl * (t_cl_abs**4 - tr_abs**4)

            # Convection Term: fcl * hc * (Tcl - Ta)
            conv = fcl * hc * (t_cl - ta)

            # T_cl new estimate
            # T_cl = 35.7 - 0.028(M-W) - I_cl * (Rad + Conv)
            t_cl_new = (35.7 - 0.028 * mw) - (icl * (rad + conv))

            # Dampening
            t_cl = (t_cl_new + t_cl_old) / 2.0

            if abs(t_cl - t_cl_old) < eps:
                break
            n_iter += 1

        # 3. Calculate Heat Loss Components (ISO 7730)
        # Skin diffusion
        hl1 = 3.05 * 0.001 * (5733 - (6.99 * mw) - pa)
        # Sweat (Latent)
        if mw > 58.15:
            hl2 = 0.42 * (mw - 58.15)
        else:
            hl2 = 0.0
        # Latent Respiration
        hl3 = 1.7 * 0.00001 * m * (5867 - pa)
        # Dry Respiration
        hl4 = 0.0014 * m * (34 - ta)
        # Radiation
        hl5 = 3.96 * 10**-8 * fcl * ((t_cl + 273.15) ** 4 - tr_abs**4)
        # Convection
        hl6 = fcl * hc * (t_cl - ta)

        # 4. Final PMV Calc
        ts = 0.303 * math.exp(-0.036 * m) + 0.028
        pmv = ts * (mw - hl1 - hl2 - hl3 - hl4 - hl5 - hl6)

        return max(-3.5, min(3.5, pmv))  # Clamp to valid range

    @staticmethod
    def calculate_humidity_ratio(vp_actual: float, pressure_hpa: float) -> float:
        """
        Calculate Mixing Ratio (W) in g_water / kg_dry_air.
        """
        # W = 0.622 * e / (P - e)
        # Result is kg/kg, multiply by 1000 for g/kg
        if (pressure_hpa - vp_actual) <= 0:
            return 0.0
        w = 0.622 * vp_actual / (pressure_hpa - vp_actual)
        return w * 1000.0

    @staticmethod
    def calculate_air_density(
        t_air: float, vp_actual: float, pressure_hpa: float
    ) -> float:
        """
        Calculate Moist Air Density in kg/m³.
        """
        # Gas Constants
        R_d = 287.058  # Dry Air J/(kg·K)
        R_v = 461.495  # Water Vapor J/(kg·K)

        t_kelvin = t_air + 273.15
        p_total_pa = pressure_hpa * 100.0
        e_pa = vp_actual * 100.0
        p_dry_pa = p_total_pa - e_pa

        # density = (Pd / (Rd * T)) + (Pv / (Rv * T))
        rho = (p_dry_pa / (R_d * t_kelvin)) + (e_pa / (R_v * t_kelvin))
        return rho

    @staticmethod
    def calculate_vapor_pressure(t_air: float) -> float:
        """Calculate saturation vapor pressure (hPa) using Magnus formula."""
        return 6.112 * math.exp((17.67 * t_air) / (t_air + 243.5))

    @staticmethod
    def calculate_dew_point(t_air: float, rh: float) -> float:
        """Calculate Dew Point (°C)."""
        if rh <= 0:
            return -50.0  # Safety
        a = 17.27
        b = 237.7
        # Alpha parameter
        alpha = ((a * t_air) / (b + t_air)) + math.log(rh / 100.0)
        return (b * alpha) / (a - alpha)

    @staticmethod
    def calculate_frost_point(t_air: float, dew_point: float, rh: float | None = None) -> float:
        """
        Calculate Frost Point (°C): the temperature at which air saturates over ice.
        Above 0 °C it equals the dew point; below 0 °C it is higher than the dew point.
        """
        if dew_point >= 0:
            return dew_point
        # Vapor pressure at the dew point (over water), then invert Magnus over ice.
        e = 6.112 * math.exp((17.62 * dew_point) / (243.12 + dew_point))
        ln_ratio = math.log(e / 6.112)
        a, b = 22.46, 272.62
        return (b * ln_ratio) / (a - ln_ratio)

    @staticmethod
    def calculate_enthalpy(
        t_air: float, rh: float, pressure_hpa: float = 1013.25
    ) -> float:
        """
        Calculate Air Enthalpy (kJ/kg).
        Requires Pressure in hPa (mbar).
        """
        vp_sat = Psychrometrics.calculate_vapor_pressure(t_air)
        vp_actual = vp_sat * (rh / 100.0)

        # Humidity Ratio (W) calculation depends on Pressure!
        # W = 0.622 * e / (P - e)
        # If P is lower (altitude), W is higher.
        if (pressure_hpa - vp_actual) <= 0:
            return 1.006 * t_air
        w = 0.622 * vp_actual / (pressure_hpa - vp_actual)

        # H = 1.006*T + W*(2501 + 1.86*T)
        return (1.006 * t_air) + (w * (2501 + 1.86 * t_air))

    @staticmethod
    def calculate_humidex(t_air: float, dew_point: float) -> float:
        """Calculate Humidex (°C)."""
        # Humidex = T + 0.5555 * (e - 10)
        # e = vapor pressure in hPa (mbar)

        # Calculate e from dewpoint (inverse Magnus)
        e = 6.11 * math.exp(5417.7530 * ((1 / 273.16) - (1 / (273.15 + dew_point))))

        return t_air + 0.5555 * (e - 10)
