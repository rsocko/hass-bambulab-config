# Bambuddy Photo Archive Integration

## Overview

This document outlines how to integrate with Bambuddy's API to push printer photos to the print archive automatically.

## What is Bambuddy?

Bambuddy is a self-hosted print archive and management system for Bambu Lab 3D printers. It provides:
- Print job tracking and history
- Photo/timelapse storage
- API for automation
- Webhook support for notifications

## API Integration

### Authentication

Bambuddy uses API key authentication. Generate an API key from:
- Bambuddy Web UI → Settings → API Keys
- Include the key in requests as the `X-API-Key` header

### Base URL

Default base URL: `http://your-bambuddy-server:8000/api/v1`

### Relevant Endpoints

1. **List Archives**: `GET /archives`
   - Returns list of print jobs in the archive

2. **Create Archive Entry**: `POST /archives`
   - Creates a new print job entry
   - Include print details (name, duration, weight, etc.)

3. **Upload Photo to Archive**: `POST /archives/{id}/photos`
   - Uploads a photo to an existing archive entry
   - Accepts image file uploads

## Home Assistant Integration Approach

### Option 1: RESTful Command (Simple)

Add to your `configuration.yaml`:

```yaml
rest_command:
  bambuddy_upload_photo:
    url: "http://your-bambuddy-server:8000/api/v1/archives/{{ archive_id }}/photos"
    method: POST
    headers:
      X-API-Key: "YOUR_API_KEY_HERE"
    payload: "{{ photo_data }}"
    content_type: "multipart/form-data"
```

### Option 2: Shell Command (Recommended)

Add to your `configuration.yaml`:

```yaml
shell_command:
  # Upload latest snapshot file to Bambuddy
  bambuddy_upload_latest_snapshot: >
    latest_file=$(ls -t /config/www/printer_snapshots/*.jpg | head -n 1) &&
    curl -X POST 
    -H "X-API-Key: {{ api_key }}" 
    -F "file=@${latest_file}" 
    "{{ base_url }}/archives/{{ archive_id }}/photos"
```

This command finds the most recently created snapshot and uploads it to Bambuddy.

### Option 3: Python Script (Most Powerful)

Create `/config/python_scripts/bambuddy_upload.py`:

```python
import requests
import os

# Get parameters
api_key = data.get('api_key')
base_url = data.get('base_url')
archive_id = data.get('archive_id')
snapshot_path = data.get('snapshot_path')

# Upload photo
url = f"{base_url}/archives/{archive_id}/photos"
headers = {"X-API-Key": api_key}
files = {"file": open(snapshot_path, "rb")}

response = requests.post(url, headers=headers, files=files)

# Log result
if response.status_code == 200:
    logger.info(f"Successfully uploaded photo to Bambuddy archive {archive_id}")
else:
    logger.error(f"Failed to upload photo: {response.status_code} - {response.text}")
```

## Integration with Print Complete Notification

To integrate Bambuddy photo upload with the print completion notification:

1. **Create Archive Entry First** (on print start):
   - Capture print job details when print starts
   - Send POST to `/archives` to create entry
   - Store the returned `archive_id` in an input_text helper

2. **Upload Photo on Completion** (on print finish):
   - Use the notification automation's snapshot
   - Call the Bambuddy upload action with the stored `archive_id`

### Example Integration in Automation

Add this action to `print_complete_notification.yaml`:

```yaml
# After camera snapshot is taken
- action: shell_command.bambuddy_upload_snapshot
  data:
    archive_id: "{{ states('input_text.current_print_archive_id') }}"
    snapshot_path: "/config/www/printer_snapshots/{{ now().strftime('%Y%m%d_%H%M%S') }}_{{ task_name | replace(' ', '_') }}.jpg"
```

## Required Configuration

### Input Helpers

Add to `notification_helpers.yaml`:

```yaml
input_text:
  bambuddy_api_key:
    name: Bambuddy API Key
    max: 255
    initial: ""
  
  bambuddy_base_url:
    name: Bambuddy Base URL
    max: 255
    initial: "http://localhost:8000/api/v1"
  
  current_print_archive_id:
    name: Current Print Archive ID
    max: 100
    initial: ""

input_boolean:
  bambuddy_integration_enabled:
    name: Bambuddy Integration Enabled
    initial: false
```

## Workflow

### Complete Workflow with Bambuddy

1. **Print Starts**:
   - Trigger: `event_print_started`
   - Create Bambuddy archive entry via API
   - Store `archive_id` in `input_text.current_print_archive_id`

2. **Print Completes**:
   - Trigger: `event_print_finished`
   - Take camera snapshot
   - Upload snapshot to Bambuddy using stored `archive_id`
   - Send notification to user
   - Clear `input_text.current_print_archive_id`

3. **Print Fails**:
   - Trigger: `binary_sensor.print_error` turns on
   - Take camera snapshot
   - Upload snapshot to Bambuddy (if `archive_id` exists)
   - Send error notification to user
   - Clear `input_text.current_print_archive_id`

## Security Considerations

1. **Never hardcode API keys** in automations
   - Use `secrets.yaml` or input_text helpers
   - Consider using Home Assistant's secure storage

2. **Validate API responses**
   - Check status codes before proceeding
   - Log errors for troubleshooting

3. **Network Security**
   - Use HTTPS if Bambuddy is exposed externally
   - Consider firewall rules to restrict access

## Resources

- [Bambuddy Documentation](https://wiki.bambuddy.cool/)
- [Bambuddy API Reference](https://wiki.bambuddy.cool/reference/api/)
- [Bambuddy GitHub](https://github.com/maziggy/bambuddy)

## Future Enhancements

- Automatic archive cleanup (delete old photos)
- Sync filament usage data to Bambuddy
- Pull timelapse videos from Bambuddy
- Two-way sync between Home Assistant and Bambuddy
