[CmdletBinding()]
param(
    [ValidateSet("A", "B1", "B2", "C")]
    [string]$Lane = "A",
    [switch]$NoViewer,
    [switch]$NoOpenFolder,
    [switch]$WaitViewer,
    [string]$RepoRoot = "c:\dev\hass-bambulab-config",
    [string]$CatalogRoot = "C:\Users\rysock\OneDrive\3D Printing Catalog",
    [string]$SdBackupsRoot = "C:\Users\rysock\OneDrive\3D Printing\_SD Card Backups",
    [string]$ArchiveBaseUrl = "http://bambuddy.socko.us"
)

$ErrorActionPreference = "Stop"

$pythonExe = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw "Python executable not found: $pythonExe"
}

$folderCatalogViewer = Join-Path $RepoRoot "tools\bambuddy\folder_3mf_catalog_viewer.py"
$gcodeForensicsViewer = Join-Path $RepoRoot "tools\bambuddy\gcode_forensics_viewer.py"

switch ($Lane) {
    "A" {
        $workingRoot = $CatalogRoot
        $manifest = Join-Path $CatalogRoot "manifest.json"
        $state = Join-Path $CatalogRoot "state\catalog_state.json"
        $viewerScript = $folderCatalogViewer
        $viewerArgs = @(
            $viewerScript,
            "--manifest", $manifest,
            "--state", $state,
            "--archive-base-url", $ArchiveBaseUrl
        )
    }
    "B1" {
        $sourceRoot = Join-Path $SdBackupsRoot "2025-08-14 - SD Card Backup"
        $manifest = Join-Path $SdBackupsRoot "backfill-state\archive_backfill_manifest_v2_earlier_sd_card.json"
        $workingRoot = $sourceRoot
        $viewerScript = $gcodeForensicsViewer
        $viewerArgs = @(
            $viewerScript,
            "--source-root", $sourceRoot,
            "--manifest", $manifest
        )
    }
    "B2" {
        $sourceRoot = Join-Path $SdBackupsRoot "2026-04-03 - SD Card Backup"
        $manifest = Join-Path $SdBackupsRoot "backfill-state\archive_backfill_manifest_v2.json"
        $workingRoot = $sourceRoot
        $viewerScript = $gcodeForensicsViewer
        $viewerArgs = @(
            $viewerScript,
            "--source-root", $sourceRoot,
            "--manifest", $manifest
        )
    }
    "C" {
        $sourceRoot = Join-Path $RepoRoot "bambuddy\Backup SD Card - 2026-04-03"
        $manifest = Join-Path $RepoRoot "bambuddy\backfill-state\archive_backfill_manifest_v2.json"
        $workingRoot = $sourceRoot
        $viewerScript = $gcodeForensicsViewer
        $viewerArgs = @(
            $viewerScript,
            "--source-root", $sourceRoot,
            "--manifest", $manifest
        )
    }
}

Write-Host "Lane $Lane selected."
Write-Host "Working root: $workingRoot"

if (-not $NoOpenFolder) {
    if (Test-Path -LiteralPath $workingRoot) {
        Start-Process -FilePath "explorer.exe" -ArgumentList $workingRoot | Out-Null
    }
    else {
        Write-Warning "Working root not found: $workingRoot"
    }
}

if ($NoViewer) {
    Write-Host "Viewer launch skipped (--NoViewer)."
    return
}

if (-not (Test-Path -LiteralPath $viewerScript)) {
    throw "Viewer script not found: $viewerScript"
}

Write-Host "Launching viewer via $pythonExe"

if ($WaitViewer) {
    & $pythonExe @viewerArgs
}
else {
    Start-Process -FilePath $pythonExe -ArgumentList $viewerArgs | Out-Null
    Write-Host "Viewer started in background."
}
