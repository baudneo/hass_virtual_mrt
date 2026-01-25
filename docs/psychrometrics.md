# 💧 Psychrometrics, Comfort & Mold

Air temperature is only half the battle. By adding a **Relative Humidity (RH) Sensor** to your room configuration, the integration unlocks 7 advanced thermodynamic sensors.

>[!IMPORTANT]
> **Technical Note:** All psychrometric values (Dew Point, Humidex, Enthalpy) are calculated using the **Air Temperature** ($T_{air}$), not the Operative Temperature ($T_{op}$). This is because humidity properties are physically bound to the air mass itself, not the radiant environment.

## 🦠 The Microclimate: Mold Risk Sensor

Standard mold sensors warn you if room humidity is >60%. **This is dangerously misleading in cold climates.** Mold doesn't start in the air; it starts on the coldest surface in the room (corners, windows, thermal bridges).

This integration calculates the **Surface Relative Humidity**:
1. It uses your $k_{loss}$ setting and Outdoor Temp to estimate how cold your wall is.
2. It calculates the resulting RH at that specific boundary layer.
3. It alerts you if the **wall surface** crosses 80% RH, even if your room air feels perfectly dry.

#### Risk Levels
| Surface RH    | Status       | Action Required |
|:--------------|:-------------|:----------------|
| **< 65%** | **Low Risk** | None. Safe. |
| **65% - 80%** | **Warning** | The surface is damp enough for spores to settle. Lower indoor humidity or improve air circulation. |
| **> 80%** | **CRITICAL** | **Active Growth Potential.** Conditions are perfect for mold germination on your walls. Immediate ventilation required. |

>[!TIP]
> **Diagnostic Mode:** If you tape a physical temperature/humidity sensor to your exterior wall and input it as the `wall_surface_sensor` and `calibration_rh_sensor`, the integration will switch from "estimates" to "measurements." It will then generate an **Estimated Insulation Factor** sensor to tell you the *actual* R-Value and air seal quality of your wall.

### 🛠️ Hardware Guide: Wall Surface Sensors

If you want to use the **Diagnostic Mode** to calculate your actual wall R-Value or measure real mold risk, you need to properly install a sensor on an exterior wall. Measuring surface temperature is tricky because the room air will try to influence the sensor.

#### 1. What type of sensor to use?
You need a small, wireless sensor that measures both Temperature and Humidity. 
* **Best Options (Zigbee/BLE):** Small sensors like the **Aqara Temperature/Humidity Sensor**, **Xiaomi Mijia (LYWSD03MMC)**, or **SwitchBot Meter**. They are cheap, accurate, and small enough to mount flush against a wall.
* **Wired Probes (Advanced):** A Sensiron SHT3/4 series sensor would work very well


#### 2. Where to install it?
Pick the **worst-performing exterior wall** in the room. This is usually:
* A north-facing wall (no solar gain).
* A corner where two exterior walls meet (geometric thermal bridge).
* **Behind furniture** (like a couch or wardrobe). This is highly recommended! The lack of airflow behind furniture makes the wall colder, which is exactly where mold is most likely to grow.
* **AVOID:** Direct sunlight, interior walls, and areas directly above radiators or near HVAC vents.

#### 3. How to mount it (The "Insulated Box" Method)
To get the true surface conditions, the sensor needs to be protected from the warm room air.
1. Place the sensor flat against the wall. Ensure the humidity grill is facing the wall surface or the tiny air pocket right next to it.
2. **Insulate the back:** Tape a small piece of Styrofoam, XPS insulation board, or thick foam tape over the back of the sensor. 
3. This creates a tiny trapped air pocket against the wall. The sensor will now read the true microclimate of the wall surface rather than the ambient room air.

## ⚡ Energy Savings: Enthalpy & Free Cooling

Enthalpy ($kJ/kg$) measures the **Total Heat Energy** stored in the air, combining sensible heat (temperature) and latent heat (humidity). 

* **The Problem:** It is 24°C outside and 26°C inside. You open the windows to cool down. But outside humidity is 80%, while inside is 40%. You just flooded your house with high-energy moist air, and your AC will have to work overtime to remove it.
* **The Solution:** The **Air Enthalpy Sensor** compares indoor vs. outdoor energy. If the `enthalpy_difference` is positive, outside air is cheaper to condition. This lets you automate "Free Cooling" window prompts or HRV Economizer bypass modes.

## 🌡️ PMV & Thermal Comfort

**Predicted Mean Vote (PMV)** is the ISO 7730 standard for comfort. It uses 6 variables to predict if a human feels hot or cold on a scale of -3 (Cold) to +3 (Hot).

* **Inputs Needed:** $T_{air}$, $T_{mrt}$, $v_{air}$, $RH$.
* **Personal Inputs:** Configured via numeric sliders for Clothing Level ($clo$) and Metabolic Rate ($met$).
* **Output:** A numeric PMV value and a text category ("Comfortable", "Slightly Cool", "Hot").