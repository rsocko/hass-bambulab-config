# Syslog Integration for Home Assistant Logs

## Overview

Forward Home Assistant logs to a traditional syslog server using standard syslog protocol. This is ideal for environments with existing syslog infrastructure.

## Architecture

```
Home Assistant → Syslog Forwarder → Syslog Server
   (Generates)      (Ships)           (Stores)
```

## Methods

### Method 1: rsyslog (Recommended for Linux)

#### Installation

**Ubuntu/Debian**:
```bash
sudo apt-get update
sudo apt-get install rsyslog
```

**RHEL/CentOS**:
```bash
sudo yum install rsyslog
```

**Home Assistant OS**:
Use the Syslog addon from Add-on Store.

#### Configuration

Create `/etc/rsyslog.d/homeassistant.conf`:

```conf
# Monitor Home Assistant log file
module(load="imfile" PollingInterval="10")

# Input for home-assistant.log
input(type="imfile"
      File="/config/home-assistant.log"
      Tag="homeassistant"
      Severity="info"
      Facility="local0")

# Forward to remote syslog server
*.* @@remote-syslog-server:514

# Or write to local file
if $programname == 'homeassistant' then /var/log/homeassistant-remote.log
& stop
```

#### Restart rsyslog

```bash
sudo systemctl restart rsyslog
sudo systemctl status rsyslog
```

### Method 2: syslog-ng

#### Installation

```bash
sudo apt-get install syslog-ng
```

#### Configuration

Add to `/etc/syslog-ng/syslog-ng.conf`:

```conf
# Source: Home Assistant log file
source s_homeassistant {
    file("/config/home-assistant.log"
         follow-freq(1)
         program-override("homeassistant")
         flags(no-parse));
};

# Destination: Remote syslog server
destination d_remote {
    syslog("remote-syslog-server" 
           port(514) 
           transport("tcp"));
};

# Destination: Local file
destination d_local {
    file("/var/log/homeassistant.log");
};

# Log path
log {
    source(s_homeassistant);
    destination(d_remote);
    destination(d_local);
};
```

#### Restart syslog-ng

```bash
sudo systemctl restart syslog-ng
sudo systemctl status syslog-ng
```

### Method 3: Docker Container

#### Using rsyslog Docker container

Create `docker-compose.yml`:

```yaml
version: '3.8'

services:
  rsyslog-forwarder:
    image: rsyslog/syslog_appliance_alpine:latest
    container_name: ha-syslog-forwarder
    volumes:
      - /path/to/homeassistant/config:/config:ro
      - ./rsyslog.conf:/etc/rsyslog.conf:ro
    networks:
      - logging
    restart: unless-stopped

networks:
  logging:
    driver: bridge
```

Create `rsyslog.conf`:

```conf
module(load="imfile")

input(type="imfile"
      File="/config/home-assistant.log"
      Tag="homeassistant"
      Severity="info"
      Facility="local0")

*.* @@your-syslog-server:514
```

Start container:
```bash
docker-compose up -d
```

## Syslog Server Options

### Option 1: Local Syslog Server

**Install syslog server**:
```bash
sudo apt-get install rsyslog
```

**Configure to receive logs** (`/etc/rsyslog.conf`):
```conf
# Enable TCP reception
module(load="imtcp")
input(type="imtcp" port="514")

# Enable UDP reception
module(load="imudp")
input(type="imudp" port="514")

# Store Home Assistant logs separately
if $programname == 'homeassistant' then /var/log/homeassistant/homeassistant.log
& stop
```

**Restart rsyslog**:
```bash
sudo systemctl restart rsyslog
```

### Option 2: Graylog

**Setup**:
1. Install Graylog (Docker or standalone)
2. Create Syslog TCP input on port 514
3. Configure rsyslog to forward to Graylog
4. Create extractors for Home Assistant log format

**Graylog Input Configuration**:
- Type: Syslog TCP
- Port: 514
- Bind address: 0.0.0.0

### Option 3: Splunk

**Setup**:
1. Install Splunk Universal Forwarder on HA host
2. Configure to monitor `/config/home-assistant.log`
3. Forward to Splunk indexer

**Universal Forwarder Config** (`inputs.conf`):
```conf
[monitor:///config/home-assistant.log]
disabled = false
index = homeassistant
sourcetype = homeassistant:log
```

### Option 4: Papertrail

**Setup**:
1. Sign up for Papertrail account
2. Get log destination (e.g., `logsN.papertrailapp.com:XXXXX`)
3. Configure rsyslog to forward

**rsyslog configuration**:
```conf
*.* @@logs5.papertrailapp.com:12345
```

## Log Format Parsing

### Standard Home Assistant Format

```
YYYY-MM-DD HH:MM:SS LEVEL (Thread) [logger.name] message
```

### Example Parsing Rules

#### For Graylog Extractors

**Extractor 1: Timestamp**:
- Type: Regex
- Field: `message`
- Pattern: `^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})`
- Name: `timestamp`

**Extractor 2: Level**:
- Type: Regex
- Field: `message`
- Pattern: `^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} (\w+)`
- Name: `level`

**Extractor 3: Logger**:
- Type: Regex
- Field: `message`
- Pattern: `\[(.*?)\]`
- Name: `logger`

#### For Splunk

Create `props.conf`:
```conf
[homeassistant:log]
EXTRACT-timestamp = ^(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})
EXTRACT-level = ^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} (?P<level>\w+)
EXTRACT-thread = \((?P<thread>[^)]+)\)
EXTRACT-logger = \[(?P<logger>[^\]]+)\]
EXTRACT-message = \] (?P<log_message>.*)$
```

## Security

### TLS/SSL Configuration

**rsyslog with TLS**:

1. Generate certificates or use existing ones

2. Configure rsyslog client (`/etc/rsyslog.d/tls.conf`):
```conf
global(
    DefaultNetstreamDriver="gtls"
    DefaultNetstreamDriverCAFile="/etc/ssl/ca.pem"
    DefaultNetstreamDriverCertFile="/etc/ssl/cert.pem"
    DefaultNetstreamDriverKeyFile="/etc/ssl/key.pem"
)

*.* @@remote-server:6514
```

3. Configure rsyslog server to accept TLS:
```conf
module(load="imtcp" 
       StreamDriver.Name="gtls"
       StreamDriver.Mode="1"
       StreamDriver.Authmode="anon")

input(type="imtcp" port="6514")
```

### Authentication

**Using stunnel for TLS**:

```bash
sudo apt-get install stunnel4
```

Configure `/etc/stunnel/stunnel.conf`:
```conf
[syslog-tls]
client = yes
accept = 127.0.0.1:601
connect = remote-server:6514
cert = /etc/stunnel/cert.pem
key = /etc/stunnel/key.pem
```

Update rsyslog to forward to stunnel:
```conf
*.* @@127.0.0.1:601
```

## Filtering

### Filter by Log Level

**rsyslog**:
```conf
# Only errors and critical
if $syslogseverity-text == 'ERROR' or $syslogseverity-text == 'CRITICAL' then @@remote:514
& stop
```

### Filter by Component

**rsyslog**:
```conf
# Only Bambu Lab logs
if $msg contains 'bambulab' then @@remote:514
& stop
```

### Combined Filters

```conf
# Only Bambu Lab errors
if $msg contains 'bambulab' and $syslogseverity-text == 'ERROR' then {
    @@remote:514
    stop
}
```

## Monitoring

### Check syslog forwarding

**Test with logger command**:
```bash
logger -t homeassistant "Test message from Home Assistant"
```

**Check local logs**:
```bash
tail -f /var/log/syslog | grep homeassistant
```

**Check remote logs**:
```bash
ssh remote-server "tail -f /var/log/homeassistant.log"
```

### Troubleshooting

**Logs not forwarding**:
1. Check rsyslog is running: `systemctl status rsyslog`
2. Check configuration: `rsyslogd -N1`
3. Check firewall: `sudo ufw allow 514/tcp`
4. Test connectivity: `telnet remote-server 514`
5. Check rsyslog logs: `journalctl -u rsyslog -f`

**Permission issues**:
```bash
# Give rsyslog permission to read HA logs
sudo usermod -aG homeassistant syslog
sudo chmod 644 /config/home-assistant.log
```

**Disk space issues**:
Configure log rotation in `/etc/logrotate.d/homeassistant`:
```conf
/var/log/homeassistant/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 0640 syslog adm
    postrotate
        systemctl reload rsyslog > /dev/null 2>&1 || true
    endscript
}
```

## Example Queries

### Search for Errors

**Graylog**:
```
source:homeassistant AND level:ERROR
```

**Splunk**:
```
index=homeassistant level=ERROR
```

**Grep (local file)**:
```bash
grep "ERROR" /var/log/homeassistant.log
```

### Find Specific Operations

**Graylog**:
```
source:homeassistant AND message:*Print Complete*
```

**Splunk**:
```
index=homeassistant "Print Complete"
```

## Performance Tuning

### Batch Processing

**rsyslog queue**:
```conf
$ActionQueueType LinkedList
$ActionQueueFileName homeassistant
$ActionResumeRetryCount -1
$ActionQueueSaveOnShutdown on
$ActionQueueMaxDiskSpace 1g
```

### Rate Limiting

```conf
$SystemLogRateLimitInterval 60
$SystemLogRateLimitBurst 1000
```

## Resources

- [rsyslog Documentation](https://www.rsyslog.com/doc/)
- [syslog-ng Documentation](https://www.syslog-ng.com/technical-documents/doc/syslog-ng-open-source-edition/)
- [Graylog Syslog Input](https://docs.graylog.org/docs/syslog)
- [Splunk Universal Forwarder](https://docs.splunk.com/Documentation/Forwarder/)
- [RFC 5424: Syslog Protocol](https://tools.ietf.org/html/rfc5424)
