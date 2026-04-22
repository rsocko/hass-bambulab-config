[CmdletBinding()]
param(
    [string]$CatalogRoot = "C:\Users\rysock\OneDrive\3D Printing Catalog",
    [string]$SdBackupsRoot = "C:\Users\rysock\OneDrive\3D Printing\_SD Card Backups",
    [string]$RepoBackfillStateRoot = "c:\dev\hass-bambulab-config\bambuddy\backfill-state",
    [switch]$UpdateLatest
)

$ErrorActionPreference = 'Stop'

function Copy-IfExists {
    param(
        [string]$Source,
        [string]$Destination,
        [string]$Label
    )

    if (-not (Test-Path -LiteralPath $Source)) {
        Write-Warning "Missing source for ${Label}: $Source"
        return $false
    }

    $destDir = Split-Path -Parent $Destination
    New-Item -ItemType Directory -Path $destDir -Force | Out-Null
    Copy-Item -LiteralPath $Source -Destination $Destination -Force
    Write-Host "Copied $Label -> $Destination"
    return $true
}

$stamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$snapshotRoot = Join-Path $RepoBackfillStateRoot ("snapshots\" + $stamp)

$files = @(
    @{
        Label = "lane-a-manifest"
        Source = Join-Path $CatalogRoot "manifest.json"
        SnapshotName = "lane-a_manifest.json"
        LatestName = "lane-a_manifest.latest.json"
    },
    @{
        Label = "lane-a-state"
        Source = Join-Path $CatalogRoot "state\catalog_state.json"
        SnapshotName = "lane-a_catalog_state.json"
        LatestName = "lane-a_catalog_state.latest.json"
    },
    @{
        Label = "lane-b1-manifest"
        Source = Join-Path $SdBackupsRoot "backfill-state\archive_backfill_manifest_v2_earlier_sd_card.json"
        SnapshotName = "lane-b1_archive_backfill_manifest_v2_earlier_sd_card.json"
        LatestName = "archive_backfill_manifest_v2_earlier_sd_card.json"
    },
    @{
        Label = "lane-b2-manifest"
        Source = Join-Path $SdBackupsRoot "backfill-state\archive_backfill_manifest_v2.json"
        SnapshotName = "lane-b2_archive_backfill_manifest_v2.json"
        LatestName = "archive_backfill_manifest_v2.json"
    },
    @{
        Label = "lane-b-cache-manifest"
        Source = Join-Path $SdBackupsRoot "backfill-state\archive_backfill_manifest_v2_ha_bambulab_cache.json"
        SnapshotName = "lane-b_cache_archive_backfill_manifest_v2_ha_bambulab_cache.json"
        LatestName = "archive_backfill_manifest_v2_ha_bambulab_cache.json"
    }
)

New-Item -ItemType Directory -Path $snapshotRoot -Force | Out-Null
$copiedCount = 0

foreach ($entry in $files) {
    $snapshotDestination = Join-Path $snapshotRoot $entry.SnapshotName
    if (Copy-IfExists -Source $entry.Source -Destination $snapshotDestination -Label $entry.Label) {
        $copiedCount++
        if ($UpdateLatest) {
            $latestDestination = Join-Path $RepoBackfillStateRoot $entry.LatestName
            Copy-IfExists -Source $entry.Source -Destination $latestDestination -Label ($entry.Label + " (latest)") | Out-Null
        }
    }
}

Write-Host "Snapshot complete. Files copied: $copiedCount"
Write-Host "Snapshot path: $snapshotRoot"
