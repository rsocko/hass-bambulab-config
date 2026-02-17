# Advanced Configuration Guide

This guide covers advanced configuration scenarios for Paperless-AI with Ollama.

## Integration Scenarios

### Scenario 1: Standalone Stack

**Use Case:** Run Paperless-AI as a separate service that connects to an existing Paperless-ngx instance.

**Configuration:**
```env
# In .env
PAPERLESS_API_URL=http://your-paperless-host:8000/api
```

**Pros:**
- Easy to manage independently
- No impact on existing Paperless setup
- Can be stopped/started without affecting Paperless

**Cons:**
- Requires network connectivity between services
- Slightly higher latency

### Scenario 2: Integrated with Existing Paperless Stack

**Use Case:** Add Paperless-AI services to your existing Paperless-ngx docker-compose.yml.

**Steps:**

1. Copy the service definitions from `docker-compose.yml`
2. Add to your existing Paperless compose file:

```yaml
services:
  # Your existing paperless-ngx services...
  
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    restart: unless-stopped
    volumes:
      - ollama_data:/root/.ollama
    networks:
      - paperless

  paperless-ai:
    image: clusterzx/paperless-ai:latest
    container_name: paperless-ai
    restart: unless-stopped
    depends_on:
      - ollama
      - webserver  # Your paperless webserver service
    ports:
      - "3000:3000"
    environment:
      - PAPERLESS_API_URL=http://webserver:8000/api  # Use service name
      # ... other env vars
    networks:
      - paperless

volumes:
  ollama_data:

networks:
  paperless:
    # Use existing network
```

**Pros:**
- Single compose file to manage
- Shared network for faster communication
- Easier service discovery

**Cons:**
- Tightly coupled to Paperless stack
- Updates affect both systems

## Model Selection Guide

### By Use Case

**Document Classification (Most Common)**
```env
OLLAMA_MODEL=llama3.2        # Best all-around choice
# or
OLLAMA_MODEL=mistral         # Faster, great for English
# or
OLLAMA_MODEL=glm4            # Best accuracy (requires more RAM)
```

**Multilingual Documents**
```env
OLLAMA_MODEL=mistral         # Good German/French support
# or
OLLAMA_MODEL=glm4            # Best multilingual support
```

**Low-Resource Systems**
```env
OLLAMA_MODEL=phi3            # Minimal RAM usage
# or
OLLAMA_MODEL=tinyllama       # Fastest, least accurate
```

**High-Accuracy Processing**
```env
OLLAMA_MODEL=glm4            # Best quality
# or
OLLAMA_MODEL=mistral-small:24b  # Enterprise-grade (requires 32GB RAM)
```

### Model Comparison

| Model | Size | RAM | Speed | Accuracy | Multilingual | Best For |
|-------|------|-----|-------|----------|--------------|----------|
| **llama3.2** | 3B | 8GB | Fast | Good | ✅ | General use, default choice |
| **mistral** | 7B | 8GB | Fast | Very Good | ✅✅ | Production, multilingual |
| **phi3** | 3.8B | 4GB | Very Fast | Moderate | ❌ | Low-end hardware |
| **glm4** | 9B | 16GB | Medium | Excellent | ✅✅✅ | Best accuracy |
| **mistral-small:24b** | 24B | 32GB | Slow | Excellent | ✅✅✅ | Enterprise, high-volume |
| **tinyllama** | 1.1B | 2GB | Instant | Basic | ❌ | Testing, minimal setup |

## Custom System Prompts

### Invoice Processing

Optimize for extracting invoice information:

```env
SYSTEM_PROMPT='You are an invoice analyzer. Extract:\n1. title: Format as "Invoice XXXX - Company Name"\n2. correspondent: Company name only\n3. tags: ["invoice", "finance", relevant category]\n4. document_date: Invoice date in YYYY-MM-DD\n5. language: Document language\n\nAdditional fields:\n- invoice_number: Extract invoice number\n- total_amount: Extract total in format XX.XX\n- currency: Extract currency code\n\nReturn as structured JSON.'
```

### Receipt Processing

Optimize for retail receipts:

```env
SYSTEM_PROMPT='You are a receipt analyzer. Extract:\n1. title: Format as "Receipt - Store Name - Date"\n2. correspondent: Store/merchant name\n3. tags: ["receipt", "expense", category like "grocery", "electronics"]\n4. document_date: Purchase date in YYYY-MM-DD\n5. language: Document language\n\nFor receipts:\n- Use short store names (e.g., "Walmart" not "Walmart Inc.")\n- Tag by category (grocery, clothing, electronics, etc.)\n- Include date in title for easy sorting'
```

### Contract Processing

Optimize for legal documents:

```env
SYSTEM_PROMPT='You are a legal document analyzer. Extract:\n1. title: Contract type and parties (e.g., "Employment Contract - Company Name")\n2. correspondent: Primary party or institution\n3. tags: ["contract", "legal", contract type, urgency if renewal needed]\n4. document_date: Contract signing date in YYYY-MM-DD\n5. language: Document language\n\nFor contracts:\n- Identify contract type (employment, rental, service, etc.)\n- Extract key dates (signing, start, end if visible)\n- Note if renewal or action required'
```

## Processing Rules

### Tag-Based Processing

Process only specific document types:

```env
# Only process documents with "needs-classification" tag
PROCESS_PREDEFINED_DOCUMENTS=yes
TAGS=needs-classification

# Auto-add "ai-processed" after completion
ADD_AI_PROCESSED_TAG=yes
AI_PROCESSED_TAG_NAME=ai-processed
```

### Workflow Example

1. Document arrives in Paperless-ngx
2. Paperless-ngx consumption adds `needs-classification` tag
3. Paperless-AI detects tag and processes document
4. AI adds appropriate tags, title, correspondent
5. AI adds `ai-processed` tag to mark completion

### Multiple Processing Queues

Run multiple Paperless-AI instances with different configs:

**Instance 1: Invoices**
```env
PAPERLESS_AI_PORT=3000
TAGS=invoice-process
OLLAMA_MODEL=glm4
SYSTEM_PROMPT='...[invoice-specific prompt]...'
```

**Instance 2: Receipts**
```env
PAPERLESS_AI_PORT=3001
TAGS=receipt-process
OLLAMA_MODEL=mistral
SYSTEM_PROMPT='...[receipt-specific prompt]...'
```

## Performance Optimization

### High-Volume Processing

For processing many documents quickly:

```env
# Faster scan interval
SCAN_INTERVAL=*/10 * * * *

# Use fast model
OLLAMA_MODEL=mistral

# Process all unprocessed docs
PROCESS_PREDEFINED_DOCUMENTS=yes
TAGS=unprocessed
```

### Low-Resource Optimization

For systems with limited resources:

```env
# Slower scan interval to reduce CPU usage
SCAN_INTERVAL=0 */2 * * *

# Use lightweight model
OLLAMA_MODEL=phi3

# Disable RAG to save memory
RAG_SERVICE_ENABLED=false
```

### Batch Processing

Process documents in batches during off-hours:

```env
# Only run at night (1 AM)
SCAN_INTERVAL=0 1 * * *

# Use best model since no time pressure
OLLAMA_MODEL=glm4
```

## Network Configuration

### Using with Reverse Proxy

Example Nginx configuration:

```nginx
server {
    listen 443 ssl;
    server_name paperless-ai.example.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Update docker-compose.yml to expose only to localhost:

```yaml
paperless-ai:
  ports:
    - "127.0.0.1:3000:3000"  # Only accessible via localhost
```

### Using with Traefik

Add labels to paperless-ai service:

```yaml
paperless-ai:
  labels:
    - "traefik.enable=true"
    - "traefik.http.routers.paperless-ai.rule=Host(`paperless-ai.example.com`)"
    - "traefik.http.routers.paperless-ai.entrypoints=websecure"
    - "traefik.http.routers.paperless-ai.tls=true"
    - "traefik.http.services.paperless-ai.loadbalancer.server.port=3000"
```

## GPU Acceleration (Optional)

For faster processing on systems with NVIDIA GPUs:

1. Install NVIDIA Container Toolkit
2. Update docker-compose.yml:

```yaml
ollama:
  image: ollama/ollama:latest
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
  environment:
    - NVIDIA_VISIBLE_DEVICES=all
```

This can significantly speed up model inference (3-10x faster).

## Monitoring and Alerting

### Health Check Monitoring

Use Docker health checks with monitoring tools:

```bash
# Check health status
docker inspect paperless-ai --format='{{.State.Health.Status}}'
docker inspect ollama --format='{{.State.Health.Status}}'
```

### Integration with Home Assistant

Since this is a Home Assistant configuration repo, you can monitor Paperless-AI:

```yaml
# configuration.yaml
binary_sensor:
  - platform: rest
    name: Paperless AI Status
    resource: http://localhost:3000/
    method: GET
    scan_interval: 60
    value_template: "{{ value == 'OK' }}"

sensor:
  - platform: rest
    name: Ollama Status
    resource: http://localhost:11434/api/tags
    method: GET
    scan_interval: 300
    value_template: >
      {% if value_json.models is defined %}
        {{ value_json.models | length }} models
      {% else %}
        unavailable
      {% endif %}
```

## Security Hardening

### Additional Security Measures

```yaml
paperless-ai:
  security_opt:
    - no-new-privileges:true
    - seccomp:unconfined  # May be needed for some models
  read_only: false  # Needs write access for data directory
  tmpfs:
    - /tmp
  environment:
    - PAPERLESS_API_TOKEN=${PAPERLESS_API_TOKEN}
  secrets:
    - paperless_token

secrets:
  paperless_token:
    file: ./secrets/paperless_token.txt
```

### Network Isolation

Create isolated network for AI services:

```yaml
networks:
  ai_internal:
    internal: true  # No external access
  paperless:
    # Connected to Paperless-ngx
```

## Backup and Recovery

### Automated Backup Script

```bash
#!/bin/bash
# backup-paperless-ai.sh

BACKUP_DIR="/backups/paperless-ai"
DATE=$(date +%Y%m%d_%H%M%S)

# Create backup directory
mkdir -p "$BACKUP_DIR"

# Backup volumes
docker run --rm \
  -v paperless_ai_data:/data \
  -v "$BACKUP_DIR":/backup \
  alpine tar czf "/backup/paperless-ai-data-$DATE.tar.gz" /data

docker run --rm \
  -v ollama_data:/data \
  -v "$BACKUP_DIR":/backup \
  alpine tar czf "/backup/ollama-data-$DATE.tar.gz" /data

# Keep only last 7 backups
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +7 -delete

echo "Backup completed: $DATE"
```

### Recovery

```bash
# Restore paperless-ai data
docker run --rm \
  -v paperless_ai_data:/data \
  -v /backups/paperless-ai:/backup \
  alpine tar xzf /backup/paperless-ai-data-YYYYMMDD_HHMMSS.tar.gz -C /

# Restore ollama data
docker run --rm \
  -v ollama_data:/data \
  -v /backups/paperless-ai:/backup \
  alpine tar xzf /backup/ollama-data-YYYYMMDD_HHMMSS.tar.gz -C /
```

## Troubleshooting

### Enable Debug Logging

```env
# Add to .env
LOG_LEVEL=debug
```

Then restart and check logs:
```bash
docker-compose restart paperless-ai
docker-compose logs -f paperless-ai
```

### Common Issues and Solutions

**Issue: Documents not being processed**
```bash
# Check scan is running
docker logs paperless-ai | grep "Scanning"

# Verify tag configuration
# Documents must have the tag specified in TAGS env var

# Check Paperless API connection
docker exec paperless-ai curl -H "Authorization: Token $PAPERLESS_API_TOKEN" \
  "$PAPERLESS_API_URL/documents/"
```

**Issue: Slow model performance**
```bash
# Check model size and available RAM
docker stats ollama

# Consider switching to smaller model
# Update OLLAMA_MODEL in .env and restart
```

**Issue: RAG index not building**
```bash
# Rebuild RAG index
docker-compose restart paperless-ai

# Check logs for errors
docker logs paperless-ai | grep -i rag
```

## Additional Resources

- [Paperless-AI GitHub Discussions](https://github.com/clusterzx/paperless-ai/discussions)
- [Ollama Model Library](https://ollama.com/library)
- [Docker Compose Best Practices](https://docs.docker.com/compose/production/)
