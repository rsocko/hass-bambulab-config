# Phase 3 Deployment Configuration & Environment Setup

**Last Updated:** April 25, 2026

## Production Deployment

### Sidecar Service

**Location:** https://model-catalog.socko.us  
**Type:** Docker container (FastAPI + SQLite)  
**Status:** ✅ Running  

**Environment Variables (from `.env`):**
```env
MODEL_CATALOG_IMAGE_TAG=0.1.0
MANYFOLD_BASE_URL=http://manyfold:3214
MANYFOLD_MODELS_PATH=/models
MANYFOLD_CLIENT_ID=<oauth-client-id>
MANYFOLD_CLIENT_SECRET=<oauth-client-secret>
MANYFOLD_OAUTH_SCOPES=public read
MODEL_CATALOG_REFRESH_TTL_SECONDS=900
```

**Database:** `/data/model_catalog.db` (SQLite)

**Configuration Files:**
- [sidecars/model_catalog/Dockerfile](sidecars/model_catalog/Dockerfile)
- [sidecars/model_catalog/README.md](sidecars/model_catalog/README.md)

**Build & Deploy:**
```bash
# Build locally
docker build \
  -f sidecars/model_catalog/Dockerfile \
  -t registry.socko.us/model-catalog-sidecar:0.2.0 \
  .

# Push to registry
docker push registry.socko.us/model-catalog-sidecar:0.2.0

# Update compose and deploy
docker compose pull && docker compose up -d
```

### Home Assistant Integration

**Location:** http://192.168.1.5:8123  
**Package:** 3d_printing/model_catalog  
**Status:** ✅ Wired

**Key Files:**
```
homeassistant/packages/3d_printing/model_catalog/
├── model_catalog_loader.yaml           # Package loader
├── services.yaml                        # Service definitions
├── rest_commands.yaml                   # REST endpoints
├── automations.yaml                     # Triggers
├── scripts/
│   ├── model_catalog_accept_and_notify.yaml
│   └── (add: archive_link_model.yaml for Phase 3.3)
├── automations/
│   ├── example_open_detail_popup.yaml
│   ├── model_catalog_on_link_accepted.yaml
│   └── (add: link_archive_on_print_complete.yaml for Phase 3.3)
├── helpers/
│   └── input_text/
├── dashboard_views/
│   └── model_catalog.yaml
└── rest_commands/
    └── (individual command YAML files)
```

**Dashboard Resources:**
```yaml
# File: homeassistant/packages/3d_printing/common/dashboards/_resources.yaml
- url: /local/3d_printing/model_catalog/model-catalog-browser-card.js?v=6
  type: module

# Phase 3.2 additions:
- url: /local/3d_printing/model_catalog/geometry-parser.js?v=1
  type: module
- url: /local/3d_printing/model_catalog/viewer.js?v=1
  type: module
- url: /local/3d_printing/model_catalog/build-volume.js?v=1
  type: module
- url: /local/3d_printing/model_catalog/controls.js?v=1
  type: module
- url: /local/3d_printing/model_catalog/model-detail-3d-viewer.js?v=1
  type: module

# Phase 3.3 additions:
- url: /local/3d_printing/model_catalog/model-statistics-card.js?v=1
  type: module
```

**Important:** After code changes, increment resource version numbers (e.g., `?v=7` → `?v=8`) for cache busting.

---

## Development Environment Setup

### Local Testing (Phase 3.2-3.3)

#### Prerequisites
```bash
# Python 3.10+
python --version

# Virtual environment (already set up)
source .venv/Scripts/activate  # Windows
# or
source .venv/bin/activate      # Linux/Mac

# Install dependencies
pip install -r requirements-dev.txt
```

#### Running Tests
```bash
# All Phase 3 tests
pytest tests/phase3/ -v

# Specific phase
pytest tests/phase3/test_phase3_2_3d_viewer.py -v

# With coverage
pytest tests/phase3/ --cov=sidecars/model_catalog --cov-report=html

# Run integration tests
python test_phase3_endpoints.py
```

#### Building Sidecar Locally
```bash
# Build Docker image
docker build \
  -f sidecars/model_catalog/Dockerfile \
  -t model-catalog-sidecar:dev \
  .

# Run locally
docker run -p 8090:8000 \
  -e MANYFOLD_BASE_URL=http://host.docker.internal:3214 \
  -v $(pwd)/sidecars/model_catalog/data:/data \
  model-catalog-sidecar:dev
```

#### Local Sidecar Testing
```bash
# Test endpoint
curl -X GET http://localhost:8090/api/models/gridfinity-bin

# Check health
curl http://localhost:8090/health

# View diagnostics
curl http://localhost:8090/diagnostics
```

### JavaScript Development (Phase 3.2-3.3)

#### IDE Setup
```bash
# Install Node.js modules (if needed for linting)
npm install --save-dev eslint prettier

# Format code
npx prettier --write homeassistant/www/3d_printing/model_catalog/*.js

# Lint
npx eslint homeassistant/www/3d_printing/model_catalog/*.js
```

#### Testing JavaScript Components
```bash
# Copy files to Home Assistant
cp homeassistant/www/3d_printing/model_catalog/*.js /path/to/config/www/

# Reload dashboard
# Visit http://192.168.1.5:8123/3d-printing/model-catalog
# Press F12 (Developer Console)
# Check for errors
```

#### Three.js Setup
```bash
# Option 1: Use CDN (in _resources.yaml)
- url: https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js
  type: js

# Option 2: Install via npm
npm install three

# Option 3: Use HACS (Home Assistant Community Store)
# Add custom repository: https://github.com/besnow/threejs-hacs
```

---

## Testing & Validation

### Phase 3.2 Validation Checklist

#### Unit Tests
```bash
pytest tests/phase3/test_phase3_2_3d_viewer.py::TestSTLLoader -v
pytest tests/phase3/test_phase3_2_3d_viewer.py::TestGeometryRendering -v
pytest tests/phase3/test_phase3_2_3d_viewer.py::TestBuildVolumeVisualization -v
pytest tests/phase3/test_phase3_2_3d_viewer.py::TestCameraControls -v
```

#### Integration Tests
1. Open Model Catalog dashboard
2. Click any model with STL file
3. Verify:
   - [ ] 3D viewer loads without errors
   - [ ] Model geometry displays correctly
   - [ ] Camera auto-fits on load
   - [ ] Mouse rotate/zoom works
   - [ ] Build volume shows (space key toggle)
   - [ ] Fit message displays (✅ or ⚠️)
   - [ ] Keyboard shortcuts work (R=reset, Space=volume)

#### Performance Tests
- Large model (1MB+): Load within 2 seconds
- 500k triangles: Render without lag
- Memory usage: < 100MB for single viewer

### Phase 3.3 Validation Checklist

#### Unit Tests
```bash
pytest tests/phase3/test_phase3_3_cross_system.py -v
```

#### Integration Tests
1. Complete a print to get archive
2. Verify:
   - [ ] Archive linked to correct model
   - [ ] Recommendations display
   - [ ] Statistics show correct values
   - [ ] Export generates valid files

#### API Tests
```bash
# Test archive linking
curl https://model-catalog.socko.us/api/archives/12345/model

# Test related models
curl https://model-catalog.socko.us/api/models/gridfinity-bin/related

# Test recommendations
curl https://model-catalog.socko.us/api/recommendations?strategy=next_steps

# Test statistics
curl https://model-catalog.socko.us/api/models/gridfinity-bin/print-stats
```

---

## Deployment Workflow

### For Phase 3.2 & 3.3 Changes

#### 1. Local Development
```bash
# Create feature branch
git checkout -b feature/phase-3.2-3d-viewer

# Make changes
# Edit files in homeassistant/www/3d_printing/model_catalog/
# Edit sidecars/model_catalog/app/main.py as needed

# Run tests
pytest tests/phase3/test_phase3_2_3d_viewer.py -v

# Commit
git add -A
git commit -m "feat(phase3.2): Add 3D viewer and STL loader"
```

#### 2. Deploy to Staging
```bash
# Build sidecar image
docker build -f sidecars/model_catalog/Dockerfile \
  -t registry.socko.us/model-catalog-sidecar:0.2.0-rc1 .

# Push
docker push registry.socko.us/model-catalog-sidecar:0.2.0-rc1

# Update staging env
echo "MODEL_CATALOG_IMAGE_TAG=0.2.0-rc1" >> .env.staging

# Deploy
docker compose -f docker-compose.staging.yml pull
docker compose -f docker-compose.staging.yml up -d
```

#### 3. Test in Staging
```bash
# Run integration tests
python test_phase3_endpoints.py

# Manual testing in browser
# Visit http://staging-ha.socko.us:8123/3d-printing/model-catalog
```

#### 4. Deploy to Production
```bash
# Push to production after staging validation
# Update version in main .env
echo "MODEL_CATALOG_IMAGE_TAG=0.2.0" >> .env

# Deploy
docker compose pull
docker compose up -d

# Verify
curl https://model-catalog.socko.us/health
```

#### 5. Update Dashboard Cache
```bash
# Increment resource versions in _resources.yaml
# geometry-parser.js?v=1 → ?v=2
# viewer.js?v=1 → ?v=2
# etc.

# Commit and push
git add homeassistant/packages/3d_printing/common/dashboards/_resources.yaml
git commit -m "chore: Bump resource versions for cache busting"

# Reload Home Assistant UI
# User: Hard refresh browser (Ctrl+Shift+R)
```

---

## Troubleshooting

### Common Issues

#### Sidecar Connection Issues
```bash
# Check if sidecar is running
docker ps | grep model-catalog

# Check logs
docker logs model-catalog-sidecar

# Verify network connectivity
curl -v https://model-catalog.socko.us/health

# Check firewall
# Port 443 should be open
```

#### Three.js Not Loading
```bash
# Check browser console (F12)
# Look for CORS errors or missing THREE object

# Verify script is in _resources.yaml
grep "three.min.js" homeassistant/packages/3d_printing/common/dashboards/_resources.yaml

# Hard refresh browser
# Ctrl+Shift+R (Windows/Linux)
# Cmd+Shift+R (Mac)
```

#### STL Parser Errors
```bash
# Check browser console for specific error
# Common: "Invalid STL file" → check file format
# Common: "Unexpected end of data" → check file not truncated

# Test parser locally
python -c "from sidecars.model_catalog.app.geometry import STLParser; ..."
```

#### Archive Linking Not Working
```bash
# Check sidecar logs
docker logs model-catalog-sidecar | grep archive

# Check filenames match
# Archive: "gridfinity-bin_v2.stl"
# Model: "gridfinity-bin" (fuzzy match should work)

# Verify automation triggered
# Check Home Assistant automation traces
```

---

## Performance Optimization

### Phase 3.2 Optimization Tips

#### Large Model Handling
```javascript
// Implement progressive loading for large STL files
// 1. Start with lower resolution mesh
// 2. Stream triangle data in chunks
// 3. Display simplified geometry while loading full model
```

#### Memory Management
```javascript
// Dispose resources when viewer destroyed
viewer.dispose = function() {
  this.geometry.dispose();
  this.material.dispose();
  this.renderer.dispose();
};
```

#### Rendering Performance
```javascript
// Use WebWorker for STL parsing (offload from main thread)
// This prevents UI freezing during large file parsing
const worker = new Worker('stl-parser.worker.js');
```

### Phase 3.3 Optimization Tips

#### Archive Linking Speed
```python
# Cache summary map for faster lookups
self.summary_cache = {s.model_id: s for s in summaries}  # O(1) lookup
```

#### Statistics Aggregation
```python
# Pre-compute statistics on a schedule (not on-demand)
# Store in cache for fast retrieval
# Invalidate cache when new archive added
```

---

## Monitoring & Logging

### Sidecar Logs
```bash
# Real-time logs
docker logs -f model-catalog-sidecar

# Specific level
docker logs --since 10m model-catalog-sidecar 2>&1 | grep ERROR
```

### Home Assistant Logs
```bash
# Location
/config/logs/home-assistant.log

# Watch for Phase 3 errors
tail -f /config/logs/home-assistant.log | grep -i "model_catalog"
```

### Browser Console
```javascript
// Enable detailed logging in JavaScript
window.PHASE3_DEBUG = true;

// View logs
console.log("Model loaded:", geometryData);
console.error("STL parse error:", error);
```

---

## Version History

| Version | Date | Phase | Status | Notes |
|---------|------|-------|--------|-------|
| 0.1.0 | 2026-03-28 | Phase 1A | ✅ Deployed | Initial scaffold |
| 0.1.1 | 2026-04-15 | Phase 1B | ✅ Deployed | Archive link CRUD |
| 0.2.0 | 2026-05-03 | Phase 3.1 | ✅ Deployed | Edit form + metadata |
| 0.3.0 | 2026-05-10 | Phase 3.2 | 🔄 In Progress | 3D viewer |
| 0.4.0 | 2026-05-17 | Phase 3.3 | 🟡 Planned | Cross-system integration |

---

## Important Files Reference

| File | Purpose | Type |
|------|---------|------|
| [PHASE-3.1-VALIDATION-REPORT.md](PHASE-3.1-VALIDATION-REPORT.md) | Deployment verification | 📄 Report |
| [PHASE-3.2-IMPLEMENTATION-PLAN.md](PHASE-3.2-IMPLEMENTATION-PLAN.md) | 3D viewer implementation | 📋 Plan |
| [PHASE-3.3-IMPLEMENTATION-PLAN.md](PHASE-3.3-IMPLEMENTATION-PLAN.md) | Cross-system implementation | 📋 Plan |
| [test_phase3_endpoints.py](test_phase3_endpoints.py) | Integration test script | 🧪 Test |
| [tests/phase3/](tests/phase3/) | Unit test suite (890 lines) | 🧪 Tests |

---

**Configuration Last Updated:** April 25, 2026  
**Prepared For:** Phase 3.2-3.3 Implementation (April 26 - May 10, 2026)
