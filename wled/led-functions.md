### Lighting Functions:

Top of Tag
- Used in current print
- Color-match for filament color (to highlight the tag)

Bottom of Tag
- % of filament left
- Used in current print
- Indicate if filament desiccant needs to be replaced (> X months old)
- Indicator if the spool has an error / run out

Top of AMS Tray
- Lighting of all spools (white)
- indicator of current spool in use
- Indicator if there is a spool error - eg filament load issue, etc.
- Animation if loading spool, unloading spoo
- Animation if heating spool slot (AMS2 only)

Front/Bottom of AMS Tray
- Lighting of all spools (white)
- indicator of current spool in use
- Indicator if there is a spool error - eg filament load issue, etc.
- Animation if loading spool, unloading spoo
- Animation if heating spool slot (AMS2 only)

Hygrometer (Top and Bottom)
- Lighting to make hygrometer visible
- Indicator if the humidity is high (above X) in the AMS
  
Bottom of Printer door
- Display print progress (as percent complete)
  -  Animate the progress portion in some way
  -  Pause animation if the print is paused or error
- Flash green when complete?
  
Left side of Printer door
- Show print status
  - Pulsing soft green when actively printing
  - flashing red on error
  - other?
    
Top of printer door
- same as left side (print status)

Interior Lights
- Use existing Home Assistant automation for rules to control colors based on print status & stage
