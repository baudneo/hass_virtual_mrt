# 🌡️ Virtual Thermal Comfort (MRT & Operative Temperature)

[![HACS Badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=baudneo&repository=hass_virtual_mrt&category=integration)

This integration brings professional building science concepts into Home Assistant. Instead of just looking at standard air temperature, this integration creates a **Virtual Room Device** that calculates how hot or cold a person *actually feels*.

* **Standard Thermometers** measure Air Temperature ($T_{air}$). 🌡️
* **This Integration** calculates **Operative Temperature** ($T_{op}$), accounting for air temperature, the radiant heat of surrounding walls/windows, and local air velocity.

It does this by computing the **Mean Radiant Temperature (MRT)**, which tracks the thermal inertia of your room's surfaces based on outside weather, insulation quality, and sun exposure. ☀️

---

## 🙏 Thanks & Credits
Ported and expanded from a blueprint that [@Ecronika](https://github.com/Ecronika) [shared in the Home Assistant Community Forums](https://community.home-assistant.io/t/blueprint-virtual-mrt-v0-1-10-mean-radiant-temperature-operative-temperature/945267/3).

---

## 📚 Documentation Index

To keep this README short, detailed guides and formulas are located in the `docs/` folder:

1. **[🏠 Core Concepts: Layman's Guide](./docs/concepts.md)** - What is MRT, $T_{op}$, and Thermal Mass? Why should you care?
2. **[⚙️ Setup & Configuration Guide](./docs/setup.md)** - Step-by-step installation and config flow examples.
3. **[🔬 Advanced Physics & Formulas](./docs/advanced_physics.md)** - Detailed formulas for air speed, solar gain, and radiant heating models.
4. **[💧 Psychrometrics, Comfort & Mold](./docs/psychrometrics.md)** - Deep dive into Dew Point, Mold Risk, PMV, Heat Flux, and Enthalpy.
5. **[🏢 Zone Aggregators](./docs/aggregators.md)** - Group rooms to calculate HVAC spread or multi-floor Stack Effect.

---

## ⚡ Quick Features

* **True Comfort Metrics:** Automate your HVAC using $T_{op}$ rather than simple air temperature.
* **Radiant Heating/Cooling Support:** Accurately models the slow thermal lag of in-floor systems and radiators.
* **Advanced Mold Risk Detection:** Calculates relative humidity at the *wall surface*, where mold actually starts.
* **Heat Flux Monitoring:** Estimates actual heat loss (Watts) through walls and windows.
* **PMV & Thermal Perception:** ISO 7730 standard metrics for human comfort.
