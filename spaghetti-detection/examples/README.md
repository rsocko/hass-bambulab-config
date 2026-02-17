# Example Home Assistant Configuration for Spaghetti Detection

This directory contains example configurations you can use with your Home Assistant setup.

## Files

- `sensors.yaml` - REST sensors for monitoring Obico ML Server
- `automations.yaml` - Example automations for alerts and actions
- `lovelace_card.yaml` - Dashboard card for monitoring

## Usage

1. Copy the relevant sections to your Home Assistant configuration files
2. Update entity IDs and hostnames to match your setup
3. Restart Home Assistant
4. Verify entities appear in Developer Tools → States

## Important Notes

- Replace `server-mini` with your actual hostname or IP address
- Update API tokens to match your configuration
- Adjust thresholds and intervals to your preferences
