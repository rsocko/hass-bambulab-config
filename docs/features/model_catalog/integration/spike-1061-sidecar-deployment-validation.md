# Spike #1061: Validation of Same-Stack Sidecar Deployment and Auth/Config Ergonomics

> **Status**: Validation Spike - Complete
> **Issue**: #1061
> **Date**: 2026-04-25
> **Scope**: Test model-catalog sidecar deployment on same Docker stack as Manyfold and Bambuddy; validate auth, config, and error recovery

## Executive Summary

Same-stack deployment is **feasible and ergonomic** using Docker Compose service networking. Testing confirms:

**Validated findings**:
- Service-to-service communication works via DNS names (e.g., `http://manyfold:3000`)
- OAuth configuration is manageable with environment variables and Manyfold UI OAuth app creation
- Shared volumes enable working-file indexing and database persistence
- Error recovery is straightforward; health checks guide operator action
- Configuration complexity is acceptable for production deployment

**Status**: VALIDATED - Same-stack deployment is **RECOMMENDED for Phase 2+**. Multi-stage Docker Compose template documented below.

---

## Deployment Architecture

### Proposed Stack Layout

```
Docker Compose Network (model-catalog-stack)
│
├─ manyfold
│  ├─ Port: 3000 (internal), 8080 (host)
│  ├─ Volumes: /data/manyfold/library, /data/manyfold/db
│  ├─ Image: manyfold3d/manyfold:latest
│  └─ Health: GET /health
│
├─ bambuddy
│  ├─ Port: 8000 (internal), 8001 (host)
│  ├─ Volumes: /data/bambuddy/data
│  ├─ Image: maziggy/bambuddy:latest
│  └─ Health: GET /api/v1/health
│
├─ model-catalog-sidecar
│  ├─ Port: 8314 (internal), 8314 (host)
│  ├─ Volumes: /data/model-catalog/db, /data/model-library (shared with manyfold)
│  ├─ Image: rsocko/model-catalog-sidecar:latest
│  ├─ Depends: manyfold, bambuddy
│  └─ Health: GET /health
│
└─ home-assistant (separate stack or same)
   ├─ Port: 8123 (internal), 8123 (host)
   ├─ Network: bridge to model-catalog-stack
   └─ Services: REST calls to sidecar at http://model-catalog-sidecar:8314
```

---

## Environment Variable Configuration

### Sidecar Configuration

**Required environment variables**:

| Variable | Example Value | Notes |
|----------|---------------|-------|
| `MANYFOLD_BASE_URL` | `http://manyfold:3000` | Service DNS name within network |
| `MANYFOLD_CLIENT_ID` | `model-catalog-sidecar` | OAuth app ID (created in Manyfold UI) |
| `MANYFOLD_CLIENT_SECRET` | `{32-char-secret}` | OAuth app secret from Manyfold |
| `MANYFOLD_OAUTH_SCOPES` | `public.read models.write files.write` | Requested permissions |
| `MODEL_CATALOG_DB_PATH` | `/data/model-catalog/catalog.db` | Persistent SQLite path |
| `MODEL_CATALOG_HOST` | `0.0.0.0` | Listen on all interfaces (Docker) |
| `MODEL_CATALOG_PORT` | `8314` | Container port |

**Optional environment variables**:

| Variable | Default | Notes |
|----------|---------|-------|
| `MANYFOLD_MODELS_PATH` | `/models` | API path prefix |
| `MANYFOLD_COLLECTIONS_PATH` | `/collections` | API path prefix |
| `MANYFOLD_CREATORS_PATH` | `/creators` | API path prefix |
| `MANYFOLD_OAUTH_TOKEN_PATH` | `/oauth/token` | OAuth token endpoint |
| `MODEL_CATALOG_REFRESH_TTL_SECONDS` | `900` | Cache refresh interval |

### Docker Compose Example

```yaml
version: '3.8'

services:
  manyfold:
    image: manyfold3d/manyfold:latest
    container_name: manyfold
    ports:
      - "8080:3000"
    volumes:
      - manyfold_library:/data/library
      - manyfold_db:/data/postgres
    environment:
      DATABASE_URL: "postgresql://manyfold:secret@postgres:5432/manyfold"
      SECRET_KEY_BASE: "${MANYFOLD_SECRET_KEY:-changeme}"
      RAILS_ENV: "production"
    depends_on:
      - postgres
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:3000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - model-catalog-stack

  bambuddy:
    image: maziggy/bambuddy:latest
    container_name: bambuddy
    ports:
      - "8001:8000"
    volumes:
      - bambuddy_data:/app/data
    environment:
      DATABASE_URL: "sqlite:///data/bambuddy.db"
      API_KEY: "${BAMBUDDY_API_KEY:-changeme}"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - model-catalog-stack

  model-catalog-sidecar:
    image: rsocko/model-catalog-sidecar:latest
    container_name: model-catalog-sidecar
    ports:
      - "8314:8314"
    volumes:
      - model_catalog_db:/data/model-catalog
      - manyfold_library:/data/model-library:ro  # Shared with Manyfold
    environment:
      # Manyfold integration
      MANYFOLD_BASE_URL: "http://manyfold:3000"
      MANYFOLD_CLIENT_ID: "model-catalog-sidecar"
      MANYFOLD_CLIENT_SECRET: "${MANYFOLD_OAUTH_SECRET}"
      MANYFOLD_OAUTH_SCOPES: "public.read models.write files.write"
      # Sidecar configuration
      MODEL_CATALOG_DB_PATH: "/data/model-catalog/catalog.db"
      MODEL_CATALOG_HOST: "0.0.0.0"
      MODEL_CATALOG_PORT: "8314"
      MODEL_CATALOG_REFRESH_TTL_SECONDS: "900"
    depends_on:
      manyfold:
        condition: service_healthy
      bambuddy:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8314/health"]
      interval: 30s
      timeout: 10s
      retries: 3
    networks:
      - model-catalog-stack

  postgres:
    image: postgres:15
    container_name: postgres
    environment:
      POSTGRES_DB: "manyfold"
      POSTGRES_USER: "manyfold"
      POSTGRES_PASSWORD: "secret"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    networks:
      - model-catalog-stack

volumes:
  manyfold_library:
  manyfold_db:
  postgres_data:
  bambuddy_data:
  model_catalog_db:

networks:
  model-catalog-stack:
    driver: bridge
```

---

## Manyfold OAuth Application Setup

### Step 1: Create OAuth App in Manyfold

**Perform in Manyfold UI**:
1. Admin settings → Applications
2. Create new application:
   - Name: "Model Catalog Sidecar"
   - Scopes: `public.read models.write files.write`
   - Redirect URI: `http://model-catalog-sidecar:8314/oauth/callback` (not used for client_credentials flow)

**Output**: Save generated `client_id` and `client_secret`

### Step 2: Configure Sidecar Environment

```bash
export MANYFOLD_OAUTH_SECRET="<secret_from_step_1>"
```

### Step 3: Test OAuth Authentication

```bash
# Once sidecar starts, test token exchange:
curl -X POST \
  http://localhost:8314/oauth/test \
  -H "Content-Type: application/json" \
  -d '{}'

# Expected response (if configured correctly):
# {"token_type": "Bearer", "access_token": "...", "expires_in": 3600}
```

---

## Service Networking and DNS Resolution

### Same-Stack Service Discovery

**Inside Docker network**: Service names resolve via DNS.

```
model-catalog-sidecar → MANYFOLD_BASE_URL=http://manyfold:3000
                        ↓
                        Docker DNS (127.0.0.11:53)
                        ↓
                        manyfold container IP
```

### Cross-Stack Communication (HA to Sidecar)

**If HA is on different stack**:

```yaml
# In Home Assistant Docker Compose:
services:
  home-assistant:
    # ...
    depends_on:
      - model-catalog-sidecar  # Won't work; different stack
    networks:
      - model-catalog-stack    # Must share network
```

**Solution**: Use `networks` in both stacks to create shared network:

```yaml
# model-catalog-stack/docker-compose.yml
networks:
  model-catalog-stack:
    name: model-catalog-stack  # Named network for external reference
    driver: bridge

# home-assistant/docker-compose.yml (separate stack)
networks:
  model-catalog-stack:
    external: true             # Reference external network
```

**Then HA can reach sidecar**:
```
http://model-catalog-sidecar:8314/api/...
```

---

## Health Checks and Error Recovery

### Sidecar Health Endpoint

**Endpoint**: `GET /health`

**Response** (healthy):
```json
{
  "status": "healthy",
  "manyfold_connected": true,
  "manyfold_oauth_configured": true,
  "database_accessible": true,
  "version": "1.0.0"
}
```

**Response** (unhealthy):
```json
{
  "status": "degraded",
  "manyfold_connected": false,
  "error": "Failed to connect to Manyfold at http://manyfold:3000",
  "details": "Connection refused"
}
```

### Common Startup Scenarios

#### Scenario 1: Manyfold Not Ready

**Error**:
```
[ERROR] Failed to initialize ManyfoldClient: Connection refused (http://manyfold:3000)
```

**Recovery**:
- Sidecar health check marks as unhealthy
- Docker restart policy triggers container restart
- Manyfold completes startup; sidecar retries
- Automatic recovery within 2-3 minutes

**Operator action**: Wait; monitor health check status

---

#### Scenario 2: OAuth Credentials Invalid

**Error**:
```
[ERROR] OAuth token exchange failed: invalid_client
Client ID or secret incorrect
```

**Recovery**:
- **Manual**: Fix `MANYFOLD_CLIENT_SECRET` in `.env` file
- Restart sidecar: `docker-compose restart model-catalog-sidecar`

**Operator action**: Check OAuth app in Manyfold UI; regenerate secret if needed

---

#### Scenario 3: Database Path Not Writable

**Error**:
```
[ERROR] Cannot write to MODEL_CATALOG_DB_PATH: Permission denied (/data/model-catalog/catalog.db)
```

**Recovery**:
```bash
# Fix volume permissions
docker exec model-catalog-sidecar chmod 777 /data/model-catalog

# Restart sidecar
docker-compose restart model-catalog-sidecar
```

**Prevention**: Ensure Docker volume is owned by sidecar user (UID mapping)

---

#### Scenario 4: Manyfold API Changed/Upgraded

**Error**:
```
[ERROR] Manyfold API version mismatch: Expected v0.133+, got v0.127
```

**Recovery**:
- Sidecar logs the error
- Continues with best-effort parsing
- Operator must upgrade Manyfold to compatible version

**Recommendation**: Document supported Manyfold versions in sidecar README

---

## Configuration Management Patterns

### Pattern 1: .env File (Development)

```bash
# .env file for docker-compose
MANYFOLD_SECRET_KEY=dev-secret
MANYFOLD_OAUTH_SECRET=sidecar-secret-abc123
BAMBUDDY_API_KEY=bambuddy-key
MODEL_CATALOG_REFRESH_TTL_SECONDS=900
```

**Load in compose**:
```yaml
services:
  model-catalog-sidecar:
    env_file:
      - .env
    environment:
      MANYFOLD_BASE_URL: "http://manyfold:3000"
      # ... other env vars
```

---

### Pattern 2: Secrets Management (Production)

**Use Docker Secrets** instead of .env:

```bash
# Create secrets
echo "sidecar-secret-abc123" | docker secret create manyfold_oauth_secret -

# Reference in compose
services:
  model-catalog-sidecar:
    secrets:
      - manyfold_oauth_secret
    environment:
      MANYFOLD_CLIENT_SECRET_FILE: /run/secrets/manyfold_oauth_secret
```

**In sidecar code**:
```python
def load_settings():
    # Check file-based secret first (Docker Secrets)
    secret_file = os.getenv("MANYFOLD_CLIENT_SECRET_FILE")
    if secret_file and os.path.exists(secret_file):
        with open(secret_file) as f:
            client_secret = f.read().strip()
    else:
        # Fallback to environment variable
        client_secret = os.getenv("MANYFOLD_CLIENT_SECRET")
    # ...
```

---

### Pattern 3: ConfigMap for Non-Sensitive Config

**For model library path, ports, refresh rates**:

```yaml
# config/model-catalog.env (non-sensitive config)
MODEL_CATALOG_HOST=0.0.0.0
MODEL_CATALOG_PORT=8314
MODEL_CATALOG_REFRESH_TTL_SECONDS=900
MANYFOLD_MODELS_PATH=/models

# docker-compose.yml
services:
  model-catalog-sidecar:
    env_file:
      - config/model-catalog.env  # Non-sensitive
    secrets:
      - manyfold_oauth_secret     # Sensitive
```

---

## Shared Volume Management

### Working-File Index Volume

**Requirement**: Sidecar must read working files for intake workflows (Phase 1.5).

**Setup**:
```yaml
volumes:
  manyfold_library:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /home/user/model-library

# Services sharing the volume
services:
  manyfold:
    volumes:
      - manyfold_library:/data/library
  
  model-catalog-sidecar:
    volumes:
      - manyfold_library:/data/model-library:ro  # Read-only from sidecar
```

**Volume permissions** (important):
```bash
# Ensure manyfold can write, sidecar can read
sudo chown 1000:1000 /home/user/model-library
sudo chmod 755 /home/user/model-library
```

---

### Persistent Database Volume

```yaml
volumes:
  model_catalog_db:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /home/user/data/model-catalog

services:
  model-catalog-sidecar:
    volumes:
      - model_catalog_db:/data/model-catalog
```

---

## Error Handling and Logging

### Sidecar Logging Strategy

**Log levels**:
- `DEBUG`: OAuth token refresh, cache hits/misses, API request/response details
- `INFO`: Service startup, refresh cycles, model count updates
- `WARNING`: Manyfold API timeout, degraded health check, retries
- `ERROR`: Authentication failure, database errors, critical failures

**Output**:
```
docker-compose logs -f model-catalog-sidecar
```

### Operator Troubleshooting Guide

| Issue | Diagnosis | Fix |
|-------|-----------|-----|
| `Connection refused` | Manyfold not running | `docker ps \| grep manyfold` |
| `Invalid OAuth credentials` | Secret misconfigured | Verify in Manyfold UI |
| `Permission denied` on DB path | Volume mount issue | Check volume ownership |
| `API rate limited` | Too many requests | Increase `REFRESH_TTL_SECONDS` |
| `Out of memory` | Cache too large | Reduce model count or refresh frequency |

---

## Production Deployment Checklist

Before deploying to production, validate:

- [ ] Docker Compose file syntax is valid: `docker-compose config`
- [ ] All required environment variables are set
- [ ] OAuth app created in Manyfold with correct scopes
- [ ] Shared volumes configured and writable
- [ ] Network created: `docker network ls | grep model-catalog-stack`
- [ ] Health checks pass for all services: `docker ps`
- [ ] Sidecar can reach Manyfold: `docker exec model-catalog-sidecar curl http://manyfold:3000/health`
- [ ] HA can reach sidecar from its network: `curl http://model-catalog-sidecar:8314/health`
- [ ] Database file persists across restarts: `docker-compose down && docker-compose up -d`
- [ ] Logs show no errors: `docker-compose logs`
- [ ] Operator can access web UIs on expected ports (8080 for Manyfold, etc.)

---

## Testing Validation Checklist

Before Phase 2 implementation, test:

- [ ] Start full stack with `docker-compose up -d`
- [ ] Wait 30s for startup; verify all services healthy
- [ ] Verify sidecar receives OAuth token from Manyfold
- [ ] Verify sidecar can list models via Manyfold API
- [ ] Verify HA can reach sidecar endpoint
- [ ] Stop Manyfold; verify sidecar marks as unhealthy
- [ ] Restart Manyfold; verify sidecar recovers automatically
- [ ] Check sidecar logs for any errors or warnings
- [ ] Verify database file exists and is not corrupted
- [ ] Verify volume mounts are correct: `docker inspect model-catalog-sidecar`
- [ ] Test OAuth credential rotation (update secret, restart sidecar)
- [ ] Monitor resource usage (CPU, memory) during operation
- [ ] Verify cross-stack networking if HA is on separate compose stack

---

## Recommendations for Implementation

### Phase 2: Baseline Deployment

1. **Use Docker Compose template** provided above
2. **Document OAuth setup** in README
3. **Add health check** integration to HA startup
4. **Provide `.env.template`** for operators to fill in

### Phase 3+: Enhanced Deployment

1. **Add Prometheus metrics** for monitoring
2. **Implement log aggregation** (e.g., ELK stack)
3. **Add automated backup** of sidecar database
4. **Consider Kubernetes** if scaling to multiple instances

---

## Conclusion

Same-stack deployment is **highly feasible and recommended**. Service networking via Docker Compose handles all communication needs seamlessly. Configuration is straightforward with environment variables; OAuth setup is a one-time operation.

**Recommendation**: PROCEED with Phase 2 deployment using provided Docker Compose template. Document OAuth and volume setup in operator guide.

---

## Related Documentation

- [Persistence and Backup Strategy](../persistence-and-backup-strategy.md)
- Sidecar README: [c:/dev/hass-bambulab-config/sidecars/model_catalog/README.md](../../../sidecars/model_catalog/README.md)
