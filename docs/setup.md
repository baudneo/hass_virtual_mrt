The way to use this integration is to have a temp/humidity sensor in each room you want to monitor and then set up 
the integration to read from those sensors.

Example:

- 2 temp/humidity sensors in the main floor living room
  - these 2 sensors are merged using the HASS group/combine/sum helper into a single sensor called "Living Room Avg. temp"
    - You will need to use customize.yaml to set the `device_class: temperature` for this sensor, for some reason the helper does not set it automatically!
- OpenWeatherMap weather integration for the weather entity
- HASS Sun integration setup for the `sun.sun` entity
- A dedicated Global Solar Radiation sensor (can be a template or physical sensor)

- Find the `Virtual MRT / T_op` integration in `Settings > Devices and services > + Add integration` and add an entry for each room you want to monitor:
![Add integration](./assets/int_search.png)
- Configure the integration with the appropriate sensors for each room:
![Integration config](./assets/int_config.png)
- You should see the new devices in your device list:
![Devices list](./assets/device_list.png)
- View the entities in the Entities list:
![Entities list](./assets/device_info.png)
- The profile and thermal inertia smoothing factor entities:
![Profile and smoothing factor entities](./assets/device_info2.png)