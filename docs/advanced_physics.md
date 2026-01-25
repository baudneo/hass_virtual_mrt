# 🔬 Advanced Physics & Formulas

This integration continuously balances the heat loss through the building envelope against the heat gain from the sun and internal HVAC systems. It relies heavily on external data and uses a cascading fallback system if physical sensors are unavailable.

## 1. External Data Sources and Fallbacks

The integration intelligently hunts for the most accurate data available, falling back to HASS defaults if you don't supply dedicated sensors.

| Data Point | Primary Source (Highest Priority) | Fallback Source | Use in Calculation |
|:---|:---|:---|:---|
| **Outdoor Air Temp ($T_{out}$)** | Dedicated Sensor | `weather` entity attribute (`temperature`) | Calculates the **Heat Loss Term** (how much heat escapes through the walls). |
| **Wind Speed / Gust** | Dedicated Sensor | `weather` entity attribute (`wind_speed`) | Calculates convective loss on the exterior envelope. High wind strips heat away faster. |
| **Sun Elevation & Azimuth** | `sun.sun` (Native) | N/A | Calculates the **Solar Angle of Incidence Factor**. Sun hitting a window at 90° imparts more energy than sun grazing it at 15°. |
| **Global Solar Radiation** | Dedicated Sensor (W/m²) | Cloud Cover / `sun.sun` heuristics | The raw fuel for solar heating. Capped at $1000 \text{ W/m}^2$ if using the weather/cloud fallback. |

## 2. Dynamic Heat Loss: The "Apparent Temperature" Factor

Building heat loss is driven by the exterior boundary layer. The integration does not just use the outdoor dry-bulb temperature; it calculates the **Apparent Temperature (Wind Chill)**.

1. It checks the `apparent_temperature` attribute from your weather entity.
2. If Apparent Temp is **lower** than the actual Outdoor Temp ($T_{out}$) due to wind chill, the integration uses the lower value. 

*Effect:* If a 30km/h wind hits your house at $0^{\circ}\text{C}$, the effective exterior temperature pulling heat out of your walls is actually $-6^{\circ}\text{C}$. This makes your interior surfaces colder than standard thermostats predict.

## 3. Solar Gain Modifiers & Shading Logic

Once the baseline solar energy is determined, it is modified by physical obstructions:

1. **Shading Entity:** Accepts a Cover, Binary Sensor, or Input Number. 
   * If a blind is 50% open, solar gain is multiplied by 0.5.
   * If a binary sensor is `off` (blinds closed), solar gain is 0.0.
2. **Rain Penalty:** If a `precipitation_sensor` detects rain (rate > 0), or if the weather condition is `rainy`/`snowy`/`hail`, a **Rain Multiplier** of $0.4$ is applied. This simulates dark storm clouds reducing radiation transmission.
3. **Daylight Factor:** Used as a multiplier for solar gain when the sun is below the horizon to account for diffuse sky radiation.

## 4. Air Speed ($v_{air}$) Logic

Air speed determines how much weight is given to Air Temp vs MRT when calculating Operative Temp. The integration dynamically shifts this using a **"Max Wins"** priority list:

| Trigger | Applied Speed | Notes |
|:---|:---|:---|
| **Door Open** | 0.8 m/s | Heavily biases towards Air Temp. |
| **Window Open** | 0.5 m/s | |
| **HVAC Active** | Configurable (Default 0.4 m/s) | Automatically triggers when climate entity is `heating`/`cooling`/`fan`. |
| **Local Fan** | Mapped by state | `low`: 0.3, `medium`/`auto`/`on`: 0.5, `high`: 0.8 |
| **Still Air** | 0.1 m/s | Baseline |

>[!NOTE]
> The optional climate entity is only used to detect if the HVAC system is actively heating, cooling, or blowing air. It does not read or modify the target temperature.

## 5. Radiant Heating Model

If **"Is Radiant Heating?"** is enabled in options, the HVAC air speed logic is bypassed (set to 0.1 m/s). Instead, a **Radiant Boost** is applied to the MRT when the thermostat says `heating`.

The speed of this boost is governed by the **Radiant System Type**:
* **High Mass (Concrete Slab):** Slow response, large thermal lag.
* **Low Mass (Baseboard Radiator):** Fast response, instant heat.