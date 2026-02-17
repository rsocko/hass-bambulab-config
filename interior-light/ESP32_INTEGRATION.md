# ESP32 Screen Integration Guide

This guide explains how to add an interior light reset button to an ESP32 screen mounted on your Bambu Lab printer.

## Overview

You can integrate the interior light reset functionality with an ESP32 display using ESPHome. This allows you to have a physical touchscreen button directly on your printer.

## Prerequisites

- ESP32 device with display (e.g., ESP32 with ILI9341, ST7789, or similar)
- ESPHome installed and configured
- ESP32 connected to Home Assistant
- Interior light reset script installed (see main README.md)

## ESPHome Configuration

### Basic Button Implementation

Add this to your ESPHome YAML configuration:

```yaml
# ESPHome configuration for Bambu Lab printer display
esphome:
  name: bambu_printer_display
  platform: ESP32
  board: esp32dev

# Enable Home Assistant API
api:
  encryption:
    key: "your_encryption_key_here"

# WiFi configuration
wifi:
  ssid: "YourSSID"
  password: "YourPassword"

# Display configuration (example with ILI9341)
display:
  - platform: ili9341
    model: TFT 2.4
    cs_pin: GPIO15
    dc_pin: GPIO2
    rotation: 90
    lambda: |-
      // Draw printer status
      it.print(10, 10, id(font_large), "Bambu Lab P1S");
      
      // Draw current print status (with safety check to prevent crashes)
      // Always check has_state() before accessing state on text sensors
      // to avoid crashes during startup or network issues
      it.printf(10, 40, id(font_medium), "Status: %s", 
        id(printer_status).has_state() ? id(printer_status).state.c_str() : "Unknown");
      
      // Draw light reset button
      if (id(touchscreen).touched()) {
        auto touch = id(touchscreen).get_touch();
        // Button area: 10,200 to 230,260 (220x60 pixels)
        if (touch.x > 10 && touch.x < 230 && 
            touch.y > 200 && touch.y < 260) {
          // Button pressed - draw highlighted
          it.filled_rectangle(10, 200, 220, 60, COLOR_ON);
          it.print(120, 230, id(font_medium), COLOR_OFF, TextAlign::CENTER, "RESET LIGHT");
        } else {
          // Button normal state
          it.rectangle(10, 200, 220, 60, COLOR_ON);
          it.print(120, 230, id(font_medium), COLOR_ON, TextAlign::CENTER, "RESET LIGHT");
        }
      } else {
        // Button normal state
        it.rectangle(10, 200, 220, 60, COLOR_ON);
        it.print(120, 230, id(font_medium), COLOR_ON, TextAlign::CENTER, "RESET LIGHT");
      }

# Touchscreen (if using resistive touch)
touchscreen:
  platform: xpt2046
  id: touchscreen
  cs_pin: GPIO14
  on_touch:
    - lambda: |-
        auto touch = id(touchscreen).get_touch();
        // Check if button area was touched
        if (touch.x > 10 && touch.x < 230 && 
            touch.y > 200 && touch.y < 260) {
          // Call the Home Assistant script
          id(reset_light_button).press();
        }

# Button to trigger Home Assistant script
button:
  - platform: template
    id: reset_light_button
    name: "Reset Interior Light"
    on_press:
      - homeassistant.service:
          service: script.reset_interior_light_to_white

# Import printer status from Home Assistant
text_sensor:
  - platform: homeassistant
    id: printer_status
    entity_id: sensor.ntk_ryansoffice_3dprinter_print_status

# Fonts
font:
  - file: "fonts/arial.ttf"
    id: font_large
    size: 24
  - file: "fonts/arial.ttf"
    id: font_medium
    size: 18
  - file: "fonts/arial.ttf"
    id: font_small
    size: 14

# Colors
color:
  - id: COLOR_ON
    red: 100%
    green: 100%
    blue: 100%
  - id: COLOR_OFF
    red: 0%
    green: 0%
    blue: 0%
```

### Using LVGL (Advanced)

For more sophisticated interfaces, use LVGL:

```yaml
# LVGL configuration
lvgl:
  displays:
    - display_id: my_display
  
  # Define the button
  pages:
    - id: main_page
      widgets:
        # Printer status label
        - label:
            id: status_label
            text: "Printer Status: Idle"
            x: 10
            y: 10
        
        # Reset light button
        - button:
            id: reset_light_btn
            x: 10
            y: 200
            width: 220
            height: 60
            widgets:
              - label:
                  text: "💡 Reset Light"
                  align: CENTER
            on_click:
              - homeassistant.service:
                  service: script.reset_interior_light_to_white
              - label.set_text:
                  id: status_label
                  text: "Light Reset!"
              - delay: 2s
              - label.set_text:
                  id: status_label
                  text: "Printer Status: Idle"
        
        # Additional printer info
        - label:
            id: progress_label
            text: "Progress: 0%"
            x: 10
            y: 100

# Update status from Home Assistant
text_sensor:
  - platform: homeassistant
    id: printer_status
    entity_id: sensor.ntk_ryansoffice_3dprinter_print_status
    on_value:
      - lvgl.label.update:
          id: status_label
          text: !lambda 'return "Status: " + x;'
  
  - platform: homeassistant
    id: print_progress
    entity_id: sensor.ntk_ryansoffice_3dprinter_print_progress
    on_value:
      - lvgl.label.update:
          id: progress_label
          text: !lambda 'return "Progress: " + x + "%";'
```

## Button Variations

### Simple Binary Button (No Display)

If you just want a physical button without a display:

```yaml
binary_sensor:
  - platform: gpio
    pin:
      number: GPIO0
      mode: INPUT_PULLUP
      inverted: true
    name: "Reset Light Button"
    on_press:
      - homeassistant.service:
          service: script.reset_interior_light_to_white
      - logger.log: "Interior light reset button pressed"
```

### Button with LED Feedback

Add an LED that lights up when button is pressed:

```yaml
binary_sensor:
  - platform: gpio
    pin:
      number: GPIO0
      mode: INPUT_PULLUP
      inverted: true
    name: "Reset Light Button"
    on_press:
      - switch.turn_on: feedback_led
      - homeassistant.service:
          service: script.reset_interior_light_to_white
      - delay: 1s
      - switch.turn_off: feedback_led

switch:
  - platform: gpio
    pin: GPIO2
    id: feedback_led
    name: "Button Feedback LED"
```

### Multi-Function Button (Long Press)

Different actions for tap vs. hold:

```yaml
binary_sensor:
  - platform: gpio
    pin:
      number: GPIO0
      mode: INPUT_PULLUP
      inverted: true
    name: "Light Control Button"
    on_click:
      # Short press: Reset to white
      - min_length: 50ms
        max_length: 1000ms
        then:
          - homeassistant.service:
              service: script.reset_interior_light_to_white
          - logger.log: "Short press - Reset to white"
    
    on_multi_click:
      # Long press: Turn off
      - timing:
          - ON for at least 2s
        then:
          - homeassistant.service:
              service: light.turn_off
              data:
                entity_id: light.magwled
          - logger.log: "Long press - Turn off light"
```

## Full Dashboard Example

Complete ESP32 dashboard with multiple controls:

```yaml
display:
  - platform: ili9341
    model: TFT 2.4
    cs_pin: GPIO15
    dc_pin: GPIO2
    rotation: 90
    update_interval: 1s
    lambda: |-
      // Header
      it.filled_rectangle(0, 0, 320, 40, COLOR_HEADER);
      it.print(160, 20, id(font_large), COLOR_TEXT, TextAlign::CENTER, "Bambu Lab Control");
      
      // Printer status (with safety checks to prevent crashes)
      it.printf(10, 50, id(font_medium), "Status: %s", 
        id(printer_status).has_state() ? id(printer_status).state.c_str() : "Unknown");
      
      it.printf(10, 75, id(font_medium), "Progress: %s%%", 
        id(print_progress).has_state() ? id(print_progress).state.c_str() : "0");
      
      // Light status
      auto light_brightness = id(light_brightness).state;
      it.printf(10, 100, id(font_medium), "Light: %.0f%%", light_brightness);
      
      // Buttons
      // Button 1: Reset Light
      bool btn1_pressed = false;
      if (id(touchscreen).touched()) {
        auto touch = id(touchscreen).get_touch();
        if (touch.x > 10 && touch.x < 150 && touch.y > 150 && touch.y < 210) {
          btn1_pressed = true;
        }
      }
      
      auto btn1_color = btn1_pressed ? COLOR_BUTTON_PRESSED : COLOR_BUTTON;
      it.filled_rectangle(10, 150, 140, 60, btn1_color);
      it.print(80, 180, id(font_medium), COLOR_TEXT, TextAlign::CENTER, "Reset");
      it.print(80, 200, id(font_medium), COLOR_TEXT, TextAlign::CENTER, "Light");
      
      // Button 2: Pause Print
      bool btn2_pressed = false;
      if (id(touchscreen).touched()) {
        auto touch = id(touchscreen).get_touch();
        if (touch.x > 170 && touch.x < 310 && touch.y > 150 && touch.y < 210) {
          btn2_pressed = true;
        }
      }
      
      auto btn2_color = btn2_pressed ? COLOR_BUTTON_PRESSED : COLOR_BUTTON;
      it.filled_rectangle(170, 150, 140, 60, btn2_color);
      it.print(240, 180, id(font_medium), COLOR_TEXT, TextAlign::CENTER, "Pause");
      it.print(240, 200, id(font_medium), COLOR_TEXT, TextAlign::CENTER, "Print");

touchscreen:
  platform: xpt2046
  id: touchscreen
  cs_pin: GPIO14
  on_touch:
    - lambda: |-
        auto touch = id(touchscreen).get_touch();
        
        // Reset light button
        if (touch.x > 10 && touch.x < 150 && touch.y > 150 && touch.y < 210) {
          id(ha_reset_light).execute();
        }
        
        // Pause button
        if (touch.x > 170 && touch.x < 310 && touch.y > 150 && touch.y < 210) {
          id(ha_pause_print).execute();
        }

script:
  - id: ha_reset_light
    then:
      - homeassistant.service:
          service: script.reset_interior_light_to_white
      - logger.log: "Reset light command sent"
  
  - id: ha_pause_print
    then:
      - homeassistant.service:
          service: button.press
          data:
            entity_id: button.ntk_ryansoffice_3dprinter_pause
      - logger.log: "Pause print command sent"

sensor:
  - platform: homeassistant
    id: light_brightness
    entity_id: light.magwled
    attribute: brightness

text_sensor:
  - platform: homeassistant
    id: printer_status
    entity_id: sensor.ntk_ryansoffice_3dprinter_print_status
  
  - platform: homeassistant
    id: print_progress
    entity_id: sensor.ntk_ryansoffice_3dprinter_print_progress

color:
  - id: COLOR_HEADER
    red: 0%
    green: 50%
    blue: 100%
  - id: COLOR_BUTTON
    red: 30%
    green: 30%
    blue: 30%
  - id: COLOR_BUTTON_PRESSED
    red: 50%
    green: 50%
    blue: 50%
  - id: COLOR_TEXT
    red: 100%
    green: 100%
    blue: 100%
```

## Troubleshooting

### Button Not Responding

1. Check ESPHome logs:
```bash
esphome logs bambu_printer_display.yaml
```

2. Verify Home Assistant API connection:
```yaml
logger:
  level: DEBUG
```

3. Test button press in logs:
```yaml
on_press:
  - logger.log: "Button pressed!"
  - homeassistant.service:
      service: script.reset_interior_light_to_white
```

### Touchscreen Calibration

If touch coordinates are off, calibrate:

```yaml
touchscreen:
  platform: xpt2046
  calibration:
    x_min: 300
    x_max: 3900
    y_min: 300
    y_max: 3900
  swap_xy: false
  mirror_x: false
  mirror_y: false
```

### Display Not Updating

Increase update interval or force refresh:

```yaml
display:
  update_interval: 500ms  # Update twice per second
```

## Hardware Recommendations

### Displays
- **ILI9341** (2.4" - 3.2") - Good balance of size and performance
- **ST7789** (1.3" - 2.0") - Compact option
- **ILI9488** (3.5") - Larger display for more controls

### ESP32 Boards
- **ESP32-DevKitC** - Standard development board
- **ESP32-WROVER** - More RAM for complex displays
- **TTGO T-Display** - Built-in display option

### Mounting
- 3D print a case and mount for the ESP32 + display
- Mount directly on printer frame or AMS unit
- Use magnetic or adhesive mounting for easy removal

## Next Steps

1. Flash ESPHome configuration to ESP32
2. Add device to Home Assistant
3. Test button functionality
4. Customize display layout
5. Add additional controls (temperature, fans, etc.)

## Resources

- [ESPHome Documentation](https://esphome.io/)
- [LVGL Graphics Library](https://lvgl.io/)
- [ESP32 Touchscreen Guide](https://esphome.io/components/touchscreen/)
- [Home Assistant Service Calls](https://esphome.io/components/api.html#homeassistant-service-action)

---

**Pro Tip:** Start with a simple button configuration and gradually add more features as you become comfortable with ESPHome!
