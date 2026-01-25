# 🏠 Core Concepts: Layman's Guide

Why does $21^{\circ}\text{C}$ in the winter feel cold, while $21^{\circ}\text{C}$ in the summer feels warm? 

The answer is **Radiant Heat**. Your standard thermostat is lying to you because it only measures the air. Humans feel the temperature of the objects *around* them.

## The Two Temperatures
1. **Mean Radiant Temperature (MRT):** The average surface temperature of the walls, windows, floor, and ceiling. This acts like a "thermal battery" for the room.
2. **Operative Temperature ($T_{op}$):** What you actually feel. It is a weighted average of the Air Temperature and the MRT. **This is the metric you should use to trigger your heating and cooling.**

>[!NOTE]
> **Example:** In winter, your room air might be $21^{\circ}\text{C}$, but if your windows and walls are cold, the MRT might only be $16^{\circ}\text{C}$. The resulting Operative Temperature ($T_{op}$) will be $18.5^{\circ}\text{C}$. You feel cold.

---

## 🏗️ The 4 Room Physical Constants

To accurately calculate your room's thermal battery, the integration needs to know how the room is built. 

You do not need to guess these! The integration includes **Default Profiles** (like "Top Floor Attic", "Basement", "Interior Room") which pre-fill these values. However, you can fine-tune them using the four numeric inputs below.

### 1. Exterior Envelope Ratio ($f_{out}$)
*What percentage of the room's total interior surface area touches the outside?*

* **$0.0 - 0.2$:** An interior hallway or closet (surrounded by warm rooms).
* **$0.4 - 0.5$:** A standard room with one exterior wall.
* **$0.7 - 0.8$:** A corner room with two exterior walls.
* **$0.9 - 1.0$:** A top-floor attic room where the ceiling and walls are all exposed to the cold.

### 2. Window Share ($f_{win}$)
*What percentage of the exterior wall area is made of glass?*

* **$0.0 - 0.1$:** A basement with no windows, or tiny egress windows.
* **$0.2 - 0.3$:** A standard bedroom with one normal window.
* **$0.4 - 0.5$:** A living room with a large picture window or sliding glass door.
* **$0.8 - 1.0$:** A sunroom or conservatory made entirely of glass.

### 3. Insulation Loss Factor ($k_{loss}$)
*How poorly insulated is the room? (Higher = worse insulation).*

* **$0.08 - 0.10$:** Passive house, extremely well insulated (R-40+ walls, triple pane windows).
* **$0.14 - 0.16$:** Modern standard home built to code (R-20 walls, double pane).
* **$0.20 - 0.25$:** Old 1950's home with uninsulated walls and drafty single-pane windows.

### 4. Solar Gain Factor ($k_{solar}$)
*How much solar energy penetrates the windows to heat up the room?*

* **$0.4 - 0.6$:** Basement windows or heavily shaded windows.
* **$0.8 - 1.0$:** Standard clear double-pane windows.
* **$1.2 - 1.4$:** Large, unshaded south-facing windows.
* **$1.5+$:** Tilted skylights or solariums that receive direct perpendicular sunlight.

---

## 🧱 Thermal Mass (Smoothing Factor $\alpha$)

Heavy buildings (brick, concrete) take a long time to heat up and cool down. Light buildings (wood frames) change temperature quickly. 

The **Thermal Smoothing Factor** ($\alpha$) controls this behavior in the calculation:

* **High $\alpha$ (0.50 - 0.95):** Fast reacting. Use for standard wooden structures or mobile homes.
* **Low $\alpha$ (0.05 - 0.20):** Slow reacting. Use for heavy masonry, concrete block homes, or earth-sheltered homes.

>[!IMPORTANT]
> When you change the $\alpha$ setting, the formula updates instantly, but the sensor reading will take time to adapt because it is simulating physical thermal lag.