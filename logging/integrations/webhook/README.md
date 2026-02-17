# Webhook Log Forwarding Integration

## Overview

Forward Home Assistant logs to a custom HTTP endpoint (webhook) for processing, storage, or integration with custom systems.

## Use Cases

- Forward logs to custom homelab services
- Integrate with incident management systems
- Send logs to serverless functions
- Trigger external automation workflows
- Custom log processing and analytics

## Configuration

### 1. Create REST Command in Home Assistant

Add to your `configuration.yaml`:

```yaml
rest_command:
  # Forward logs to webhook
  forward_log_to_webhook:
    url: "http://your-webhook-endpoint.local:8080/logs"
    method: POST
    headers:
      Content-Type: "application/json"
      Authorization: "Bearer YOUR_SECRET_TOKEN"
    payload: >
      {
        "timestamp": "{{ timestamp }}",
        "level": "{{ level }}",
        "logger": "{{ logger }}",
        "message": "{{ message }}",
        "correlation_id": "{{ correlation_id }}",
        "source": "homeassistant",
        "host": "{{ states('sensor.hostname') }}",
        "additional_context": {{ context | tojson }}
      }
```

### 2. Create Log Forwarding Automation

Create `logging/automations/webhook_forwarder.yaml`:

```yaml
- alias: "Logging: Forward Errors to Webhook"
  description: "Forward ERROR level logs to external webhook"
  mode: queued
  max: 50
  trigger:
    - platform: event
      event_type: system_log_event
      event_data:
        level: ERROR
  
  condition:
    # Only forward Bambu Lab logs
    - condition: template
      value_template: >-
        {{ trigger.event.data.name is defined and 
           'bambulab' in trigger.event.data.name | lower }}
  
  action:
    - variables:
        log_data:
          timestamp: "{{ now().isoformat() }}"
          level: "{{ trigger.event.data.level }}"
          logger: "{{ trigger.event.data.name }}"
          message: "{{ trigger.event.data.message[0] if trigger.event.data.message is defined else '' }}"
          correlation_id: "{{ now().timestamp() | string + '_' + range(1000, 9999) | random | string }}"
    
    # Forward to webhook
    - service: rest_command.forward_log_to_webhook
      data:
        timestamp: "{{ log_data.timestamp }}"
        level: "{{ log_data.level }}"
        logger: "{{ log_data.logger }}"
        message: "{{ log_data.message }}"
        correlation_id: "{{ log_data.correlation_id }}"
        context: "{{ trigger.event.data }}"
      continue_on_error: true

- alias: "Logging: Forward Critical Warnings to Webhook"
  description: "Forward WARNING level logs to external webhook (rate limited)"
  mode: queued
  max: 20
  trigger:
    - platform: event
      event_type: system_log_event
      event_data:
        level: WARNING
  
  condition:
    - condition: template
      value_template: >-
        {{ trigger.event.data.name is defined and 
           'bambulab' in trigger.event.data.name | lower }}
    
    # Only forward if multiple warnings (avoid spam)
    - condition: template
      value_template: >-
        {{ states('counter.bambulab_warning_count') | int > 3 }}
  
  action:
    - service: rest_command.forward_log_to_webhook
      data:
        timestamp: "{{ now().isoformat() }}"
        level: "WARNING"
        logger: "{{ trigger.event.data.name }}"
        message: "{{ trigger.event.data.message[0] if trigger.event.data.message is defined else '' }}"
        correlation_id: "{{ now().timestamp() | string }}"
        context: "{{ trigger.event.data }}"
      continue_on_error: true
```

## Webhook Payload Format

```json
{
  "timestamp": "2026-02-17T17:30:00.123456+00:00",
  "level": "ERROR",
  "logger": "homeassistant.components.bambulab.spoolman_sync",
  "message": "Print Complete ERROR: Cannot find spool...",
  "correlation_id": "1708189800.123_4567",
  "source": "homeassistant",
  "host": "homeassistant.local",
  "additional_context": {
    "name": "homeassistant.components.bambulab.spoolman_sync",
    "message": ["Print Complete ERROR: Cannot find spool..."],
    "level": "ERROR",
    "source": "components/bambulab/automation.py",
    "timestamp": 1708189800.123
  }
}
```

## Example Webhook Receivers

### Node.js Express Server

```javascript
const express = require('express');
const app = express();

app.use(express.json());

// Verify bearer token
const verifyToken = (req, res, next) => {
  const token = req.headers.authorization?.split(' ')[1];
  if (token === process.env.SECRET_TOKEN) {
    next();
  } else {
    res.status(401).json({ error: 'Unauthorized' });
  }
};

// Receive logs endpoint
app.post('/logs', verifyToken, (req, res) => {
  const log = req.body;
  
  console.log(`[${log.level}] ${log.logger}: ${log.message}`);
  
  // Process log based on level
  if (log.level === 'ERROR') {
    // Send to incident management
    notifyIncidentManagement(log);
  } else if (log.level === 'WARNING') {
    // Store for analysis
    storeWarning(log);
  }
  
  // Store in database
  db.logs.insert(log);
  
  res.status(200).json({ status: 'received', id: log.correlation_id });
});

app.listen(8080, () => {
  console.log('Webhook receiver listening on port 8080');
});
```

### Python Flask Server

```python
from flask import Flask, request, jsonify
import os
import json

app = Flask(__name__)

def verify_token():
    auth_header = request.headers.get('Authorization')
    if not auth_header:
        return False
    token = auth_header.split(' ')[1] if ' ' in auth_header else None
    return token == os.environ.get('SECRET_TOKEN')

@app.route('/logs', methods=['POST'])
def receive_log():
    if not verify_token():
        return jsonify({'error': 'Unauthorized'}), 401
    
    log = request.get_json()
    
    print(f"[{log['level']}] {log['logger']}: {log['message']}")
    
    # Process based on level
    if log['level'] == 'ERROR':
        handle_error(log)
    elif log['level'] == 'WARNING':
        handle_warning(log)
    
    # Store log
    store_log(log)
    
    return jsonify({'status': 'received', 'id': log['correlation_id']}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
```

### Go HTTP Server

```go
package main

import (
    "encoding/json"
    "fmt"
    "log"
    "net/http"
    "os"
    "strings"
)

type LogEntry struct {
    Timestamp      string                 `json:"timestamp"`
    Level          string                 `json:"level"`
    Logger         string                 `json:"logger"`
    Message        string                 `json:"message"`
    CorrelationID  string                 `json:"correlation_id"`
    Source         string                 `json:"source"`
    Host           string                 `json:"host"`
    Context        map[string]interface{} `json:"additional_context"`
}

func verifyToken(r *http.Request) bool {
    auth := r.Header.Get("Authorization")
    if auth == "" {
        return false
    }
    parts := strings.Split(auth, " ")
    if len(parts) != 2 {
        return false
    }
    return parts[1] == os.Getenv("SECRET_TOKEN")
}

func handleLogs(w http.ResponseWriter, r *http.Request) {
    if !verifyToken(r) {
        http.Error(w, "Unauthorized", http.StatusUnauthorized)
        return
    }
    
    var entry LogEntry
    if err := json.NewDecoder(r.Body).Decode(&entry); err != nil {
        http.Error(w, "Bad Request", http.StatusBadRequest)
        return
    }
    
    log.Printf("[%s] %s: %s\n", entry.Level, entry.Logger, entry.Message)
    
    // Process based on level
    switch entry.Level {
    case "ERROR":
        handleError(entry)
    case "WARNING":
        handleWarning(entry)
    }
    
    // Store log
    storeLog(entry)
    
    response := map[string]string{
        "status": "received",
        "id":     entry.CorrelationID,
    }
    
    w.Header().Set("Content-Type", "application/json")
    json.NewEncoder(w).Encode(response)
}

func main() {
    http.HandleFunc("/logs", handleLogs)
    log.Fatal(http.ListenAndServe(":8080", nil))
}
```

## Integration Examples

### 1. Discord Webhook

```yaml
rest_command:
  forward_to_discord:
    url: "https://discord.com/api/webhooks/YOUR_WEBHOOK_ID/YOUR_WEBHOOK_TOKEN"
    method: POST
    headers:
      Content-Type: "application/json"
    payload: >
      {
        "embeds": [{
          "title": "🚨 {{ level }} - {{ logger }}",
          "description": "{{ message }}",
          "color": {% if level == "ERROR" %}15158332{% elif level == "WARNING" %}16776960{% else %}3447003{% endif %},
          "fields": [
            {
              "name": "Timestamp",
              "value": "{{ timestamp }}",
              "inline": true
            },
            {
              "name": "Correlation ID",
              "value": "{{ correlation_id }}",
              "inline": true
            }
          ],
          "footer": {
            "text": "Home Assistant Logging"
          }
        }]
      }
```

### 2. Slack Webhook

```yaml
rest_command:
  forward_to_slack:
    url: "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
    method: POST
    headers:
      Content-Type: "application/json"
    payload: >
      {
        "blocks": [
          {
            "type": "header",
            "text": {
              "type": "plain_text",
              "text": "{{ level }}: {{ logger }}"
            }
          },
          {
            "type": "section",
            "text": {
              "type": "mrkdwn",
              "text": "*Message:*\n{{ message }}\n\n*Time:* {{ timestamp }}\n*CID:* `{{ correlation_id }}`"
            }
          }
        ]
      }
```

### 3. Prometheus Pushgateway

```yaml
rest_command:
  forward_to_prometheus:
    url: "http://pushgateway:9091/metrics/job/homeassistant/instance/{{ states('sensor.hostname') }}"
    method: POST
    headers:
      Content-Type: "text/plain"
    payload: >
      # TYPE homeassistant_log_event counter
      homeassistant_log_event{level="{{ level }}",logger="{{ logger }}"} 1 {{ now().timestamp() * 1000 | int }}
```

## Security Best Practices

1. **Use HTTPS**: Always use HTTPS for webhook endpoints
2. **Authentication**: Use bearer tokens or API keys
3. **Rate Limiting**: Implement rate limiting on webhook receiver
4. **Validation**: Validate incoming payloads
5. **Secrets Management**: Store tokens in secrets, not in config files

## Troubleshooting

### Webhook Not Receiving Logs

1. Check network connectivity:
   ```bash
   curl -X POST http://your-endpoint:8080/logs \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -d '{"test": "message"}'
   ```

2. Check Home Assistant logs for REST command errors

3. Verify webhook endpoint is accessible from HA network

### High Volume / Rate Limiting

Add throttling to automation:
```yaml
action:
  - condition: template
    value_template: >-
      {{ (now().timestamp() - 
          state_attr('automation.logging_forward_errors_to_webhook', 'last_triggered').timestamp() | float(0)) > 60 }}
```

### Webhook Timeouts

Increase timeout in rest_command:
```yaml
rest_command:
  forward_log_to_webhook:
    timeout: 10  # seconds
```

## Resources

- [Home Assistant REST Command](https://www.home-assistant.io/integrations/rest_command/)
- [Webhook Best Practices](https://webhooks.fyi/)
- [Discord Webhooks](https://discord.com/developers/docs/resources/webhook)
- [Slack Webhooks](https://api.slack.com/messaging/webhooks)
