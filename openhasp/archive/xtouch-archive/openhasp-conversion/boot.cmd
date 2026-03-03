// ================================================================
// xTouch → OpenHASP Boot Commands
// Runs once when the plate starts up
// ================================================================

// Set backlight brightness (0-255)
backlight {"state":"on","brightness":200}

// Set idle timeout (seconds) - dims screen after inactivity
// 0 = disabled, or set seconds (e.g., 120 = 2 minutes)
idle {"state":"off"}

// Start on home page
page 1

// Set the first sidebar button (Home) as checked
p0b2.val 1
