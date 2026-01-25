# ⚙️ Setup & Configuration Guide

## 1. Configuration Flow

Navigate to **Settings** -> **Devices & Services** -> **Add Integration** and search for "Virtual MRT".

You will be presented with two main choices:
1. **Add a Virtual Room (MRT/$T_{op}$):** Creates the sensors for a specific room.
2. **Add an Aggregator:** Groups existing Virtual Rooms together.

### Step-by-Step: Adding a Room
1. **Name:** Give your room a name (e.g., "Living Room Comfort").
2. **Required Entities:** Link your room's Air Temperature sensor and your local Weather Entity.
3. **Room Profile:** Select the template that best matches your room (e.g., "Corner Room", "Basement").
4. **Orientation:** Select which direction the main windows face (e.g., "South").
5. **Optional Sensors:** Add any external sensors you have. *See the Pro Tips below for hardware advice.*

>[!TIP]
> **💡 Pro Tip 1: Creating a Virtual Global Solar Radiation Sensor**
> For the best calculations, the integration wants a **Total Solar Radiation Sensor (W/m²)**. If you don't have a physical weather station, you can create a highly accurate virtual one using the native **Forecast.Solar** integration.
> 
> 1. Install [Forecast.Solar](https://www.home-assistant.io/integrations/forecast_solar).
> 2. **CRITICAL:** Set `total watt peak power` to `1000` and `declination angle` to `0` (leave azimuth at `180`). This tricks the integration into outputting raw Global Horizontal Irradiation (GHI) in Watts.
> 3. Take the output sensor `Estimated power production - now` (which will say something like `123 W`) and use a HASS helper to change its `device_class` to `irradiation` and `unit_of_measurement` to `W/m²`.
> 4. Use this new template sensor as your `solar_sensor` in this integration!

>[!TIP]
> **💡 Pro Tip 2: Installing Wall Surface Sensors**
> If you are setting up the `wall_surface_sensor` to measure insulation quality or mold risk, proper placement is critical. The sensor must be insulated from the room air. See the **[Hardware Guide in the Psychrometrics doc](./psychrometrics.md#%EF%B8%8F-hardware-guide-wall-surface-sensors)** for the correct installation method.

## 2. Creating Custom Profiles

Once the integration is set up, you can modify the physics of your room on the fly:

1. Click on the Virtual MRT device in Home Assistant.
2. Adjust the number sliders (e.g., increase the Window Share).
3. The Profile drop-down will automatically switch to **"Unsaved Custom Profile"**.
  - This is your 'working scratchpad', it will save the profile as 'Unsaved Custom Profile' until you give it a name and save it 
4. Type a name in the text box and press the **Save Custom Profile** button. 

## 4. Exporting to KNX (Optional)

To send the **Mean Radiant Temperature** or **Operative Temperature** to your KNX system (thermostats, displays, etc.), add the following to your `configuration.yaml`. (Uses Data Point Type 9.001 - Temperature °C).

```yaml
knx:
  expose:
    # Expose Operative Temperature (T_op) to KNX Thermostat
    - type: temperature        
      address: "1/0/11"        # Replace with your KNX Group Address
      entity_id: sensor.living_room_operative_temperature