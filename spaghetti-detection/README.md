# Bambu Lab Spaghetti Detection

This directory contains the configuration for setting up the Obico ML Server for spaghetti detection on your Bambu Lab 3D printer. This integration works with the [Bambu Lab P1 - Spaghetti Detection](https://github.com/nberktumer/ha-bambu-lab-p1-spaghetti-detection) Home Assistant integration.

## Overview

The spaghetti detection system uses machine learning to monitor your 3D prints in real-time and detect potential failures (spaghetti). It can automatically:
- Detect print failures using Obico's ML server
- Send notifications when failures are detected
- Pause or cancel prints automatically to prevent waste
- Work with any Bambu Lab printer (X1, P1, A1 series)

## Prerequisites

Before setting up this integration, ensure you have:

1. **Home Assistant** with [Bambu Lab Integration](https://github.com/greghesp/ha-bambulab) installed
2. **Docker and Docker Compose** installed on server-mini
3. **At least 4GB of RAM** available on server-mini ([Obico hardware requirements](https://www.obico.io/docs/server-guides/hardware-requirements/))
4. **Network access** from Home Assistant to server-mini on port 3333

### Supported Printers
- ✅ X1 Series
- ✅ P1 Series
- ✅ A1 Series

### NOT Supported
- ❌ Raspberry Pi (Any Model)
- ❌ Home Assistant Green/Yellow
- ❌ Latte Panda
- ❌ Jetson Nano 2GB

## Installation

### Step 1: Deploy Obico ML Server on server-mini

1. **Copy the configuration files to server-mini:**
   ```bash
   # SSH into server-mini
   ssh user@server-mini
   
   # Create directory for the service
   mkdir -p ~/bambulab/spaghetti-detection
   cd ~/bambulab/spaghetti-detection
   ```

2. **Create the configuration files:**
   ```bash
   # Copy docker-compose.yml and .env.example from this directory
   # Or create them manually using the provided files
   ```

3. **Configure environment variables:**
   ```bash
   # Copy the example environment file
   cp .env.example .env
   
   # Edit .env with your settings
   nano .env
   ```
   
   Update the following variables:
   - `ML_API_TOKEN`: Change to a secure random value (e.g., `openssl rand -hex 32`)
   - `TZ`: Set to your local timezone (e.g., `America/New_York`)

4. **Start the Obico ML Server:**
   ```bash
   docker compose up -d
   ```

5. **Verify the service is running:**
   ```bash
   # Check container status
   docker compose ps
   
   # Check logs
   docker compose logs -f
   
   # Test the health endpoint
   curl http://localhost:3333/health
   ```

### Step 2: Install Home Assistant Integration

1. **Install via HACS:**
   - Open HACS in Home Assistant
   - Go to Integrations
   - Click the "+" button
   - Search for "Bambu Lab P1 - Spaghetti Detection"
   - Click Install
   - Restart Home Assistant

2. **Configure the Integration:**
   - Go to Settings → Devices & Services
   - Click "Add Integration"
   - Search for "Bambu Lab P1 - Spaghetti Detection"
   - Enter the configuration:
     - **Obico ML API Host**: `http://server-mini:3333` (or the IP address of server-mini)
     - **Obico ML API Auth Token**: The value you set for `ML_API_TOKEN` in `.env`

### Step 3: Set Up Automation Blueprint

1. **Import the Blueprint:**
   - Click this button or manually import from [GitHub](https://github.com/nberktumer/ha-bambu-lab-p1-spaghetti-detection/blob/main/blueprints/spaghetti_detection.yaml)
   
2. **Create Automation from Blueprint:**
   - Go to Settings → Automations & Scenes → Blueprints
   - Find "Bambu Lab Spaghetti Detection"
   - Click "Create Automation"
   
3. **Configure the Blueprint Parameters:**
   - **Home Assistant Host**: Your Home Assistant URL (e.g., `http://homeassistant.local:8123`)
   - **Obico ML API Host**: `http://server-mini:3333` (same as integration config)
   - **Obico ML API Auth Token**: Same token as configured above
   - **Notification Settings**: Choose Critical, Standard, or None
   - **Notification Service**: Select notification service (default: `notify.notify`)
   - **Printer**: Select your Bambu Lab printer entity
   - **Action on Detection**: Choose Pause Print, Cancel Print, or Notify Only

4. **Save and Enable the Automation**

## Monitoring and Resource Usage

The Docker Compose configuration includes built-in monitoring capabilities:

### Container Resource Limits
- **Memory**: Limited to 3GB max, with 1GB minimum reservation
- **CPU**: Limited to 2 cores max, with 0.5 core minimum reservation
- **Health Check**: Automatic health monitoring every 30 seconds
- **Logging**: Rotated logs (max 10MB per file, 3 files retained)

### Monitoring Commands

```bash
# View container stats (CPU, memory, network, disk I/O)
docker stats obico-ml-server

# View detailed container info
docker inspect obico-ml-server

# View logs
docker compose logs -f obico-ml-server

# Check health status
docker inspect --format='{{.State.Health.Status}}' obico-ml-server
```

### Prometheus Monitoring (Optional)

If you have Prometheus set up, you can use the Docker metrics exporter:

```bash
# Add cAdvisor for Docker metrics
docker run -d \
  --name=cadvisor \
  --restart unless-stopped \
  --volume=/:/rootfs:ro \
  --volume=/var/run:/var/run:ro \
  --volume=/sys:/sys:ro \
  --volume=/var/lib/docker/:/var/lib/docker:ro \
  --publish=8080:8080 \
  gcr.io/cadvisor/cadvisor:latest
```

Then configure Prometheus to scrape `http://server-mini:8080/metrics`.

### Grafana Dashboard (Optional)

You can create a Grafana dashboard to visualize:
- CPU usage over time
- Memory usage and trends
- Container health status
- API request rates
- Detection accuracy metrics

## Troubleshooting

### Service Won't Start

```bash
# Check if port 3333 is already in use
sudo netstat -tulpn | grep 3333

# Check Docker logs for errors
docker compose logs obico-ml-server

# Verify sufficient RAM is available
free -h
```

### Integration Not Connecting

1. Verify the ML server is accessible from Home Assistant:
   ```bash
   # From Home Assistant container or host
   curl http://server-mini:3333/health
   ```

2. Check the API token matches in:
   - Docker compose `.env` file
   - Home Assistant integration configuration
   - Automation blueprint configuration

3. Check firewall rules allow traffic on port 3333

### High Resource Usage

1. Monitor current usage:
   ```bash
   docker stats obico-ml-server
   ```

2. Adjust resource limits in `docker-compose.yml` if needed

3. Consider reducing detection frequency in the automation

### Detection Not Working

1. Verify the Bambu Lab integration is working
2. Check that camera entity is available
3. Review automation logs in Home Assistant
4. Check Obico ML server logs:
   ```bash
   docker compose logs -f obico-ml-server
   ```

## Maintenance

### Updating the ML Server

```bash
# Pull latest image
docker compose pull

# Recreate container with new image
docker compose up -d

# Clean up old images
docker image prune
```

### Backup Configuration

```bash
# Backup configuration files
tar -czf spaghetti-detection-backup-$(date +%Y%m%d).tar.gz \
  docker-compose.yml .env
```

### Log Management

Logs are automatically rotated (10MB max per file, 3 files kept).

To manually view or clear logs:
```bash
# View logs
docker compose logs --tail=100

# Clear logs (will restart container)
docker compose down
docker compose up -d
```

## Performance Tuning

### For Systems with Limited RAM (4-6GB)

Reduce memory limits in `docker-compose.yml`:
```yaml
resources:
  limits:
    memory: 2G
  reservations:
    memory: 512M
```

### For Systems with Ample Resources (8GB+)

Increase limits for better performance:
```yaml
resources:
  limits:
    memory: 4G
    cpus: '3.0'
  reservations:
    memory: 2G
    cpus: '1.0'
```

## Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  Bambu Lab      │─────▶│  Home Assistant  │◀────▶│  Obico ML       │
│  Printer        │      │  + Integration   │      │  Server         │
│  (Camera)       │      │  + Automation    │      │  (server-mini)  │
└─────────────────┘      └──────────────────┘      └─────────────────┘
```

1. **Bambu Lab Printer** streams camera feed via integration
2. **Home Assistant** automation sends snapshots to ML server
3. **Obico ML Server** analyzes images for print failures
4. **Home Assistant** receives results and takes action (notify/pause/cancel)

## Security Considerations

1. **API Token**: Use a strong, random token for `ML_API_TOKEN`
2. **Network**: Consider using a private network or VPN if server-mini is remote
3. **Updates**: Keep the Docker image updated for security patches
4. **Firewall**: Only expose port 3333 to trusted networks

## Additional Resources

- [Main Integration Repository](https://github.com/nberktumer/ha-bambu-lab-p1-spaghetti-detection)
- [Obico Documentation](https://www.obico.io/docs/)
- [Bambu Lab Integration](https://github.com/greghesp/ha-bambulab)
- [Home Assistant Blueprints](https://www.home-assistant.io/docs/automation/using_blueprints/)

## Support

For issues specific to:
- **This setup**: Open an issue in this repository
- **The ML Server**: Check [Obico documentation](https://www.obico.io/docs/)
- **Home Assistant Integration**: Check the [integration repository](https://github.com/nberktumer/ha-bambu-lab-p1-spaghetti-detection)
- **Bambu Lab Integration**: Check the [Bambu Lab integration](https://github.com/greghesp/ha-bambulab)
