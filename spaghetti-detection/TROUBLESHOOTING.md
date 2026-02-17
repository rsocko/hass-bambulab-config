# Spaghetti Detection - Troubleshooting Guide

Common issues and their solutions for the Bambu Lab spaghetti detection system.

## 🔍 Diagnostic Commands

Run these first to gather information:

```bash
# On server-mini
# 1. Check container status
docker compose ps

# 2. View recent logs
docker compose logs --tail=50 obico-ml-server

# 3. Check health
docker inspect --format='{{.State.Health.Status}}' obico-ml-server

# 4. Test endpoint
curl -v http://localhost:3333/health

# 5. Check resources
docker stats obico-ml-server --no-stream

# 6. Verify network
ping server-mini
netstat -tulpn | grep 3333
```

## 🐛 Common Issues

### 1. Container Won't Start

**Symptoms:**
- `docker compose ps` shows container as "Exited"
- Error in logs: "Cannot start container"

**Diagnosis:**
```bash
docker compose logs obico-ml-server
```

**Solutions:**

#### A. Port Already in Use
```bash
# Check what's using port 3333
sudo netstat -tulpn | grep 3333

# If something else is using it:
# Option 1: Stop the other service
# Option 2: Change port in docker-compose.yml
ports:
  - "3334:3333"  # Use 3334 on host instead
```

#### B. Insufficient Memory
```bash
# Check available memory
free -h

# If less than 4GB total:
# Reduce memory limit in docker-compose.yml
resources:
  limits:
    memory: 2G
```

#### C. Docker Daemon Issues
```bash
# Restart Docker
sudo systemctl restart docker

# Try starting again
docker compose up -d
```

---

### 2. Connection Refused from Home Assistant

**Symptoms:**
- Integration shows "Connection refused" or "Cannot connect"
- curl from HA fails: `curl: (7) Failed to connect`

**Diagnosis:**
```bash
# From Home Assistant host/container
curl http://server-mini:3333/health

# Or with IP address
curl http://192.168.1.x:3333/health
```

**Solutions:**

#### A. Hostname Not Resolving
```bash
# Test DNS resolution
ping server-mini

# If fails, use IP address in HA config instead:
# http://192.168.1.x:3333
```

#### B. Firewall Blocking
```bash
# On server-mini, check firewall
sudo ufw status

# If active, allow port 3333
sudo ufw allow 3333/tcp

# Or for specific IP (more secure)
sudo ufw allow from 192.168.1.y to any port 3333
```

#### C. Wrong Network
```bash
# Verify both HA and server-mini are on same network
# On server-mini:
ip addr show

# On HA host:
ip addr show

# Networks should match (e.g., both 192.168.1.x)
```

---

### 3. Authentication Failed

**Symptoms:**
- "401 Unauthorized" error
- "Invalid API token"
- Integration configured but not working

**Diagnosis:**
```bash
# View token in .env file
cat ~/bambulab/spaghetti-detection/.env | grep ML_API_TOKEN

# Test with curl
curl -H "Authorization: Bearer YOUR_TOKEN_HERE" http://localhost:3333/health
```

**Solutions:**

#### A. Token Mismatch
Ensure token matches in ALL three places:

1. **server-mini `.env` file**:
   ```bash
   cat ~/bambulab/spaghetti-detection/.env
   # ML_API_TOKEN=your_token_here
   ```

2. **Home Assistant Integration Config**:
   - Settings → Devices & Services
   - Find "Bambu Lab P1 - Spaghetti Detection"
   - Click Configure
   - Update token

3. **Automation Blueprint Config**:
   - Settings → Automations
   - Edit your spaghetti detection automation
   - Update "Obico ML API Token" field

#### B. Special Characters in Token
If token has special characters, wrap in quotes:
```bash
# In .env file
ML_API_TOKEN="token-with-special-chars"
```

#### C. Restart Required
```bash
# After changing token, restart container
docker compose restart
```

---

### 4. High Memory Usage

**Symptoms:**
- Container using > 2.5GB RAM
- System becoming slow
- Out of memory errors

**Diagnosis:**
```bash
# Check current usage
docker stats obico-ml-server --no-stream

# Check system memory
free -h

# View memory trends
docker stats obico-ml-server  # Live view
```

**Solutions:**

#### A. Reduce Memory Limit
Edit `docker-compose.yml`:
```yaml
resources:
  limits:
    memory: 2G  # Reduce from 3G
```

Then restart:
```bash
docker compose down
docker compose up -d
```

#### B. Increase Detection Interval
In Home Assistant automation:
- Change "Detection Interval" from 30s to 60s or higher
- Reduces frequency of ML inference

#### C. Restart Container Periodically
Add a cron job on server-mini:
```bash
# Edit crontab
crontab -e

# Add line to restart daily at 3 AM
0 3 * * * cd ~/bambulab/spaghetti-detection && docker compose restart
```

#### D. Check for Memory Leaks
```bash
# Watch memory over time
watch -n 5 'docker stats obico-ml-server --no-stream'

# If steadily increasing, may be a bug
# Report to integration developers
```

---

### 5. Detection Not Triggering

**Symptoms:**
- Print running but no detection happening
- No notifications received
- Logs show no activity

**Diagnosis:**

```bash
# On Home Assistant
# Developer Tools → Template
{{ states('sensor.ntk_ryansoffice_3dprinter_print_status') }}

# Should show "printing" when print is active
```

**Solutions:**

#### A. Automation Not Enabled
1. Settings → Automations & Scenes
2. Find your spaghetti detection automation
3. Check toggle is ON (blue)
4. If OFF, click to enable

#### B. Wrong Printer Selected
1. Edit automation
2. Verify "Bambu Lab Printer" field
3. Should match your actual printer entity

#### C. Print Status Not Detected
```bash
# Check printer integration
# Settings → Devices & Services → Bambu Lab
# Should show printer online and entities available
```

#### D. Check Automation Traces
1. Settings → Automations
2. Click your automation
3. Click "Traces" tab
4. View last runs and any errors

---

### 6. False Positives (Too Many Alerts)

**Symptoms:**
- Getting alerts when print is fine
- Prints being paused unnecessarily

**Solutions:**

#### A. Increase Confidence Threshold
In automation config:
- "Confidence Threshold": Increase from 80% to 90%
- Higher = fewer false positives, but may miss some real issues

#### B. Adjust Detection Interval
- Increase from 30s to 60s
- Gives more time for transient issues to resolve

#### C. Review Detection History
- Check which prints are triggering false alerts
- Common causes: First layer, certain materials, camera angle

#### D. Improve Camera View
- Ensure camera has clear view of print bed
- Clean camera lens
- Adjust lighting if needed

---

### 7. False Negatives (Missed Failures)

**Symptoms:**
- Print fails but no alert sent
- Spaghetti found after print completes

**Solutions:**

#### A. Decrease Confidence Threshold
- Lower from 80% to 70%
- More sensitive but may increase false positives

#### B. Decrease Detection Interval
- Check more frequently (e.g., 20s instead of 30s)
- Catches issues earlier

#### C. Check Camera Feed
```bash
# Verify camera entity is working
# Developer Tools → States
# Find camera entity for your printer
# Click to view current snapshot
```

---

### 8. Container Unhealthy

**Symptoms:**
- Health check failing
- Status shows "unhealthy"

**Diagnosis:**
```bash
# View health check details
docker inspect --format='{{json .State.Health}}' obico-ml-server | jq

# Test endpoint manually
curl -f http://localhost:3333/health
```

**Solutions:**

#### A. Service Not Responding
```bash
# Restart container
docker compose restart

# If still failing, check logs
docker compose logs obico-ml-server
```

#### B. Adjust Health Check Timing
Edit `docker-compose.yml`:
```yaml
healthcheck:
  interval: 60s  # Check less frequently
  timeout: 20s   # Allow more time
  start_period: 60s  # Give more startup time
```

#### C. Disable Health Check (Temporary)
```yaml
healthcheck:
  disable: true
```
Use only for troubleshooting - re-enable once resolved.

---

### 9. Logs Not Showing

**Symptoms:**
- `docker compose logs` returns nothing
- Can't debug issues

**Solutions:**

```bash
# Check if container is actually running
docker compose ps

# View logs directly from Docker
docker logs obico-ml-server

# Increase log verbosity in docker-compose.yml
environment:
  - LOG_LEVEL=DEBUG

# Restart to apply
docker compose restart
```

---

### 10. Integration Not Showing in Home Assistant

**Symptoms:**
- Can't find "Bambu Lab P1 - Spaghetti Detection" integration
- HACS shows it's installed

**Solutions:**

#### A. Restart Home Assistant
```bash
# Settings → System → Restart
```

#### B. Clear Browser Cache
- Hard refresh: Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)
- Or clear browser cache completely

#### C. Check HACS Installation
1. HACS → Integrations
2. Search "Bambu Lab P1"
3. Verify it says "Installed"
4. If not, click and install

#### D. Check Integration Files
```bash
# On Home Assistant host
ls -la /config/custom_components/bambu_lab_p1_spaghetti_detection/

# Should have __init__.py, manifest.json, etc.
```

---

## 🧪 Testing Tools

### Test ML Server API

```bash
# Health check
curl http://server-mini:3333/health

# With authentication
curl -H "Authorization: Bearer YOUR_TOKEN" \
     http://server-mini:3333/health

# Test detection endpoint (requires image)
curl -X POST \
     -H "Authorization: Bearer YOUR_TOKEN" \
     -F "image=@test_image.jpg" \
     http://server-mini:3333/api/detect
```

### Test Home Assistant Connectivity

```yaml
# Add to configuration.yaml temporarily
rest_command:
  test_obico:
    url: "http://server-mini:3333/health"
    method: GET
    headers:
      Authorization: "Bearer YOUR_TOKEN"

# Then call from Developer Tools → Services
# Service: rest_command.test_obico
```

### Monitor Network Traffic

```bash
# On server-mini
# Install tcpdump if needed
sudo apt-get install tcpdump

# Monitor port 3333
sudo tcpdump -i any -n port 3333

# You should see traffic when HA connects
```

---

## 🔧 Advanced Troubleshooting

### Enable Debug Logging

**In Docker Container:**
Edit `docker-compose.yml`:
```yaml
environment:
  - LOG_LEVEL=DEBUG
```

Restart: `docker compose restart`

**In Home Assistant:**
Add to `configuration.yaml`:
```yaml
logger:
  default: info
  logs:
    custom_components.bambu_lab_p1_spaghetti_detection: debug
```

Restart Home Assistant.

### Capture Network Traffic

```bash
# On server-mini
sudo tcpdump -i any -w /tmp/capture.pcap port 3333

# Let it run during a test
# Stop with Ctrl+C

# Analyze with Wireshark or:
tcpdump -r /tmp/capture.pcap -A
```

### Check Docker Networking

```bash
# View networks
docker network ls

# Inspect network
docker network inspect bambulab-network

# Test connectivity between containers
docker exec obico-ml-server ping -c 3 google.com
```

---

## 📊 Performance Troubleshooting

### Slow Detection Response

**Check:**
1. Server CPU usage: `top` or `htop`
2. Network latency: `ping server-mini`
3. Disk I/O: `iostat -x 1`

**Solutions:**
- Reduce detection frequency
- Allocate more CPU in docker-compose.yml
- Use wired network instead of WiFi
- Ensure SSD (not HDD) for Docker storage

### High CPU Usage

```bash
# Check what's using CPU
top

# If obico-ml-server is high:
# 1. Reduce detection frequency in automation
# 2. Check for multiple concurrent requests
# 3. Review logs for errors causing retry loops
```

---

## 📝 Logging Best Practices

```bash
# Save logs for debugging
docker compose logs > debug-$(date +%Y%m%d-%H%M%S).log

# Follow logs in real-time during testing
docker compose logs -f --timestamps

# Filter logs for errors
docker compose logs | grep -i error

# Filter logs for specific timeframe
docker compose logs --since="2024-01-15T10:00:00"
```

---

## 🆘 Still Having Issues?

### Gather Information

Create a debug report:

```bash
#!/bin/bash
# Save as debug-report.sh and run

echo "=== System Info ===" > debug-report.txt
uname -a >> debug-report.txt
free -h >> debug-report.txt

echo -e "\n=== Docker Info ===" >> debug-report.txt
docker version >> debug-report.txt
docker compose version >> debug-report.txt

echo -e "\n=== Container Status ===" >> debug-report.txt
docker compose ps >> debug-report.txt

echo -e "\n=== Container Logs ===" >> debug-report.txt
docker compose logs --tail=100 >> debug-report.txt

echo -e "\n=== Health Check ===" >> debug-report.txt
docker inspect --format='{{json .State.Health}}' obico-ml-server | jq >> debug-report.txt

echo -e "\n=== Resource Usage ===" >> debug-report.txt
docker stats obico-ml-server --no-stream >> debug-report.txt

echo "Debug report saved to debug-report.txt"
```

### Get Help

1. **Check existing issues**: [Integration GitHub Issues](https://github.com/nberktumer/ha-bambu-lab-p1-spaghetti-detection/issues)
2. **Search forums**: Home Assistant Community
3. **Create new issue** with:
   - Your debug report
   - What you were trying to do
   - What happened instead
   - Steps to reproduce

---

## ✅ Troubleshooting Checklist

Before asking for help, verify:

- [ ] Docker container is running: `docker compose ps`
- [ ] Health check passing: `docker inspect obico-ml-server`
- [ ] Network connectivity: `curl http://server-mini:3333/health`
- [ ] API token matches everywhere
- [ ] Home Assistant integration installed and configured
- [ ] Automation exists and is enabled
- [ ] Printer integration working
- [ ] Logs checked for errors: `docker compose logs`
- [ ] Sufficient resources available: `free -h`
- [ ] Firewall not blocking port 3333

---

**Note**: Most issues are related to network connectivity or authentication. Double-check these first!
