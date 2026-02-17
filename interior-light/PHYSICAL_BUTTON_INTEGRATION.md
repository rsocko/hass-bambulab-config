# Physical Button Integration Guide

This guide explains how to add a physical button by your Bambu Lab printer to reset the interior light to white.

## Overview

There are several ways to integrate a physical button to control your interior light:

1. **ESPHome Button** - Connect to ESP32/ESP8266 device
2. **Zigbee Button** - Use off-the-shelf Zigbee button
3. **Z-Wave Button** - Use Z-Wave smart button
4. **WiFi Button** - Use Shelly or similar WiFi button
5. **Wired Button** - Direct GPIO connection to Home Assistant device

## Option 1: ESPHome Button (Recommended)

### What You Need
- ESP32 or ESP8266 board ($3-10)
- Momentary push button ($1-5)
- Optional: LED for feedback
- USB power supply or 5V power
- Wires and enclosure

### Hardware Setup

**Simple Wiring:**
```
ESP32/ESP8266          Button
    GPIO0 ------------ Pin 1
    GND -------------- Pin 2
```

**With LED Feedback:**
```
ESP32/ESP8266          Button          LED          Resistor
    GPIO0 ------------ Pin 1
    GPIO2 ---[220Ω]--- (Anode) ------- (Cathode) --- GND
    GND -------------- Pin 2
```

### ESPHome Configuration

Create `printer_button.yaml`:

```yaml
esphome:
  name: printer_button
  platform: ESP32  # or ESP8266
  board: esp32dev   # or nodemcuv2 for ESP8266

wifi:
  ssid: "YourSSID"
  password: "YourPassword"

# Enable Home Assistant API
api:
  encryption:
    key: "your_encryption_key_here"

ota:
  password: "your_ota_password"

# Status LED (optional)
status_led:
  pin:
    number: GPIO2
    inverted: false

# Physical button
binary_sensor:
  - platform: gpio
    pin:
      number: GPIO0
      mode: INPUT_PULLUP
      inverted: true
    name: "Interior Light Reset Button"
    id: reset_button
    
    # Single press: Reset to white
    on_press:
      - logger.log: "Button pressed - resetting light"
      - homeassistant.service:
          service: script.reset_interior_light_to_white
      
      # Optional: Blink LED for feedback
      - if:
          condition:
            lambda: 'return id(feedback_led).state;'
          then:
            - switch.turn_off: feedback_led
            - delay: 100ms
            - switch.turn_on: feedback_led
            - delay: 100ms
            - switch.turn_off: feedback_led
            - delay: 100ms
            - switch.turn_on: feedback_led

# Feedback LED
switch:
  - platform: gpio
    pin: GPIO2
    id: feedback_led
    name: "Button Feedback LED"
    restore_mode: ALWAYS_ON
```

### Flash to Device

1. Install ESPHome:
```bash
pip install esphome
```

2. Compile and upload:
```bash
esphome run printer_button.yaml
```

3. Add to Home Assistant (auto-discovered)

---

## Option 2: Zigbee Button

### Recommended Buttons

**IKEA Tradfri Shortcut Button**
- Single button, simple
- Battery powered (2x AAA)
- ~$7-10
- Good battery life (1+ years)

**Aqara Wireless Mini Switch**
- Single button, compact
- Battery powered (CR2032)
- ~$12-15
- Very long battery life (2+ years)

**Philips Hue Dimmer Switch**
- 4 buttons, versatile
- Battery powered (2x AAA)
- ~$20-25
- Can assign different actions to each button

### Setup

1. **Pair with Zigbee Coordinator** (Zigbee2MQTT, ZHA, or deCONZ)

2. **Create Automation** in Home Assistant:

```yaml
automation:
  - id: physical_button_reset_light
    alias: "Physical Button - Reset Interior Light"
    description: "Reset light when physical Zigbee button is pressed"
    mode: single
    
    trigger:
      # For IKEA button
      - platform: event
        event_type: zha_event
        event_data:
          device_id: YOUR_BUTTON_DEVICE_ID
          command: "toggle"
      
      # Or for Aqara button
      # - platform: mqtt
      #   topic: "zigbee2mqtt/bedroom_button/action"
      #   payload: "single"
    
    action:
      - service: script.reset_interior_light_to_white
        data: {}
```

3. **Find Device ID:**
   - Settings → Devices & Services
   - Click on Zigbee integration
   - Find your button device
   - Copy device ID from URL

---

## Option 3: Z-Wave Button

### Recommended Buttons

**Aeotec NanoMote Quad**
- 4 programmable buttons
- Battery powered (CR2450)
- ~$40-50
- Scene control capable

**Hank One-Key Scene Controller**
- Single button with LED
- Battery powered
- ~$25-30
- Simple and reliable

### Setup

1. **Include Z-Wave Button** in your Z-Wave network

2. **Create Automation:**

```yaml
automation:
  - id: zwave_button_reset_light
    alias: "Z-Wave Button - Reset Interior Light"
    description: "Reset light on Z-Wave button press"
    mode: single
    
    trigger:
      - platform: event
        event_type: zwave_js_value_notification
        event_data:
          node_id: YOUR_NODE_ID
          property_key: "001"  # Button 1
          value: "KeyPressed"
    
    action:
      - service: script.reset_interior_light_to_white
        data: {}
```

---

## Option 4: WiFi Button (Shelly)

### Shelly Button1

Perfect for this use case:
- WiFi connected
- Battery powered (coin cell, 1.5+ years)
- ~$15-20
- Very compact

### Setup

1. **Configure Shelly Button1:**
   - Connect to Shelly WiFi
   - Configure to connect to your network
   - Add to Home Assistant (auto-discovered)

2. **Create Automation:**

```yaml
automation:
  - id: shelly_button_reset_light
    alias: "Shelly Button - Reset Interior Light"
    description: "Reset light when Shelly button is pressed"
    mode: single
    
    trigger:
      - platform: state
        entity_id: binary_sensor.shelly_button1_input
        to: "on"
    
    action:
      - service: script.reset_interior_light_to_white
        data: {}
```

---

## Option 5: Wired Button to Raspberry Pi

If Home Assistant runs on Raspberry Pi with accessible GPIO:

### Hardware Setup

```
Raspberry Pi          Button
    GPIO17 ---------- Pin 1
    GND ------------- Pin 2
```

### Configuration

Add to `configuration.yaml`:

```yaml
binary_sensor:
  - platform: rpi_gpio
    ports:
      17: Interior Light Button

automation:
  - id: rpi_button_reset_light
    alias: "RPi Button - Reset Interior Light"
    description: "Reset light when RPi GPIO button is pressed"
    mode: single
    
    trigger:
      - platform: state
        entity_id: binary_sensor.interior_light_button
        to: "on"
    
    action:
      - service: script.reset_interior_light_to_white
        data: {}
```

---

## Multi-Function Button Examples

### Short Press vs. Long Press

```yaml
automation:
  # Short press: Reset to white
  - id: button_short_press
    alias: "Button Short Press - Reset to White"
    trigger:
      - platform: event
        event_type: zha_event
        event_data:
          device_id: YOUR_BUTTON_DEVICE_ID
          command: "single"
    action:
      - service: script.reset_interior_light_to_white
  
  # Long press: Turn off
  - id: button_long_press
    alias: "Button Long Press - Turn Off Light"
    trigger:
      - platform: event
        event_type: zha_event
        event_data:
          device_id: YOUR_BUTTON_DEVICE_ID
          command: "hold"
    action:
      - service: light.turn_off
        target:
          entity_id: light.magwled
```

### Double Press for Different Action

```yaml
automation:
  # Single press: Reset to white
  - id: button_single_press
    alias: "Button Single - Reset White"
    trigger:
      - platform: event
        event_type: zha_event
        event_data:
          device_id: YOUR_BUTTON_DEVICE_ID
          command: "single"
    action:
      - service: script.reset_interior_light_to_white
  
  # Double press: Photo mode
  - id: button_double_press
    alias: "Button Double - Photo Mode"
    trigger:
      - platform: event
        event_type: zha_event
        event_data:
          device_id: YOUR_BUTTON_DEVICE_ID
          command: "double"
    action:
      - service: script.interior_light_photo_mode
```

### Multi-Button Controller

Use a 4-button controller for different presets:

```yaml
automation:
  # Button 1: Bright white
  - id: button_1_bright
    alias: "Button 1 - Bright White"
    trigger:
      - platform: event
        event_type: zha_event
        event_data:
          device_id: YOUR_DEVICE_ID
          command: "on"
          args: [1]  # Button 1
    action:
      - service: script.reset_interior_light_to_white
  
  # Button 2: Warm white
  - id: button_2_warm
    alias: "Button 2 - Warm White"
    trigger:
      - platform: event
        event_type: zha_event
        event_data:
          device_id: YOUR_DEVICE_ID
          command: "on"
          args: [2]  # Button 2
    action:
      - service: script.interior_light_warm_white
  
  # Button 3: Photo mode
  - id: button_3_photo
    alias: "Button 3 - Photo Mode"
    trigger:
      - platform: event
        event_type: zha_event
        event_data:
          device_id: YOUR_DEVICE_ID
          command: "on"
          args: [3]  # Button 3
    action:
      - service: script.interior_light_photo_mode
  
  # Button 4: Turn off
  - id: button_4_off
    alias: "Button 4 - Turn Off"
    trigger:
      - platform: event
        event_type: zha_event
        event_data:
          device_id: YOUR_DEVICE_ID
          command: "on"
          args: [4]  # Button 4
    action:
      - service: light.turn_off
        target:
          entity_id: light.magwled
```

---

## Button Mounting Ideas

### 3D Printed Enclosure

Design considerations:
- Small enclosure for ESP32 + button
- Mount point for printer frame or desk
- LED visibility hole
- USB power cable routing

STL files: (link to Thingiverse/Printables when created)

### Adhesive Mounting

- Use 3M VHB tape for permanent mounting
- Command strips for removable mounting
- Magnetic mounting on metal surfaces

### Desk-Mount Options

- Small project box on desk near printer
- Under-desk mounting bracket
- Incorporated into custom printer desk setup

---

## Troubleshooting

### Button Not Triggering

1. **Check battery** (for wireless buttons)
2. **Verify pairing** with coordinator
3. **Check Home Assistant logs** for events
4. **Test with Developer Tools** → Events → Listen for device events

### Delayed Response

1. Wireless buttons have ~100-500ms delay (normal)
2. Check WiFi/Zigbee signal strength
3. Move coordinator closer if needed

### Accidental Presses

1. Use button debouncing in ESPHome:
```yaml
binary_sensor:
  - platform: gpio
    pin: GPIO0
    filters:
      - delayed_on: 50ms  # Debounce
```

2. Add confirmation in automation:
```yaml
action:
  - service: persistent_notification.create
    data:
      message: "Resetting interior light..."
  - service: script.reset_interior_light_to_white
```

---

## Cost Comparison

| Option | Hardware Cost | Difficulty | Battery Life | Range |
|--------|--------------|------------|--------------|-------|
| ESPHome Button | $5-15 | Medium | Wired | WiFi range |
| Zigbee Button | $10-25 | Easy | 1-2 years | Good (mesh) |
| Z-Wave Button | $25-50 | Easy | 1-2 years | Excellent (mesh) |
| Shelly Button | $15-20 | Easy | 1.5+ years | WiFi range |
| RPi GPIO | $2-5 | Medium | Wired | N/A |

---

## Recommended Setup

**Best Overall:** 
- **IKEA Tradfri Button** + **Zigbee2MQTT/ZHA**
- Cheap, reliable, long battery life
- Easy to set up
- Can add more buttons easily

**Most Flexible:**
- **ESP32 + ESPHome**
- Complete control over functionality
- Can add LED feedback, display, etc.
- Wired (always available)

**Simplest:**
- **Shelly Button1**
- Just works out of the box
- Battery powered
- WiFi (no hub needed)

---

## Next Steps

1. Choose your button type
2. Order hardware
3. Follow setup instructions for your chosen option
4. Install and test
5. Mount near printer for easy access

---

## Resources

- [ESPHome Button Component](https://esphome.io/components/binary_sensor/gpio.html)
- [Zigbee2MQTT Supported Devices](https://www.zigbee2mqtt.io/supported-devices/)
- [ZHA Device Support](https://zigbee.blakadder.com/)
- [Shelly Documentation](https://shelly-api-docs.shelly.cloud/)

---

**Pro Tip:** Start with a single button for the reset function. Once working, you can expand to multi-button controllers for additional presets!
