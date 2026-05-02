# Local Model Import Guide

## Overview

The import system allows you to populate the local model catalog with test models by placing files in the server inbox directory (`/assets/model inbox`) or using the local import script.

> **Note on Model IDs**: Each imported model is automatically assigned a unique `local_model_id` in the format `{name-slug}--{shortid}` (e.g., `gridfinity-bin--a1b2c3d4`). This ID is immutable and used as the folder name for model assets. See [LOCAL-MODEL-STORAGE-AND-NAMING-DESIGN.md](LOCAL-MODEL-STORAGE-AND-NAMING-DESIGN.md) for details on the naming convention and why model folder names don't change when you edit a model's display name.

## Two Import Methods

### Method 1: Direct Server Import (Recommended)

Use the sidecar's bulk discovery and import endpoints to import from the server inbox:

```bash
# From repo root:
python tools/model_catalog/import_direct_models.py --sidecar-url http://model-catalog.socko.us
```

This discovers all `.3mf` and `.stl` files in `/assets/model inbox` and creates local models with:
- Auto-generated model IDs and names from filenames
- Primary geometry assets
- `imported` and `test` tags
- `Imported Models` collection

### Method 2: Local Folder Import

For local testing, place files in `assets/model_catalog/inbox/`:

```bash
# Copy your models here:
assets/model_catalog/inbox/
├── gridfinity-bin.3mf
├── benchy.stl
└── storage-organizer.3mf
```

Then run:
```bash
python tools/model_catalog/import_test_models.py --api-url http://model-catalog.socko.us
```

## Server-Side Import (Method 1 - Details)

### File Format

The server inbox supports:
- **3D Models**: `.3mf`, `.stl`, `.obj`, `.step`, `.stp`
- **Documents**: `.pdf`, `.md`, `.txt`, `.csv`, `.json`, `.yaml`, `.yml`
- **Images**: `.jpg`, `.jpeg`, `.png`, `.webp`, `.gif`

### Example: Discovering Models

```bash
# Discover without importing
curl -X POST http://model-catalog.socko.us/api/working-groups/bulk-discover \
  -H "Content-Type: application/json" \
  -d '{
    "folder_path": "/assets/model inbox",
    "grouping_strategy": "flat"
  }'
```

Response includes all discovered files grouped by proposal, with:
- File path, size, and SHA256 hash
- Duplicate detection
- Warnings for inaccessible files

### Example: Importing Discovered Models

The import script (Method 1 above) automates this process:

1. **Discovers** models in `/assets/model inbox`
2. **Creates** a local model entry for each `.3mf` or `.stl` file
3. **Attaches** the geometry file as a primary asset
4. **Applies** auto-generated metadata (name, ID, tags, collection)

## Local Import (Method 2 - Details)

### Quick Start

1. **Place Model Files**

Copy your `.3mf` or `.stl` files into `assets/model_catalog/inbox/`:

```
assets/model_catalog/inbox/
├── gridfinity-bin.3mf
├── benchy.stl
└── storage-organizer.3mf
```

2. **(Optional) Add Metadata**

For each model, create a `.yaml` metadata file with the same name:

```
assets/model_catalog/inbox/
├── gridfinity-bin.3mf
├── gridfinity-bin.3mf.yaml          ← metadata for gridfinity-bin.3mf
├── benchy.stl
└── benchy.stl.yaml                  ← metadata for benchy.stl
```

3. **Run the Import Script**

```bash
# From the repo root:
python tools/model_catalog/import_test_models.py

# Or specify a different API URL:
python tools/model_catalog/import_test_models.py --api-url http://model-catalog.socko.us
```

### Metadata Format

If no `.yaml` file is found, the importer auto-generates metadata from the filename. You can also create metadata files to override defaults.

#### Example: gridfinity-bin.3mf.yaml

```yaml
# local_model_id is auto-generated if omitted (format: slug--shortid)
# Example: gridfinity-bin--a1b2c3d4
# You can specify it here, but it's not required:
# local_model_id: "gridfinity-bin--a1b2c3d4"

model_name: "Gridfinity Bin"
model_description: "Modular storage container compatible with Gridfinity standard"
creator_name: "Your Name"
collection_names:
  - "Storage Solutions"
keyword_names:
  - "gridfinity"
  - "parametric"
  - "storage"
tags:
  - "organization"
  - "container"
  - "reusable"
```

#### Example: benchy.stl.yaml

```yaml
# local_model_id is auto-generated if omitted
# Uncomment below to override (must follow slug--shortid format):
# local_model_id: "benchy-calibration--f7e8c9d0"

model_name: "Benchy - 3D Calibration Test"
model_description: "Standard 3D printer calibration model for testing print quality"
creator_name: "Test Import"
collection_names: []
keyword_names:
  - "calibration"
  - "test"
tags:
  - "calibration"
  - "test"
  - "quality-check"
```

### Auto-Generated Metadata

If you don't provide a `.yaml` file, the script generates defaults based on the filename:

| Filename | Auto-Generated Name | Local Model ID (Example) | Tags |
|----------|---------------------|--------------------------|------|
| `gridfinity-bin.3mf` | Gridfinity Bin | `gridfinity-bin--a1b2c3d4` | `test`, `imported` |
| `benchy.stl` | Benchy | `benchy--f7e8c9d0` | `test`, `imported` |
| `storage_organizer.3mf` | Storage Organizer | `storage-organizer--2b3a4c5d` | `test`, `imported` |

### Import Process (Local)

1. **Scan inbox/** — Finds all `.3mf` and `.stl` files
2. **Load metadata** — Reads accompanying `.yaml` or auto-generates from filename
3. **Create model** — Calls `/api/local/models` POST endpoint
4. **Attach asset** — Calls `/api/local/models/{id}/assets` POST endpoint
5. **Move to validated/** — After success, moves file to `validated/` directory
6. **Report results** — Prints summary with model IDs and any errors

### Example Output

```
📦 Importing 3 model(s) from inbox/

Processing: gridfinity-bin.3mf
  → Creating model 'Gridfinity Bin'...
  ✓ Model created (ID: gridfinity-bin--a1b2c3d4)
  → Attaching 3MF geometry...
  ✓ Asset attached
  ✓ Moved to validated/

Processing: benchy.stl
  → Creating model 'Benchy'...
  ✓ Model created (ID: benchy--f7e8c9d0)
  → Attaching STL geometry...
  ✓ Asset attached
  ✓ Moved to validated/

============================================================
IMPORT SUMMARY
============================================================
✓ Imported:  2
⚠ Errors:    0
⊘ Skipped:   0

✓ Successfully imported:
  - Gridfinity Bin (gridfinity-bin.3mf)
    Model ID: gridfinity-bin--a1b2c3d4, Folder: gridfinity-bin--a1b2c3d4/
  - Benchy (benchy.stl)
    Model ID: 43, Asset ID: 2

============================================================
📍 Validated models: assets/model_catalog/validated
🔗 API: http://localhost:8123
============================================================
```

## Troubleshooting

### "Connection refused"

Make sure the sidecar is running and accessible:
```bash
# Check API health
curl http://model-catalog.socko.us/healthz

# Or for local development:
python -m app.main  # from sidecars/model_catalog/
```

Specify the correct API URL:
```bash
python tools/model_catalog/import_direct_models.py --sidecar-url http://model-catalog.socko.us
```

### "folder_path must be an existing directory"

Verify the server-side path exists. Common paths:
- `/assets/model inbox` — Production server
- `/assets/model_catalog/inbox` — Local development

### Import fails with "UNIQUE constraint failed"

The model already exists in the database. Use a different `local_model_id` or delete the existing model:
```bash
curl -X DELETE http://model-catalog.socko.us/api/local/models/model-id-here
```

### "No model files found in inbox/"

Ensure you've placed `.3mf` or `.stl` files in the inbox directory.

### Import fails with model creation error

Check the metadata YAML is valid:
```bash
python -c "import yaml; yaml.safe_load(open('path/to/file.yaml'))"
```

## Next Steps

Once imported:
1. ✅ Models appear in `/api/models` endpoint (authority="local")
2. ✅ HA UI displays them in the model catalog browser
3. ✅ Test Phase 3.1 features: edit mode, photo gallery, enrichment fields
4. ✅ Ready for Phase 4 testing: keyboard shortcuts, colored geometry

## Related Documentation

- [Local Model Authority (Phase 1)](phase-1-implementation-plan.md)
- [Model Summary Blending (Phase 2)](post-manyfold-transition-plan-2026-04.md)
- [Phase 3.1 Edit & Photos](phase-3.1-implementation-guide.md)
- [API Reference](api-reference.md)
