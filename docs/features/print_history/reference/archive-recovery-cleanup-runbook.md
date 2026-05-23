# Archive Recovery Cleanup Runbook

Status: Active
Last Reviewed: 2026-05-23
Functional Owner: print_history
Replaces: docs/features/print_history/recovery/archive-recovery-cleanup-runbook.md
Replaced By: none

## Purpose

Provide a manual, operator-approved path for removing the original fallback archive after a successful replacement-archive recovery.

This is optional.

Default policy remains:

- keep the historical fallback archive
- keep the recovered file-backed replacement archive

## When cleanup is safe

Only consider deleting the fallback archive when all of the following are true:

1. the replacement archive exists and opens correctly in Bambuddy
2. the replacement archive has a non-empty `file_path`
3. the replacement archive has a non-empty `content_hash`
4. the replacement archive has a thumbnail
5. the replacement archive contains a `[RECOVERY_AUDIT_V1]` note block preserving the original runtime values
6. the historical archive contains the expected `replaced_by:<new_id>` tag

## Recommended flow

1. inspect the old and new archive pair
2. confirm recovery linkage and recovery notes
3. decide whether to keep both or delete the historical fallback archive
4. if deleting, delete only the historical fallback archive, never the replacement archive
5. re-open the replacement archive and verify its notes/tags still preserve provenance clearly

## PowerShell Helper

Use:

- `tests/phase3/print_history/Test-BambuddyArchiveCleanup.ps1`

Inspect only:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\tests\phase3\print_history\Test-BambuddyArchiveCleanup.ps1' -Mode Inspect -BaseUrl 'http://bambuddy.socko.us' -HistoricalArchiveId 189 -ReplacementArchiveId 199
```

Delete after verification:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& '.\tests\phase3\print_history\Test-BambuddyArchiveCleanup.ps1' -Mode Delete -BaseUrl 'http://bambuddy.socko.us' -HistoricalArchiveId 189 -ReplacementArchiveId 199
```

## Exact API Calls For 174

Use this only after choosing the highest-confidence available source in this order:

1. `bambuddy/Backup SD Card - 2026-04-03/cache/200mm x 200mm Deadpool & Wolverine Hueforge.3mf`
2. Bambu Studio `Export plate sliced file` output produced from `bambuddy/Backup SD Card - 2026-04-03/Deadpool___Wolverine.3mf`
3. raw `bambuddy/Backup SD Card - 2026-04-03/Deadpool___Wolverine.3mf`

### 1. Inspect the fallback archive

```powershell
$baseUrl = 'http://bambuddy.socko.us'
$fallbackId = 174
Invoke-RestMethod -Method Get -Uri "$baseUrl/api/v1/archives/$fallbackId"
```

### 2. Upload the chosen recovery file

```powershell
$baseUrl = 'http://bambuddy.socko.us'
$printerId = 1
$sourcePath = '.\bambuddy\Backup SD Card - 2026-04-03\cache\200mm x 200mm Deadpool & Wolverine Hueforge.3mf'

Add-Type -AssemblyName System.Net.Http
$client = [System.Net.Http.HttpClient]::new()
$multipart = [System.Net.Http.MultipartFormDataContent]::new()
$bytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $sourcePath))
$content = New-Object System.Net.Http.ByteArrayContent -ArgumentList @(,$bytes)
$content.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse('application/octet-stream')
$multipart.Add($content, 'file', [System.IO.Path]::GetFileName($sourcePath))
$response = $client.PostAsync("$baseUrl/api/v1/archives/upload?printer_id=$printerId", $multipart).GetAwaiter().GetResult()
$body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult() | ConvertFrom-Json
$newId = $body.id
$client.Dispose()
$multipart.Dispose()
$newId
```

### 3. Patch the fallback archive with lineage metadata

```powershell
$baseUrl = 'http://bambuddy.socko.us'
$fallbackId = 174
$newId = <replacement_archive_id>

$oldBody = @{
  tags = 'exception:missing_3mf,replaced_by:' + $newId
  notes = "[RECOVERY_AUDIT_V1]`n{`"replaced_by_archive_id`":$newId,`"replacement_status`":`"archived`",`"recovery_source`":`"sd_cache_3mf`"}"
} | ConvertTo-Json -Compress

Invoke-RestMethod -Method Patch -Uri "$baseUrl/api/v1/archives/$fallbackId" -ContentType 'application/json' -Body $oldBody
```

### 4. Patch the replacement archive with preserved runtime metadata

```powershell
$baseUrl = 'http://bambuddy.socko.us'
$fallbackId = 174
$newId = <replacement_archive_id>

$newBody = @{
  tags = 'repair:recovered,recovered_from:174,recovery_source:sd_cache_3mf'
  notes = "[RECOVERY_AUDIT_V1]`n{`"recovered_from_archive_id`":174,`"recovery_source`":`"sd_cache_3mf`",`"original_status`":`"completed`",`"original_started_at`":`"<original_started_at>`",`"original_completed_at`":`"<original_completed_at>`",`"original_actual_time_seconds`":<original_actual_time_seconds>}"
} | ConvertTo-Json -Compress

Invoke-RestMethod -Method Patch -Uri "$baseUrl/api/v1/archives/$newId" -ContentType 'application/json' -Body $newBody
```

### 5. Optional cleanup delete for 174

Only after operator review:

```powershell
$baseUrl = 'http://bambuddy.socko.us'
$fallbackId = 174
Invoke-RestMethod -Method Delete -Uri "$baseUrl/api/v1/archives/$fallbackId"
```

## Recommendation

For `174`, keep the fallback archive by default even after a successful replacement because that case is still only `medium` confidence.