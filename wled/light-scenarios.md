# Bambu P1S + Dual AMS LED Scenario Catalog

This document defines all LED‑driven scenarios for a **Bambu P1S with two AMS units**, including recommended LED behaviors for each lighting zone:

- **Printer Lid LEDs**  
- **Front Door C‑LED**  
- **AMS Top LEDs (x2)**  
- **Filament Tag LEDs (per tray)**  
- **Hygrometer LEDs (per AMS)**  

Use this as the master reference for WLED presets and Home Assistant automations.

---

## 1. Printer Power & Connectivity States

### 1.1 Printer Offline / Unreachable
**Definition:** Printer is powered off or HA cannot reach it.  
**Suggested Lighting:**  
- Lid: Off  
- Door: Dim amber  
- AMS: Off  
- Hygrometer: Off  

### 1.2 Printer Idle
**Definition:** Printer is powered on but not printing.  
**Suggested Lighting:**  
- Lid: Soft white  
- Door: Soft blue  
- AMS: Low‑brightness white  
- Hygrometer: On  

### 1.3 Printer Busy (General Active State)
**Definition:** Printer is performing any job‑related action.  
**Suggested Lighting:**  
- Lid: Medium white  
- Door: Solid state color  
- AMS: White  
- Hygrometer: On  

---

## 2. Print Lifecycle States

### 2.1 Heating Bed
**Definition:** Bed warming before print.  
**Suggested Lighting:**  
- Lid: Orange  
- Door: Orange pulse  
- AMS: Off  

### 2.2 Heating Nozzle
**Definition:** Nozzle warming before print.  
**Suggested Lighting:**  
- Lid: Yellow  
- Door: Yellow pulse  
- AMS: Off  

### 2.3 Bed Leveling / Lidar Scan
**Definition:** Printer probing or scanning.  
**Suggested Lighting:**  
- Lid: Blue pulse  
- Door: Blue chase  
- AMS: Off  

### 2.4 Purge Line / Nozzle Cleaning
**Definition:** Printer purging or wiping nozzle.  
**Suggested Lighting:**  
- Lid: Cyan  
- Door: Cyan pulse  
- AMS: Off  

### 2.5 Printing
**Definition:** Active printing.  
**Suggested Lighting:**  
- Lid: White  
- Door: Green  
- AMS: White  
- Filament Tags: Filament color in use  
- Hygrometer: On  

### 2.6 Print Paused (User‑Initiated)
**Definition:** User manually paused the print.  
**Suggested Lighting:**  
- Lid: Yellow  
- Door: Yellow blink  
- AMS: Yellow  

### 2.7 Print Paused (Error)
**Definition:** Printer paused due to error.  
**Suggested Lighting:**  
- Lid: Red  
- Door: Red strobe  
- AMS: Red  
- Filament Tags: Red on affected tray  

### 2.8 Print Finished
**Definition:** Print completed successfully.  
**Suggested Lighting:**  
- Lid: Green  
- Door: Green pulse  
- AMS: Green  
- Filament Tags: Last‑used filament color  

---

## 3. Error & Warning States

### 3.1 Filament Runout
**Definition:** AMS tray reports runout.  
**Suggested Lighting:**  
- Lid: Red  
- Door: Red blink  
- AMS: Red on affected AMS  
- Filament Tags: Red on affected tray  

### 3.2 Filament Tangle / Jam
**Definition:** AMS detects abnormal resistance.  
**Suggested Lighting:**  
- AMS: Orange strobe  
- Filament Tags: Orange  
- Door: Orange blink  

### 3.3 AMS Communication Error
**Definition:** AMS offline or not responding.  
**Suggested Lighting:**  
- AMS: Purple pulse  
- Door: Purple  

### 3.4 Temperature Error
**Definition:** Nozzle or bed temperature fault.  
**Suggested Lighting:**  
- Lid: Red  
- Door: Red strobe  
- AMS: Red  

### 3.5 Door Open During Print
**Definition:** Door opened while printing.  
**Suggested Lighting:**  
- Lid: Bright white  
- Door: Bright white  
- AMS: Off  

---

## 4. AMS‑Specific Scenarios

### 4.1 Filament Loading
**Definition:** AMS loading filament into printer.  
**Suggested Lighting:**  
- AMS: Blue chase  
- Filament Tags: Blue on active tray  

### 4.2 Filament Unloading
**Definition:** AMS retracting filament.  
**Suggested Lighting:**  
- AMS: Teal chase  
- Filament Tags: Teal  

### 4.3 AMS Drying Mode
**Definition:** AMS heater active (AMS 2 Pro).  
**Suggested Lighting:**  
- AMS: Warm amber  
- Hygrometer: Bright white  

### 4.4 AMS Humidity High
**Definition:** Hygrometer reading above threshold.  
**Suggested Lighting:**  
- Hygrometer: Red  
- AMS: Red pulse  

### 4.5 AMS Humidity Normal
**Definition:** Hygrometer reading normal.  
**Suggested Lighting:**  
- Hygrometer: White  
- AMS: White  

### 4.6 AMS Tray Selected (Pre‑Print)
**Definition:** Printer has selected a tray for upcoming print.  
**Suggested Lighting:**  
- Filament Tags: Filament color  
- AMS: White  

### 4.7 AMS Tray Actively Feeding
**Definition:** Filament currently being pulled.  
**Suggested Lighting:**  
- Filament Tags: Bright filament color  
- AMS: White  

---

## 5. Maintenance & Utility States

### 5.1 Cooling Down
**Definition:** Printer cooling after print.  
**Suggested Lighting:**  
- Lid: Blue  
- Door: Blue pulse  

### 5.2 Chamber Light (Manual)
**Definition:** User toggles chamber light.  
**Suggested Lighting:**  
- Lid: White  
- Door: White  

### 5.3 Filament Change Requested
**Definition:** Printer requests filament change.  
**Suggested Lighting:**  
- Lid: Yellow  
- Door: Yellow blink  
- AMS: Yellow  
- Filament Tags: Yellow on required tray  

### 5.4 Nozzle Cleaning Required
**Definition:** Printer requests maintenance.  
**Suggested Lighting:**  
- Lid: Orange  
- Door: Orange pulse  

### 5.5 Fans Running (Post‑Print)
**Definition:** Cooling fans still active.  
**Suggested Lighting:**  
- Lid: Dim blue  
- Door: Dim blue  

---

## 6. Environmental & Safety States

### 6.1 High Chamber Temperature
**Definition:** Chamber temp exceeds threshold.  
**Suggested Lighting:**  
- Lid: Red  
- Door: Red pulse  

### 6.2 Low Chamber Temperature
**Definition:** Chamber too cold for print.  
**Suggested Lighting:**  
- Lid: Blue  
- Door: Blue  

### 6.3 Power Loss Recovery
**Definition:** Printer recovering from power outage.  
**Suggested Lighting:**  
- Lid: Purple  
- Door: Purple pulse  

---

## 7. Optional / Aesthetic Modes

### 7.1 Show Mode
**Definition:** Idle aesthetic animations.  
**Suggested Lighting:**  
- AMS: Rainbow  
- Door: Chase  
- Lid: Soft white  

### 7.2 Night Mode
**Definition:** Quiet hours.  
**Suggested Lighting:**  
- All LEDs: Off or very dim warm white  

### 7.3 Remote Monitoring Mode
**Definition:** User viewing via camera.  
**Suggested Lighting:**  
- Lid: Bright white  
- Door: White  

---

## 8. LED Zone Usage Summary

| LED Zone | Primary Uses |
|---------|--------------|
| **Lid LEDs** | Print visibility, state color, error indication |
| **Door C‑LED** | High‑visibility status, warnings, progress |
| **AMS Top LEDs** | Filament loading, AMS errors, humidity, spool illumination |
| **Filament Tag LEDs** | Tray‑specific status, filament color mapping, runout alerts |
| **Hygrometer LEDs** | Humidity alerts, drying mode, AMS environmental status |
