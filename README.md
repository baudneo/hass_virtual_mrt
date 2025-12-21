# 🌡️ Virtual Thermal Comfort (MRT & Operative Temperature)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=baudneo&repository=hass_virtual_mrt&category=integration)

## 🙏 Thanks
I ported this logic from a blueprint that [@Ecronika](https://github.com/Ecronika) [shared in the Home Assistant Community Forums](https://community.home-assistant.io/t/blueprint-virtual-mrt-v0-1-10-mean-radiant-temperature-operative-temperature/945267/3)

---

## 📝 Note
There is already a custom integration named ['Thermal Comfort' ](https://github.com/dolezsa/thermal_comfort) that uses air temp and relative humidity to expose some perception sensors alongside dew point, frost point and heat index/humidex.
This integration is different in that it focuses on **Mean Radiant Temperature (MRT)**, **Operative Temperature ($T_{op}$)**, and **Predicted Mean Vote (PMV)**—advanced concepts from building science that better represent how humans perceive temperature in a space based on the surrounding surfaces, air movement, and physiology.

---

## 🏡 Introduction: What This Integration Does

This integration brings a professional building science concept—**Thermal Comfort**—into Home Assistant. Instead of just showing the air temperature, this tool creates a **Virtual Room Device** that calculates how hot or cold a person *actually feels*.

* **Standard Thermometer:** Measures Air Temperature ($T_{air}$). 🌡️
* **Virtual Sensor:** Measures **Operative Temperature** ($T_{op}$), which is the most accurate single metric for human comfort, accounting for air temperature, the radiant heat from surrounding surfaces, and air velocity.
* **Health Monitor:** Tracks **Wall Heat Flux** (Energy Loss) and **Mold Risk** on cold surfaces.

This is achieved by computing the **Mean Radiant Temperature (MRT)**, which tracks the temperature of the walls, windows, and ceiling based on outside weather and sun exposure. ☀️

---

## 💡 Why MRT and $T_{op}$ Are Useful

| Sensor                        | Definition                                                                         | Use in HASS                                                                                                                                                                                                  |
|:------------------------------|:-----------------------------------------------------------------------------------|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Mean Radiant Temp (MRT)**   | The effective temperature of the room's surfaces (walls, windows, floor, ceiling). | Essential for **monitoring radiant systems** (floor heating/cooling). It allows you to see the **thermal lag** of your home's structure. 🐌                                                                  |
| **Operative Temp ($T_{op}$)** | The weighted average of the Air Temperature and the MRT.                           | **The ultimate trigger for HVAC automation.** Use $T_{op}$ instead of $T_{air}$ to ensure your heating/cooling system only runs when a person *feels* uncomfortable, saving energy and improving comfort. 🎯 |
| **PMV Score**                 | **Predicted Mean Vote.** The ISO 7730 Gold Standard for thermal comfort.           | **Human-Centric Logic.** A score from -3 (Cold) to +3 (Hot). It tells you if you need a sweater or AC, regardless of what the thermometer says. 🧘                                                           |

---

## 🏠 Room Configuration: Profiles and Inputs

This integration exposes a **Virtual Device** for each room you configure. This device contains the calculated $T_{op}$ and MRT sensors, along with a set of configurable **Number Inputs** to fine-tune the model to your home's unique physical characteristics.

### 1. The Core Configurable Inputs (Profiles)

The calculation relies on **four primary configurable inputs** (number entities) that represent the structural qualities of your room.

| Input Name                                     | Layman's Explanation                                                                                                                                      | Value Range   | Example by Home Type                                                                      |
|:-----------------------------------------------|:----------------------------------------------------------------------------------------------------------------------------------------------------------|:--------------|:------------------------------------------------------------------------------------------|
| **Exterior Envelope Ratio** ($f_{\text{out}}$) | **Exterior Wall Share.** How much of the room's total interior surface area touches the outside or an unconditioned space (like an attic or cold garage). | $0.0 - 1.0+$  | **0.15:** Interior apartment room. **0.80:** Corner room. **0.95:** Top-floor attic room. |
| **Window Share** ($f_{\text{win}}$)            | **Window Ratio.** The percentage of the exterior wall area that is glass.                                                                                 | $0.0 - 1.0$   | **0.10:** Small basement window. **0.50:** Large picture window/patio door. 🖼️           |
| **Insulation Loss Factor** ($k_{\text{loss}}$) | **Heat Leakage / U-Value.** How poorly insulated your walls and windows are, influencing heat loss in winter. (Higher value = worse insulation).          | $0.05 - 0.30$ | **0.10:** Modern, well-insulated home. **0.25:** Old, uninsulated walls.                  |
| **Solar Gain Factor** ($k_{\text{solar}}$)     | **Solar Heating Power.** How much solar energy actually passes through your windows to heat the room (often called SHGC).                                 | $0.0 - 2.0$   | **0.8:** Standard clear glass. **1.5:** Tilted skylight/very large clear windows.         |

#### ($k_{\text{loss}}$) : Insulation Loss Factor Guidance

| Wall Quality    | Approximate R-Value     | Recommended kloss | expected drop at −30∘C                       |
|-----------------|-------------------------|-------------------|----------------------------------------------|
| Super Insulated | R-40+ (Passive House)   | 0.03 - 0.05       | Wall stays warm        ($19^\circ\text{C}$)  |
| Modern Standard | R-20 (2x6 construction) | 0.05 - 0.08       | Wall is cool            ($17^\circ\text{C}$) |
| Older Insulated | R-12 (2x4, 1980s-90s)   | 0.10 - 0.15       | Wall is cold            ($15^\circ\text{C}$) | 
| Poor / Settled  | R-8 (1950s, gaps)       | 0.15 - 0.20       | Wall is very cold       ($12^\circ\text{C}$) | 
| Uninsulated     | R-4 (Solid Brick/Block) | 0.25 - 0.35       | Wall is freezing        ($8^\circ\text{C}$)  |

### 2. Thermal Smoothing Factor ($\alpha$)

This input is critical for accurately modeling the room's **thermal inertia** (thermal mass).

| Input Name                              | Purpose                                                                                            | Suggested Range                      | Example by Home Type                                                                                                                                                                                                           |
|:----------------------------------------|:---------------------------------------------------------------------------------------------------|:-------------------------------------|:-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Thermal Smoothing Factor** ($\alpha$) | Controls **how quickly** the calculated MRT responds to changes in outside conditions (sun, wind). | $0.05$ (Slowest) to $0.95$ (Fastest) | A North American 1950's wood-frame house has **low thermal mass**. You would use a **higher $\alpha$** (e.g., $0.40$ – $0.60$). A German home with thick masonry walls would use a **lower $\alpha$** (e.g., $0.05$ – $0.20$). |

### 3. Personal Comfort Parameters

To calculate the **PMV (Predicted Mean Vote)**, the integration needs to know about the occupant. These are exposed as number entities so you can automate them (e.g., "Sleep Mode" = higher clothing).

| Input Name           | Definition                       | Typical Values                                                                                                |
|:---------------------|:---------------------------------|:--------------------------------------------------------------------------------------------------------------|
| **Clothing** (clo)   | Thermal insulation of clothes.   | **0.5:** T-shirt/Shorts (Summer). **1.0:** Sweatshirt/Jeans (Winter). **1.5:** Heavy Sweater. **2.5:** Duvet. |
| **Metabolism** (met) | Metabolic rate (activity level). | **0.8:** Sleeping. **1.1:** Typing/Relaxing. **1.5:** Housework/Cooking. **3.0:** Exercise.                   |

### 4. Profile Management

The integration allows you to save a library of custom profiles per room.

* **Profile Selector:** The `select.profile` entity lists all default profiles and any custom profiles you save.
* **Save/Delete:** Use the `text.profile_name` input and the `button.save_profile` / `button.delete_profile` entities to manage your library.
* **"Unsaved Custom Profile" State:** If you select a default profile and manually change any of the four number inputs, the `select.profile` entity will automatically switch its state to **"Unsaved Custom Profile"** (this is your working scratchpad). 💾

---

## 🌬️ Dynamic Comfort Factors ($T_{op}$ Modifiers)

The integration uses several optional inputs to dynamically calculate the effective Air Speed ($v_{\text{air}}$) and adjust the Mean Radiant Temperature ($\text{MRT}$) based on user actions.

### 1. Air Speed ($v_{\text{air}}$) Logic

The final Air Speed ($v_{\text{air}}$) is used to determine the $T_{\text{op}}$ Convective Weighting Factor ($A_{\text{Radiant}}$). The logic uses a **"Max Wins"** approach.

| Input                   | Speed Contribution                                                                                                                                      |
|:------------------------|:--------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Door State Sensor**   | If `on`: **0.8 m/s** (ASHRAE Drafty).                                                                                                                   |
| **Window State Sensor** | If `on`: **0.5 m/s** (ASHRAE Breezy).                                                                                                                   |
| **HVAC Climate Entity** | If `hvac_action` is active (heating/cooling/fan): Uses the **HVAC Airflow Speed** setting (default 0.4 m/s). *Ignored if "Radiant Heating" is enabled.* |
| **Fan Entity**          | Uses mapped speed (`low`: 0.3, `med`: 0.5, `high`: 0.8).                                                                                                |
| **Manual Air Speed**    | Uses the value set by the user (if > 0.1).                                                                                                              |
| **Default**             | **0.1 m/s** (Still Air Baseline).                                                                                                                       |

### 2. Radiant Heating Model

If you have in-floor heating or radiators, the logic adapts.

* **"Is Radiant Heating?" Checkbox:** (In Config/Options Flow). If checked, the integration assumes the heating system warms the *surfaces* (MRT) rather than blowing air.
* **Behavior:** When `heating` is active, the Air Speed remains low, and the **Radiant Boost** is applied based on your **Radiant Surface Temperature** target (e.g., 26°C for a warm floor).

### 3. Shading Factor

* **Shading Entity:** Accepts a Cover, Binary Sensor, or Input Number.
* **Effect:** If the blinds are closed (0%), the Solar Gain term is multiplied by 0.0, stopping solar heating.

---

## 📡 External Data Sources and Fallbacks

The MRT calculation is reactive, meaning it constantly adjusts based on real-time weather conditions.

| Data Point                                 | Source                                                                                   | Use in Calculation                                                                                                                                                                                                                                                      |
|:-------------------------------------------|:-----------------------------------------------------------------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Outdoor Air Temp ($T_{out}$)**           | Optional dedicated sensor / `weather` entity attribute (`temperature`)                   | Calculates the **Heat Loss Term** (how much heat escapes through the walls).                                                                                                                                                                                            |
| **Outdoor Relative Humidity ($RH_{out}$)** | Optional dedicated sensor / `weather` entity attribute (`humidity`)                      | Used to calculate **Australian Apparent Temperature** (AAT). If available, this robust formula replaces standard wind chill to determine the **Effective Outdoor Temperature** that drives wall heat loss. Also used for **Air Density** and **Enthalpy** calculations. |
| **Apparent Temperature**                   | `weather` entity attribute (`apparent_temperature`)                                      | Used as a fallback for effective heat loss if local RH/Wind sensors are missing. If Apparent Temp is **lower** than $T_{out}$ (due to **wind chill**), the lower value is used for a more accurate loss calculation.                                                    |
| **Wind Speed / Wind Gust**                 | Optional dedicated sensor / `weather` entity attribute (`wind_speed`, `wind_gust_speed`) | Calculates the **Wind Effect Factor** (convective loss). Higher wind speed increases the heat loss from the exterior envelope.                                                                                                                                          |
| **Global Solar Radiation**                 | Optional dedicated `sensor` (e.g., `sensor.solar_radiation`)                             | **Preferred source** for solar gain calculation. Bypasses all weather heuristics if available.                                                                                                                                                                          |

---

## 🧪 Advanced Sensors: Moisture, Energy & Comfort

If you configure a **Relative Humidity (RH) Sensor** in the integration settings, the device will automatically calculate and expose several advanced sensors for building health and engineering.

| Sensor                     | Unit    | What it tells you                                                                                 | Best Use Case                                                                                                                                                                                         |
|:---------------------------|:--------|:--------------------------------------------------------------------------------------------------|:------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| **Dew Point** ($T_{dp}$)   | °C      | The temperature at which condensation forms.                                                      | **Mold Prevention.** Keep indoor $T_{dp} < 18°C$ in summer to avoid "stickiness."                                                                                                                     |
| **Frost Point** ($T_{fp}$) | °C      | The temperature at which frost forms (sub-zero dew point).                                        | **Winter Safety.** If this is higher than your window surface temperature, you will get ice buildup.                                                                                                  |
| **Absolute Humidity**      | $g/m^3$ | The actual mass of water vapor in the air. **Attributes:** Air Density ($\rho$) & Humidity Ratio. | **Dehumidifier Control.** Unlike RH, which changes with temperature, this tells you the *actual* moisture load. Check attributes for **Air Density** (fan sizing) and **Mixing Ratio** (HRV balance). |
| **Air Enthalpy** ($h$)     | $kJ/kg$ | The total heat energy (sensible + latent) stored in the air.                                      | **HRV Efficiency.** Tells you if outside air has less *energy* than inside air, even if temperatures look similar.                                                                                    |
| **Humidex**                | °C      | A "feels-like" temperature combining heat and humidity.                                           | **Summer Comfort.** Use this to trigger Air Conditioning. High humidity makes $24°C$ feel like $30°C$.                                                                                                |
| **Thermal Perception**     | Text    | Human-readable status (e.g., "Comfortable", "Sticky").                                            | **Dashboards.** Great for quick-glance status on wall tablets or phone notifications (e.g., "Warning: Heat Stroke Imminent").                                                                         |
| **Thermal Comfort (PMV)**  | Score   | ISO 7730 Comfort Score (-3 to +3).                                                                | **Human-Centric Control.** The gold standard for automating comfort based on activity and clothing.                                                                                                   |
| **Wall Heat Flux** ($q$)   | $W/m^2$ | The density of heat energy leaving the room.                                                      | **Energy Monitoring.** Shows exactly how much energy your wall is leaking right now.                                                                                                                  |
| **Mold Risk**              | %       | Relative humidity at the *wall surface*.                                                          | **Hidden Danger.** Alerts you if the wall surface is wet enough to grow mold, even if the room air seems dry.                                                                                         |

### 🧘 Thermal Comfort (PMV) Sensor
This sensor implements the **Fanger PMV (Predicted Mean Vote)** model. It combines the 4 physics variables ($T_{air}$, $MRT$, $v_{air}$, $RH$) with your 2 personal variables (`clothing`, `metabolism`).

* **Target:** Keep this score between **-0.5** and **+0.5**.
* **Automation Idea:** If PMV < -0.5, turn on heating. If PMV > +0.5, turn on ceiling fans or AC.
* **Why it's better:** It knows that $21^\circ\text{C}$ feels cold if you are sitting still in a t-shirt (PMV -1.0), but hot if you are exercising (PMV +1.5).

### ⚡ Wall Heat Flux & R-Value
The **Heat Flux Sensor** calculates the real-time energy loss through your wall assembly.
* **Attributes:** It exposes an `estimated_r_value` attribute.
* **Usage:** Check this on a cold night. If the sensor estimates **R-10** but you paid for **R-20**, you likely have significant thermal bridging or installation issues.

### 🦠 Mold Risk Sensor (Critical Surface Analysis)

The **Virtual Mold Risk Sensor** uses your specific room parameters to calculate the relative humidity **at the surface of your coldest walls**.

#### How it works
It combines indoor conditions ($T_{air}$, $RH$) with outdoor conditions ($T_{out}$) and your **Insulation Loss Factor** ($k_{loss}$) to model the microclimate at the wall's surface.

#### Risk Levels
The sensor reports the **Surface Relative Humidity** and assigns a risk level icon:

| Surface RH    | Status       | Icon | Meaning                                                                                                                                        |
|:--------------|:-------------|:-----|:-----------------------------------------------------------------------------------------------------------------------------------------------|
| **< 65%** | **Low Risk** | 🛡️  | Safe. No action needed.                                                                                                                        |
| **65% - 80%** | **Warning** | ⚠️   | **Pre-conditions for mold.** The surface is damp enough for spores to settle. You should lower indoor humidity or improve air circulation.     |
| **> 80%** | **CRITICAL** | ☣️   | **Active Growth Potential.** Conditions are perfect for mold germination on your walls. Immediate ventilation or dehumidification is required. |

---

## 🔌 KNX Integration

To send the **Mean Radiant Temperature** or **Operative Temperature** to your KNX system, add the following to your `configuration.yaml`.

**Data Point Type:** The integration outputs values compatible with **DPT 9.001** (Temperature °C).

```yaml
# configuration.yaml

knx:
  expose:
    # Expose MRT to KNX
    - type: temperature        # DPT 9.001
      address: "1/0/10"        # Replace with your KNX Group Address
      entity_id: sensor.living_room_mean_radiant_temperature

    # Expose Operative Temperature (T_op) to KNX
    - type: temperature        # DPT 9.001
      address: "1/0/11"        # Replace with your KNX Group Address
      entity_id: sensor.living_room_operative_temperature