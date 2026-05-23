# Model Catalog Persistence And Backup Strategy

> **Status**: Design approved for Phase 1.25 planning.
> **Last updated**: 2026-04-25
> **Scope**: Sidecar-owned persistence, backup automation, restore drills, and deployment-mode tradeoffs for the model-catalog service.

## Purpose

Define the concrete persistence boundary and recommended backup approach for the model-catalog sidecar so Phase 1.25 can be executed without reopening storage decisions later.

This doc exists because issue `#1121` adds an explicit requirement to determine and automate backup of sidecar-owned data before later phases accumulate harder-to-reconstruct state.

## Durable State Boundary

The sidecar's durable state boundary is the `/data` mount.

Current baseline:

- `MODEL_CATALOG_DB_PATH=/data/model_catalog.db`
- the SQLite database is the primary durable state store
- future durable sidecar artifacts should also live under `/data` unless documented otherwise

What belongs under `/data`:

- `model_catalog.db`
- future export bundles
- future ingestion manifests or parser caches that need backup parity with the DB
- backup metadata written by future admin flows if added

What does not belong under `/data` by default:

- container image layers
- transient logs that can be recreated
- fetched Manyfold data that is intentionally treated as disposable cache unless it becomes part of an operator-approved durable workflow

## Design Decisions

### Default Storage Mode

Recommended default:

- use a dedicated Docker named volume mounted at `/data`

Why this is the default:

- matches the current compose examples
- keeps deployment simple in the same-stack sidecar model
- avoids accidental dependence on Windows path translation behavior
- keeps the live SQLite workload on the Linux container filesystem path rather than a Windows-host mount

### Optional Storage Mode

Supported opt-in mode:

- use a Linux or WSL bind mount for `/data` when direct host visibility or host-native backup tooling is materially useful

Why it is optional rather than the default:

- it increases operator responsibility for permissions, path stability, and accidental edits
- it is valuable when a host backup agent already targets a known Linux-side path

### Non-Recommended Default

Avoid making a Windows-host bind mount the default for the live SQLite file.

Reasons:

- higher risk of path and permission edge cases across Docker Desktop, WSL, and Windows boundaries
- poorer fit for a frequently written SQLite workload
- easier accidental human edits from the host side
- less portable if the stack later moves to a pure Linux Docker host

## Recommended Automation Pattern

Recommended baseline:

1. keep live state on a Docker named volume
2. take a consistent SQLite backup into a timestamped export directory
3. capture sidecar metadata alongside the DB snapshot
4. copy or sync that export bundle to secondary storage
5. run restore drills against a fresh sidecar instance on a regular cadence

The main design point is that backup should operate on a consistent snapshot, not on an arbitrary raw copy of a DB file that may be mid-write.

## Recommended Snapshot Shape

Each backup should create a timestamped bundle containing:

- `model_catalog.db`
- `metadata.json`
- optional checksum manifest

Suggested metadata payload:

- backup timestamp
- sidecar image tag/version/revision
- sidecar schema version
- source deployment mode: named volume or bind mount
- hostname or stack identifier
- notes for restore provenance if the backup was taken before a risky migration

## Concrete Backup Flows

### Flow A: Default Named-Volume Backup

Recommended for the current repo baseline.

Pattern:

1. run the sidecar in Docker with `/data` on a named volume
2. create a consistent SQLite backup file into a mounted export directory
3. save metadata next to the DB backup
4. hand that export directory to a retention tool such as `restic` or `kopia`

Operational shape:

- live state remains isolated in the Docker volume
- exported backups become the portable artifact
- retention, encryption, and off-host copies happen outside the sidecar's live storage

Why this is the preferred default:

- strongest separation between live state and backup artifacts
- easiest path to same-stack deployment
- works even when Docker volumes are not directly convenient to browse from Windows

Example approach:

1. mount the live named volume and a host backup directory into a helper context
2. run a SQLite backup operation that writes a new DB file into the backup directory
3. write `metadata.json` next to the snapshot
4. hand that backup directory to retention tooling

Example command pattern using the running sidecar container's Python runtime:

```bash
BACKUP_ROOT=/srv/backups/model-catalog
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
TARGET_DIR="$BACKUP_ROOT/$STAMP"
mkdir -p "$TARGET_DIR"

docker exec model-catalog-sidecar python -c "import json, pathlib, sqlite3, urllib.request; root=pathlib.Path('$TARGET_DIR'); root.mkdir(parents=True, exist_ok=True); src=sqlite3.connect('/data/model_catalog.db'); dst=sqlite3.connect(str(root / 'model_catalog.db')); src.backup(dst); src.close(); dst.close(); health=json.load(urllib.request.urlopen('http://127.0.0.1:8314/healthz')); config=json.load(urllib.request.urlopen('http://127.0.0.1:8314/config')); (root / 'metadata.json').write_text(json.dumps({'backup_timestamp':'$STAMP','healthz':health,'config':config}, indent=2), encoding='utf-8')"
```

Design note:

- the exact execution wrapper can be host scheduler, cron inside WSL, systemd timer, or a helper container
- the important property is use of SQLite's backup API or an equivalent consistent snapshot step rather than a naive raw file copy

### Flow B: Linux/WSL Bind-Mount Backup

Use this when you specifically want host-visible sidecar data.

Pattern:

1. mount `/data` from a Linux-side host path
2. still create a consistent SQLite snapshot before retention copy
3. let the host backup agent protect either the snapshot directory or the bind-mounted data root, depending on the tool design

When this is attractive:

- a host scheduler already exists in WSL or Linux
- backup software already targets a known filesystem path
- you want easier manual inspection and restore testing without Docker volume tooling

Tradeoff:

- the live DB is more directly exposed to operator mistakes than a named volume

Example compose shape for the opt-in mode:

```yaml
services:
	model-catalog-sidecar:
		volumes:
			- /srv/model-catalog-data:/data
```

Example snapshot pattern in that mode:

```bash
DATA_ROOT=/srv/model-catalog-data
BACKUP_ROOT=/srv/backups/model-catalog
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
TARGET_DIR="$BACKUP_ROOT/$STAMP"
mkdir -p "$TARGET_DIR"

python3 - <<'PY'
import json
import os
import pathlib
import sqlite3

data_root = pathlib.Path(os.environ['DATA_ROOT'])
target_dir = pathlib.Path(os.environ['TARGET_DIR'])
target_dir.mkdir(parents=True, exist_ok=True)
src = sqlite3.connect(str(data_root / 'model_catalog.db'))
dst = sqlite3.connect(str(target_dir / 'model_catalog.db'))
src.backup(dst)
src.close()
dst.close()
(target_dir / 'metadata.json').write_text(json.dumps({'source_mode': 'bind_mount'}, indent=2), encoding='utf-8')
PY
```

This mode is easier to pair with host-native backup agents, but the recommendation remains the same: protect a fresh snapshot artifact, not an arbitrary live DB file.

## Concrete Restore Flow

Restore should be treated as an explicit drill, not an assumed property of backup existence.

Recommended restore sequence:

1. stop the sidecar
2. restore the chosen backup bundle into the target `/data` root
3. start the sidecar
4. call `/healthz` and `/config`
5. verify schema version, DB path, and key row counts or smoke-test endpoints
6. only then treat the restore as validated

Minimum restore validation:

- service starts successfully
- schema version matches expectation
- archive-link read endpoint responds
- a representative model-summary endpoint responds from cached or refreshed state

Example restore pattern:

```bash
RESTORE_DIR=/srv/backups/model-catalog/20260425T120000Z

docker stop model-catalog-sidecar
cp "$RESTORE_DIR/model_catalog.db" /srv/model-catalog-data/model_catalog.db
docker start model-catalog-sidecar
curl http://127.0.0.1:8314/healthz
curl http://127.0.0.1:8314/config
```

For the named-volume mode, replace the direct host copy with a helper step that writes the restored DB back into the mounted volume before restarting the sidecar.

## Home Assistant's Role

Home Assistant is not the primary backup executor.

Reasoning:

- the durable state lives with Docker and the sidecar host boundary
- HA should not become responsible for host filesystem orchestration just because it is the main operator UI

What HA may do later:

- show last successful backup time
- show last restore-tested time
- expose a manual "backup now" action that triggers a host-side or sidecar-admin flow
- surface backup failures as operational alerts

What HA should not own by default:

- direct filesystem copying of Docker-managed sidecar storage
- retention scheduling as the system of record

## Tooling Comparison

### Option 1: `restic`

Best fit when:

- you want mature encrypted backups with multiple backend options
- you already use restic elsewhere in the homelab
- you want snapshot retention and off-host sync without writing much custom glue

Pros:

- mature and widely used
- strong retention and repository model
- good for backing up exported bundles after the SQLite snapshot step
- works well with local disk, NAS, and cloud/object targets

Cons:

- still needs a pre-backup snapshot/export step for live SQLite consistency
- operational UX is CLI-first

Recommendation:

- strongest third-party default if you already run homelab CLI backup tooling

### Option 2: `kopia`

Best fit when:

- you want a richer repository UX or already use kopia for workstation/server backups
- you value policy management and repository inspection features

Pros:

- strong backup and retention capabilities
- good encryption and repository features
- can be friendlier than pure CLI-only workflows in some environments

Cons:

- same snapshot-consistency requirement as restic
- potentially more operational surface than needed for one sidecar initially

Recommendation:

- strong alternative to restic, especially if it matches your existing backup estate better

### Option 3: Small Scheduled Docker Backup Job

Best fit when:

- you want the lowest-friction first implementation inside the stack
- you want something repo-local and easy to reason about before adopting a broader backup platform

Pros:

- simplest custom implementation path
- easy to keep close to the sidecar deployment
- good first milestone for proving restore drills and metadata capture

Cons:

- weak retention and off-host protection unless paired with another sync/copy step
- easy to stop at "local copies" and overestimate real recoverability

Recommendation:

- good bootstrap option, but better when paired with `restic` or `kopia` rather than treated as the full backup system

## Recommended Practical Choice For This Repo

Best overall baseline:

- keep `/data` on a dedicated Docker named volume
- add a small scheduled export/snapshot job as the first concrete Phase 1.25 implementation
- feed the exported bundles into `restic` or `kopia` for retention and off-host copies

Recommended first implementation split:

1. implement the export/snapshot step first
2. prove restore with one disposable drill
3. only then attach longer-term retention and off-host sync

Why this wins:

- preserves the current same-stack sidecar deployment shape
- avoids making Windows-host path exposure a hidden dependency
- gives a concrete repo-local starting point
- leaves room to plug into a broader homelab backup system without redesigning sidecar persistence again

## Decision Matrix

| Option | Live-storage safety | Backup maturity | Off-host readiness | Windows/WSL friendliness | Operational complexity | Recommendation |
|---|---|---|---|---|---|---|
| Named volume + export + `restic` | High | High | High | Medium | Medium | Preferred default |
| Named volume + export + `kopia` | High | High | High | Medium | Medium | Strong alternative |
| Named volume + local scheduled copies only | High | Medium | Low | Medium | Low | Acceptable bootstrap only |
| Linux/WSL bind mount + host backup tool | Medium | High | High | High | Medium | Good opt-in mode |
| Windows bind mount for live DB | Low to medium | Medium | Medium | Highest direct visibility | Medium | Not recommended as default |

## Phase 1.25 Deliverables

- persistence boundary documented
- default storage mode frozen
- backup metadata shape documented
- named-volume export flow documented
- Linux/WSL bind-mount variant documented
- restore drill documented
- one preferred backup-tool path selected for the first live deployment

## Open Decisions To Confirm During Execution

- whether the first live retention target is NAS, local disk, or cloud/object storage
- whether `restic` or `kopia` better matches the rest of the homelab
- whether the first snapshot/export step should run from a host scheduler, a dedicated helper container, or a future sidecar admin endpoint

Those do not block the design baseline in this doc. They are implementation choices inside the approved Phase 1.25 boundary.