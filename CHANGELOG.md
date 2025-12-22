# 0.2.2
- Add an 'Aggregator' class to create floors, whole home, HVAC zones, etc. by combining multiple virtual room devices
  - Each room can be weighted individually to account for room size via its total area config/option entry
  - Aggregator outputs a new virtual device with weighted average temperature 
  - attributes for heat loss in watts based on total area of all combined rooms and their data
  - Can be used to create whole-home comfort monitoring or zone-based HVAC control
- Add update throttling by exposing a 'minimum update interval' config/options entry (default: 30s)
  - Saves DB spam but is still responsive
- Add a 'moisture excess' sensor to help with HRV/ERV boosts
  - shows how much moisture (in g/kg) is above the ideal comfort level for the current temperature
  - helps to decide when to run an HRV/ERV to remove excess humidity from the room
# 0.2.1
- For the ultimate building science nerd: add ISO 7730 / ASHRAE 55 PMV (*Predicted Mean Vote*) and PPD (*Predicted Percentage of Dissatisfied*) thermal comfort indices
  - requires optional room relative humidity sensor input
  - PPD is exposed as an attr of the PMV entity
  - exposes 2 new number input entities to set clothing insulation (Clo) and metabolic rate (Met) for more accurate results
    - use these in automations to adjust based on activity (e.g. higher Met when exercising, lower Clo when wearing lighter clothing)
- 
- Add "Wall Heat Flux" sensor output
  - shows estimated heat flux through the monitored wall in W/m²
  - positive values indicate heat loss from the room, negative values indicate heat gain into the room
- Added psychrometric data via an optional room relative humidity input sensor
  - frost and dew points, actual humidity, humidex, thermal comfort, mold risk, air enthalpy
- Added an auto modeling calibration output via an optional 'wall surface temperature' sensor
  - sensor that shows a calibrated K_loss value, no more guessing your insulation loss value!
  - see readme on sensor install/location tips for best results
  - since kloss is a mostly static number, once you get a fairly stable nighttime reading you can set that as your fixed kloss in the integration config to improve accuracy and move the sensor to another room.
- Expanded dedicated sensor inputs for users with a local weather station or sensors
  - outdoor temp/rel. humidity, wind speed, atmospheric pressure
- remove forgotten 2.5 thermal bridge multiplier in mold risk sensor logic
# 0.2.0
- Added using sun azimuth to calculate the **Solar Angle of Incidence Factor**
  - impacts how the sun hits the window
- Convective weighting using ASHRAE simplified coefficients (hr, hc)
  - adjust the rooms estimated air speed in m/s.
  - adds logic for monitoring windows, doors, fans and also a climate entity (if forced air)
- Config/option bool to tell the integration if your optional climate entity controls a forced air system or a radiant heat system.
- MRT radiant boost based on radiant climate entity and the radiant system target temperature
- Shade/Cover/Blind solar factor
  - Monitor a sensor that tells us how much of the window is covered 
# 0.1.0
Initial release with basic functionality.