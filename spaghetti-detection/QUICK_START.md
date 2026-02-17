# Spaghetti Detection - Quick Start Guide

Get your Bambu Lab spaghetti detection up and running in 15 minutes!

## 🎯 Overview

This setup enables real-time print failure detection for your Bambu Lab printer using machine learning.

## ⚡ Quick Setup (15 minutes)

### Step 1: Deploy on server-mini (5 minutes)

```bash
# SSH into server-mini
ssh user@server-mini

# Create directory
mkdir -p ~/bambulab/spaghetti-detection
cd ~/bambulab/spaghetti-detection

# Copy docker-compose.yml from this directory
# Or download directly:
wget https://raw.githubusercontent.com/rsocko/hass-bambulab-config/main/spaghetti-detection/docker-compose.yml

# Create environment file
cat > .env << EOF
ML_API_TOKEN=$(openssl rand -hex 32)
TZ=America/New_York
EOF

# Start the service
docker compose up -d

# Verify it's running
docker compose ps
curl http://localhost:3333/health
```

✅ **Success**: You should see `{"status": "healthy"}` or similar

### Step 2: Install Home Assistant Integration (5 minutes)

1. **Open HACS** in Home Assistant
2. **Go to Integrations** → Click **+** → Search **"Bambu Lab P1 - Spaghetti Detection"**
3. **Click Install** → **Restart Home Assistant**
4. **Add Integration**: Settings → Devices & Services → Add Integration → "Bambu Lab P1 - Spaghetti Detection"
5. **Configure**:
   - Host: `http://server-mini:3333` (or IP address)
   - Token: Copy from `.env` file on server-mini: `cat ~/bambulab/spaghetti-detection/.env`

### Step 3: Set Up Automation (5 minutes)

1. **Import Blueprint**:
   - Go to Settings → Automations & Scenes → Blueprints
   - Click **Import Blueprint**
   - Use URL: `https://github.com/nberktumer/ha-bambu-lab-p1-spaghetti-detection/blob/main/blueprints/spaghetti_detection.yaml`
   - Or use the local blueprint from `spaghetti_detection_blueprint.yaml`

2. **Create Automation**:
   - Find "Bambu Lab Spaghetti Detection" blueprint
   - Click **Create Automation**
   - Configure:
     - **Printer**: Select your Bambu Lab printer
     - **Home Assistant URL**: Your HA URL (e.g., `http://homeassistant.local:8123`)
     - **Obico ML Host**: `http://server-mini:3333`
     - **API Token**: Same as integration config
     - **Action**: Choose "Pause Print" (recommended for first test)
     - **Notification**: Keep defaults
   - **Save**

✅ **Success**: Automation is created and enabled

## 🧪 Test It

### Test 1: Service is Running

```bash
# On server-mini
curl http://localhost:3333/health

# From Home Assistant (Developer Tools → Template)
{{ states('sensor.obico_ml_server_status') }}
```

Expected: `healthy` or `online`

### Test 2: Integration is Working

1. Go to **Settings → Devices & Services**
2. Find **"Bambu Lab P1 - Spaghetti Detection"**
3. Click to view entities
4. Verify entities are available

### Test 3: Full Detection Flow

**Option A: Use Test Print**
1. Start a small test print
2. Wait for detection to run (default: every 30 seconds)
3. Check notifications and logs

**Option B: Manual Trigger**
1. Go to Developer Tools → Services
2. Call the automation manually
3. Monitor logs for activity

## 📊 Monitor Resources

```bash
# View real-time stats
docker stats obico-ml-server

# Check memory usage
docker stats obico-ml-server --no-stream --format "{{.MemUsage}}"

# View logs
docker compose logs -f obico-ml-server
```

Expected:
- Memory: < 2GB under normal load
- CPU: < 50% average, spikes during detection
- Health: Should be "healthy"

## 🎨 Configure for Your Needs

### Adjust Detection Frequency

Edit automation:
- **Detection Interval**: 30s default
- Increase to 60s to reduce resource usage
- Decrease to 15s for more aggressive monitoring

### Change Action on Detection

- **Notify Only**: Get alert, manual intervention
- **Pause Print**: Pause and wait for confirmation
- **Cancel Print**: Stop immediately

### Notification Settings

- **Critical**: Alerts with sound even on silent mode
- **Standard**: Normal notifications
- **None**: No notifications (check manually)

## ⚠️ Common Issues

### Issue: "Connection refused"

```bash
# Check if service is running
docker compose ps

# Check logs
docker compose logs obico-ml-server

# Restart if needed
docker compose restart
```

### Issue: "Authentication failed"

- Verify API token matches in:
  1. `.env` file on server-mini
  2. Home Assistant integration config
  3. Automation configuration

```bash
# View token on server-mini
cat ~/bambulab/spaghetti-detection/.env | grep ML_API_TOKEN
```

### Issue: High memory usage

```bash
# Check current usage
docker stats obico-ml-server --no-stream

# If > 2.5GB, adjust limits in docker-compose.yml
# Or restart container
docker compose restart
```

### Issue: Detection not triggering

1. **Check printer is printing**:
   ```
   Printer Status → should be "printing"
   ```

2. **Verify automation is enabled**:
   ```
   Settings → Automations → Find your automation → Check enabled
   ```

3. **Review automation logs**:
   ```
   Settings → Automations → Click automation → View traces
   ```

## 📱 Mobile App Setup

For mobile notifications, install Home Assistant Companion app:

1. **iOS**: [App Store](https://apps.apple.com/app/home-assistant/id1099568401)
2. **Android**: [Play Store](https://play.google.com/store/apps/details?id=io.homeassistant.companion.android)

Then use notification service: `notify.mobile_app_<device_name>`

## 🔄 Daily Operations

### Starting/Stopping

```bash
# Stop service
docker compose down

# Start service
docker compose up -d

# Restart service
docker compose restart

# Update to latest version
docker compose pull
docker compose up -d
```

### Viewing Logs

```bash
# Live logs
docker compose logs -f

# Last 100 lines
docker compose logs --tail=100

# Logs from last hour
docker compose logs --since=1h
```

### Backup Configuration

```bash
# Backup on server-mini
cd ~/bambulab/spaghetti-detection
tar -czf backup-$(date +%Y%m%d).tar.gz docker-compose.yml .env
```

## 📈 Next Steps

Once working:

1. **Fine-tune thresholds**: Adjust confidence level based on your experience
2. **Add monitoring**: Set up Home Assistant sensors (see MONITORING.md)
3. **Custom alerts**: Add additional notification channels (Discord, Telegram, etc.)
4. **Historical tracking**: Create dashboard to track detection accuracy

## 📚 Additional Resources

- **Full Documentation**: [README.md](README.md)
- **Monitoring Guide**: [MONITORING.md](MONITORING.md)
- **Troubleshooting**: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- **Integration Docs**: [GitHub](https://github.com/nberktumer/ha-bambu-lab-p1-spaghetti-detection)

## ✅ Checklist

Before considering setup complete:

- [ ] Docker container running on server-mini
- [ ] Health check passing
- [ ] Home Assistant integration installed and configured
- [ ] Automation created and enabled
- [ ] Test notification received
- [ ] Resource monitoring set up
- [ ] Backup configuration saved
- [ ] Mobile app notifications working (optional)

## 🆘 Need Help?

1. **Check logs first**: `docker compose logs obico-ml-server`
2. **Review documentation**: Full README and troubleshooting guide
3. **Test connectivity**: Use curl commands above
4. **Verify configuration**: Double-check API tokens match everywhere

---

**Setup Time**: ~15 minutes  
**Maintenance**: Minimal (automatic restarts, log rotation)  
**Resource Usage**: ~1-2GB RAM, <50% CPU average
