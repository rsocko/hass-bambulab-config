param(
    [string]$BaseUrl = "http://127.0.0.1:8123",
    [string]$ManifestPath = "homeassistant/packages/3d_printing/common/dashboards/_resources.yaml",
    [string]$SourcePath = "homeassistant/www/3d_printing/print_history/print-history-archive-restore-card.js",
    [switch]$Json,
    [switch]$AllowMismatch
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Resolve-RepoPath {
    param([string]$RelativePath)

    $root = Split-Path -Parent $PSScriptRoot
    $root = Split-Path -Parent $root
    return [System.IO.Path]::GetFullPath((Join-Path $root $RelativePath))
}

function Get-RestoreCardResourceUrl {
    param([string]$YamlPath)

    $content = Get-Content -LiteralPath $YamlPath -Raw
    $match = [regex]::Match(
        $content,
        '(?m)^- url: (?<url>/local/3d_printing/print_history/print-history-archive-restore-card\.js\?v=\d+)\s*$'
    )
    if (-not $match.Success) {
        throw "Unable to locate print-history-archive-restore-card resource URL in $YamlPath"
    }

    return $match.Groups['url'].Value
}

function Get-ContentSha256 {
    param([string]$Content)

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Content)
        $hashBytes = $sha.ComputeHash($bytes)
        return ([System.BitConverter]::ToString($hashBytes) -replace '-', '').ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Test-RestoreCardMarkers {
    param([string]$Content)

    return [ordered]@{
        has_helper_state = $Content.Contains('_helperState(')
        has_source_helper_fallback = $Content.Contains("const helperValue = this._helperState(this._config?.source_archive_helper).trim();")
        has_upload_helper_fallback = $Content.Contains("const helperValue = this._helperState(this._config?.upload_session_helper).trim();")
        has_direct_input_onchange = $Content.Contains('fileInput.onchange = this._boundUploadChange;')
        has_recursive_source_fallback = $Content.Contains('|| this._sourceArchive()?.id')
    }
}

$resolvedManifestPath = Resolve-RepoPath -RelativePath $ManifestPath
$resolvedSourcePath = Resolve-RepoPath -RelativePath $SourcePath

$resourceUrl = Get-RestoreCardResourceUrl -YamlPath $resolvedManifestPath
$localContent = Get-Content -LiteralPath $resolvedSourcePath -Raw
$servedUri = "{0}{1}" -f $BaseUrl.TrimEnd('/'), $resourceUrl

try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $servedUri -TimeoutSec 15
}
catch {
    throw "Failed to fetch HA-served restore card asset from $servedUri. $($_.Exception.Message)"
}

$servedContent = [string]$response.Content
$localMarkers = Test-RestoreCardMarkers -Content $localContent
$servedMarkers = Test-RestoreCardMarkers -Content $servedContent
$localHash = Get-ContentSha256 -Content $localContent
$servedHash = Get-ContentSha256 -Content $servedContent

$result = [ordered]@{
    manifest_path = $resolvedManifestPath
    source_path = $resolvedSourcePath
    resource_url = $resourceUrl
    served_uri = $servedUri
    http_status = [int]$response.StatusCode
    local_hash = $localHash
    served_hash = $servedHash
    served_matches_local = ($localHash -eq $servedHash)
    local_markers = $localMarkers
    served_markers = $servedMarkers
}

if ($Json.IsPresent) {
    $result | ConvertTo-Json -Depth 10
}
else {
    Write-Host "Restore card runtime verification"
    Write-Host ("Resource URL: {0}" -f $resourceUrl)
    Write-Host ("Served URI  : {0}" -f $servedUri)
    Write-Host ("HTTP status : {0}" -f $response.StatusCode)
    Write-Host ("Local hash  : {0}" -f $localHash)
    Write-Host ("Served hash : {0}" -f $servedHash)
    Write-Host ("Hashes match: {0}" -f ($localHash -eq $servedHash))
    Write-Host "Local markers:"
    $localMarkers.GetEnumerator() | ForEach-Object { Write-Host ("  {0}: {1}" -f $_.Key, $_.Value) }
    Write-Host "Served markers:"
    $servedMarkers.GetEnumerator() | ForEach-Object { Write-Host ("  {0}: {1}" -f $_.Key, $_.Value) }
}

if (-not $AllowMismatch.IsPresent -and $localHash -ne $servedHash) {
    throw "HA-served restore card asset does not match the workspace source."
}