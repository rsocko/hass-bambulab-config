param(
  [string]$BaseUrl = "http://192.168.1.5:8123",
  [string]$ResourcesFile = "homeassistant/packages/3d_printing/common/dashboards/_resources.yaml",
  [string]$WorkspaceRoot = ".",
  [ValidateSet("normalized", "bytes")]
  [string]$CompareMode = "normalized"
)

$ErrorActionPreference = "Stop"

function Get-ResourceEntries {
  param([string]$ResourcesPath)

  $lines = Get-Content -Path $ResourcesPath
  $entries = @()

  foreach ($line in $lines) {
    if ($line -match "^\s*-\s+url:\s+(.+)$") {
      $url = $matches[1].Trim()
      if ($url.StartsWith("/local/3d_printing/model_catalog/")) {
        $entries += $url
      }
    }
  }

  return $entries
}

function Get-FileNameFromUrl {
  param([string]$Url)

  $pathPart = $Url.Split("?")[0]
  return [System.IO.Path]::GetFileName($pathPart)
}

function Get-NormalizedContentHash {
  param([string]$Path)

  $text = Get-Content -Raw -Path $Path
  $normalized = ($text -replace "`r`n", "`n" -replace "`r", "`n")
  $bytes = [System.Text.Encoding]::UTF8.GetBytes($normalized)
  return [System.BitConverter]::ToString([System.Security.Cryptography.SHA256]::Create().ComputeHash($bytes)).Replace('-', '')
}

$root = Resolve-Path -Path $WorkspaceRoot
$resourcesPath = Join-Path $root $ResourcesFile

if (-not (Test-Path -Path $resourcesPath)) {
  throw "Resources file not found: $resourcesPath"
}

$entries = Get-ResourceEntries -ResourcesPath $resourcesPath
if (-not $entries -or $entries.Count -eq 0) {
  throw "No /local/3d_printing/model_catalog entries found in $resourcesPath"
}

$results = @()

foreach ($entry in $entries) {
  $fileName = Get-FileNameFromUrl -Url $entry
  $localPath = Join-Path $root "homeassistant/www/3d_printing/model_catalog/$fileName"
  $remoteUrl = "$BaseUrl$entry"

  if (-not (Test-Path -Path $localPath)) {
    $results += [PSCustomObject]@{
      Asset = $fileName
      VersionedUrl = $entry
      LocalHash = "MISSING"
      RemoteHash = "SKIPPED"
      Match = $false
      Note = "Local file missing"
    }
    continue
  }

  $tmpFile = Join-Path $env:TEMP ("verify-ui-" + [Guid]::NewGuid().ToString() + "-" + $fileName)

  try {
    Invoke-WebRequest -Uri $remoteUrl -OutFile $tmpFile -UseBasicParsing | Out-Null

    if ($CompareMode -eq "bytes") {
      $localHash = (Get-FileHash -Path $localPath -Algorithm SHA256).Hash
      $remoteHash = (Get-FileHash -Path $tmpFile -Algorithm SHA256).Hash
    }
    else {
      $localHash = Get-NormalizedContentHash -Path $localPath
      $remoteHash = Get-NormalizedContentHash -Path $tmpFile
    }
    $match = $localHash -eq $remoteHash

    $results += [PSCustomObject]@{
      Asset = $fileName
      VersionedUrl = $entry
      LocalHash = $localHash
      RemoteHash = $remoteHash
      Match = $match
      Note = if ($match) { "" } else { "Hash mismatch ($CompareMode)" }
    }
  }
  catch {
    $results += [PSCustomObject]@{
      Asset = $fileName
      VersionedUrl = $entry
      LocalHash = "ERROR"
      RemoteHash = "ERROR"
      Match = $false
      Note = $_.Exception.Message
    }
  }
  finally {
    if (Test-Path -Path $tmpFile) {
      Remove-Item -Path $tmpFile -Force -ErrorAction SilentlyContinue
    }
  }
}

$results | Sort-Object Asset | Format-Table -AutoSize Asset, Match, Note, VersionedUrl

$bad = $results | Where-Object { -not $_.Match }
if ($bad.Count -gt 0) {
  Write-Host ""
  Write-Host "FAILED: $($bad.Count) asset(s) are not in sync." -ForegroundColor Red
  exit 2
}

Write-Host ""
Write-Host "OK: All model catalog /local assets match local files." -ForegroundColor Green
Write-Host "Comparison mode: $CompareMode"
exit 0
