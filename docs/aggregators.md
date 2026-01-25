# 🏢 Zone Aggregators (Whole House & Floors)

Instead of making one massive device for your whole house, this integration uses a modular approach. You define individual rooms, then group them using an **Aggregator Device**.

Aggregators calculate the **Area-Weighted Average** Operative Temperature. (A 40m² living room has more impact on the average than a 5m² bathroom).

## Mode 1: HVAC Zone Balancing
*(Configured by checking "Is HVAC Zone")*

Groups rooms served by the same thermostat/air-handler.
* **Attributes Generated:** `zone_temp_spread`, `hottest_room`, `coldest_room`.
* **Use Case:** A smart home can use the `zone_temp_spread` attribute to trigger motorized duct dampers. If the spread exceeds $2^{\circ}\text{C}$, the system is "Unbalanced" and the damper to the `hottest_room` can be restricted.

## Mode 2: Multi-Floor (The Stack Effect)
*(Default Mode, generated if you group rooms with different Floor Levels)*

Heat rises. In multi-story homes, the basement is cold, and the top floor is hot. This creates vertical air pressure, known as the **Stack Effect**.

* **Attributes Generated:** `stack_height_m`, `stratification_delta` (Temp at top vs bottom).
* **Stack Effect Pressure (Pa):** Calculates the natural buoyancy pressure (in Pascals) driving air out of your roof and pulling cold makeup air into your basement.
* **Use Case:** Automating HRV/ERV fan speeds. In extreme cold weather, Stack Effect pressure can easily overpower mechanical ventilation. You can use this metric to boost HRV fan speeds to maintain positive air pressure in the home.