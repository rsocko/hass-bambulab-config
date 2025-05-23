# Spoolman API - Get Spools - Home Assistant Sensor (REST integration)

## Description:
Using the [REST integration](https://www.home-assistant.io/integrations/rest/) in Home Assistant installed, this creates a sensor that retrieves all of the non-archived spools from your inventory in Spoolman.

## Instructions:
Add the following code to your configuration.yaml in Home Assistant

```
# Example configuration.yaml entry
rest_command:
  spoolman_getspools:
    url: http://<SPOOLMAN URL>:<SPOOLMAN PORT>/api/v1/spool?allow_archived=false
    method: GET
    headers:
      accept: "application/json, text/html"
```

Note:
- Use the URL and PORT for Spoolman in your environment.
- The automations and scripts expect the sensor name to be as above: "spoolman_getspools"