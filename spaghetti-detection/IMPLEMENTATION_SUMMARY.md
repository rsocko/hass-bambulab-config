# Spaghetti Detection - Implementation Summary

## Overview

This implementation provides a complete spaghetti detection system for Bambu Lab 3D printers using the Obico ML Server and Home Assistant integration. The system can automatically detect print failures in real-time and take corrective actions.

## What Was Implemented

### 1. Docker Infrastructure (`docker-compose.yml`)

**Obico ML Server Container**:
- Image: `nberk/ha_bambu_lab_p1_spaghetti_detection_standalone:latest`
- Port: 3333 (exposed to network)
- Resource Limits:
  - Memory: 3GB max, 1GB reserved
  - CPU: 2 cores max, 0.5 cores reserved
- Health Check: Every 30 seconds via `/health` endpoint
- Logging: JSON with 10MB rotation, 3 files max
- Restart Policy: `unless-stopped` for resilience

**Why These Settings**:
- 3GB memory limit: Obico ML needs minimum 4GB system RAM; 3GB container limit provides headroom
- CPU limits prevent resource starvation on shared host
- Health checks enable automated monitoring and recovery
- Log rotation prevents disk space issues

### 2. Configuration Management

**Environment File (`.env.example`)**:
- `ML_API_TOKEN`: Authentication token (should be regenerated per deployment)
- `TZ`: Timezone for container logs and scheduling

**Security Best Practices**:
- `.gitignore` prevents committing sensitive `.env` file
- Example file provides template
- Token generation via `openssl rand -hex 32`

### 3. Automated Deployment (`deploy.sh`)

**Features**:
- Prerequisites checking (Docker, Docker Compose, memory)
- Automatic token generation
- Environment file creation
- Container health verification
- Resource monitoring
- User guidance for next steps

**Usage**:
```bash
cd ~/bambulab/spaghetti-detection
./deploy.sh
```

### 4. Comprehensive Documentation

#### Main README (`README.md`)
- Complete installation guide
- Prerequisites and compatibility
- Architecture diagram
- Configuration instructions
- Security considerations
- Maintenance procedures

#### Quick Start Guide (`QUICK_START.md`)
- 15-minute setup process
- Testing procedures
- Configuration examples
- Common operations
- Mobile app setup

#### Monitoring Guide (`MONITORING.md`)
- Built-in Docker monitoring
- Home Assistant sensor integration
- Prometheus/Grafana setup
- Alert thresholds
- Performance metrics

#### Troubleshooting Guide (`TROUBLESHOOTING.md`)
- Common issues and solutions
- Diagnostic commands
- Performance troubleshooting
- Debug report script
- Testing tools

### 5. Home Assistant Integration

#### Sensors (`examples/sensors.yaml`)
- Health status monitoring
- Memory usage tracking
- CPU utilization monitoring
- Container status checking

#### Automations (`examples/automations.yaml`)
- Offline/online alerts
- High resource usage warnings
- Automatic restart on unhealthy state
- Daily health checks
- Performance throttling warnings

#### Dashboard (`examples/lovelace_card.yaml`)
- Status overview card
- Resource usage gauges
- Quick action buttons
- Alternative Mushroom card implementation

#### Blueprint (`spaghetti_detection_blueprint.yaml`)
- Configurable detection automation
- Printer selection
- Notification settings
- Action on detection (notify/pause/cancel)
- Detection interval and confidence threshold

## Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  Bambu Lab      │─────▶│  Home Assistant  │◀────▶│  Obico ML       │
│  Printer        │      │  + Integration   │      │  Server         │
│  (Camera)       │      │  + Automation    │      │  (server-mini)  │
└─────────────────┘      └──────────────────┘      └─────────────────┘
                                                             │
                                                             ▼
                                                    ┌─────────────────┐
                                                    │  Monitoring     │
                                                    │  - Docker Stats │
                                                    │  - Health Check │
                                                    │  - HA Sensors   │
                                                    └─────────────────┘
```

## Workflow

1. **Print Starts**: Bambu Lab printer begins printing
2. **Automation Triggers**: Home Assistant automation activates
3. **Snapshot Capture**: Camera snapshot taken at regular intervals
4. **ML Analysis**: Image sent to Obico ML Server for analysis
5. **Detection Result**: ML server returns confidence score
6. **Action Taken**: Based on confidence and configuration:
   - Notify user (always)
   - Pause print (if configured)
   - Cancel print (if configured)
7. **Monitoring**: Resource usage and health tracked continuously

## Resource Requirements

### Minimum (server-mini)
- 4GB RAM total
- 2 CPU cores
- 10GB disk space
- Network connectivity to Home Assistant

### Recommended
- 8GB RAM
- 4 CPU cores
- 20GB disk space
- Wired network connection

## Key Configuration Points

### On server-mini:
1. API Token (in `.env`)
2. Timezone (in `.env`)
3. Resource limits (in `docker-compose.yml`)

### In Home Assistant:
1. Integration configuration:
   - Host: `http://server-mini:3333`
   - Token: matches `.env` file
2. Automation configuration:
   - Detection interval (default: 30s)
   - Confidence threshold (default: 80%)
   - Action on detection
   - Notification settings

## Monitoring Strategy

### Real-time Monitoring
- `docker stats obico-ml-server` - Live resource usage
- `docker compose logs -f` - Live logs
- Health endpoint: `http://server-mini:3333/health`

### Home Assistant Monitoring
- Sensor: `sensor.obico_ml_server_status`
- Binary Sensor: `binary_sensor.obico_ml_server_healthy`
- Alert automations for offline, high memory, high CPU

### Optional Advanced Monitoring
- Prometheus + cAdvisor for metrics
- Grafana for visualization
- Loki + Promtail for log aggregation

## Maintenance Operations

### Daily
- Automated health checks via HA automation

### Weekly
- Review alert history
- Check resource trends

### Monthly
- Review and adjust detection settings
- Update Docker image: `docker compose pull && docker compose up -d`

### As Needed
- Restart container: `docker compose restart`
- View logs: `docker compose logs --tail=100`
- Check resources: `docker stats obico-ml-server`

## Security Considerations

1. **API Token**: 
   - Use strong random token
   - Keep `.env` file secure
   - Never commit to git

2. **Network**:
   - Keep on private network
   - Consider firewall rules
   - Only expose port 3333 to trusted hosts

3. **Updates**:
   - Keep Docker image updated
   - Monitor for security advisories
   - Test updates in non-production first

## Future Enhancements

### Possible Improvements
1. **Multiple Camera Support**: Detect from different angles
2. **Detection History**: Track accuracy over time
3. **Custom Training**: Train model on your specific prints
4. **Integration with Spoolman**: Link failures to filament types
5. **Advanced Notifications**: Include detection images in alerts
6. **Predictive Analysis**: Warn before failure occurs
7. **Dashboard Integration**: Show detection status on main dashboard
8. **Time-based Rules**: Disable detection during certain hours

### Integration Opportunities
1. **WLED Integration**: Visual alert on detection
2. **TTS Announcements**: Voice alerts
3. **Discord/Telegram**: Remote notifications
4. **Print Completion**: Include detection stats in print summary

## Testing Checklist

Before considering deployment complete:

- [ ] Docker container starts successfully
- [ ] Health endpoint responds
- [ ] Home Assistant integration installed
- [ ] Integration connects to ML server
- [ ] Automation blueprint imported
- [ ] Automation created and enabled
- [ ] Test notification received
- [ ] Monitoring sensors working
- [ ] Alert automations tested
- [ ] Documentation reviewed
- [ ] Backup configuration saved

## Known Limitations

1. **Hardware Requirements**: Minimum 4GB RAM on host
2. **Network Latency**: Detection speed depends on network
3. **False Positives**: May occur depending on configuration
4. **Camera Quality**: Better camera = better detection
5. **First Layer**: May trigger false positives during first layer
6. **Material Types**: Some materials harder to detect than others

## Troubleshooting Quick Reference

| Issue | Quick Fix |
|-------|-----------|
| Container won't start | Check port 3333 not in use |
| Connection refused | Verify firewall, hostname resolution |
| Authentication failed | Ensure token matches everywhere |
| High memory | Reduce detection frequency |
| No detection | Check automation is enabled |
| False positives | Increase confidence threshold |

## Support Resources

- **Main Repository**: This repository
- **Integration Repository**: [nberktumer/ha-bambu-lab-p1-spaghetti-detection](https://github.com/nberktumer/ha-bambu-lab-p1-spaghetti-detection)
- **Obico Documentation**: [obico.io/docs](https://www.obico.io/docs/)
- **Bambu Lab Integration**: [greghesp/ha-bambulab](https://github.com/greghesp/ha-bambulab)

## Conclusion

This implementation provides a production-ready spaghetti detection system with:
- ✅ Automated deployment
- ✅ Comprehensive monitoring
- ✅ Detailed documentation
- ✅ Example configurations
- ✅ Troubleshooting guides
- ✅ Security best practices

The system is designed to be maintainable, monitorable, and extensible for future enhancements.

---

**Implemented by**: GitHub Copilot Agent  
**Date**: February 17, 2026  
**Version**: 1.0
