param(
    [string]$BaseUrl = "http://127.0.0.1:8818",
    [string]$Token,
    [int]$SourceArchiveId = 0,
    [int]$TargetArchiveId = 0,
    [switch]$Apply,
    [switch]$Verify,
    [switch]$RemoveOriginal,
    [switch]$RunReenrich,
    [switch]$ForceRemoveWithoutReenrich,
    [switch]$SkipPhotos,
    [switch]$CompactOutput
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Test-HasProperty {
    param(
        [object]$Value,
        [string]$Name
    )

    return $null -ne $Value -and ($Value.PSObject.Properties.Name -contains $Name)
}

function Get-OptionalProperty {
    param(
        [object]$Value,
        [string]$Name
    )

    if (Test-HasProperty -Value $Value -Name $Name) {
        return $Value.$Name
    }

    return $null
}

function Get-ErrorResponseBody {
    param([System.Exception]$Exception)

    if (Test-HasProperty -Value $Exception -Name 'ErrorDetails') {
        $errorDetails = Get-OptionalProperty -Value $Exception -Name 'ErrorDetails'
        $detailsMessage = Get-OptionalProperty -Value $errorDetails -Name 'Message'
        if ($detailsMessage) {
            return $detailsMessage
        }
    }

    $response = Get-OptionalProperty -Value $Exception -Name 'Response'
    if ($null -eq $response) {
        return $null
    }

    try {
        $stream = $response.GetResponseStream()
        if ($null -eq $stream) {
            return $null
        }

        $reader = New-Object System.IO.StreamReader($stream)
        try {
            return $reader.ReadToEnd()
        }
        finally {
            $reader.Dispose()
        }
    }
    catch {
        return $null
    }
}

function Get-RequestedFieldGroups {
    param([switch]$SkipPhotos)

    if ($SkipPhotos.IsPresent) {
        return @('runtime', 'user_metadata', 'lineage', 'snapshot_subset')
    }

    return @('runtime', 'user_metadata', 'lineage', 'snapshot_subset', 'asset_state')
}

function Get-DisplayObject {
    param(
        [object]$Value,
        [switch]$Compact
    )

    if (-not $Compact.IsPresent -or $null -eq $Value) {
        return $Value
    }

    if ((Test-HasProperty -Value $Value -Name 'status') -and (Test-HasProperty -Value $Value -Name 'db_path')) {
        return [ordered]@{
            status = $Value.status
            db_path = $Value.db_path
        }
    }

    if ((Test-HasProperty -Value $Value -Name 'source_archive_id') -and (Test-HasProperty -Value $Value -Name 'target_archive_id')) {
        return [ordered]@{
            source_archive_id = $Value.source_archive_id
            target_archive_id = $Value.target_archive_id
            updated = Get-OptionalProperty -Value $Value -Name 'updated'
            applied = Get-OptionalProperty -Value $Value -Name 'applied'
            verified = Get-OptionalProperty -Value $Value -Name 'verified'
            removable = Get-OptionalProperty -Value $Value -Name 'removable'
            source_removed = Get-OptionalProperty -Value $Value -Name 'source_removed'
            reenrich_requested = Get-OptionalProperty -Value $Value -Name 'reenrich_requested'
            reenrich_triggered = Get-OptionalProperty -Value $Value -Name 'reenrich_triggered'
            enrichment_status = Get-OptionalProperty -Value $Value -Name 'enrichment_status'
            enrichment_ready = Get-OptionalProperty -Value $Value -Name 'enrichment_ready'
            updated_fields = Get-OptionalProperty -Value $Value -Name 'updated_fields'
            field_action_summary = Get-OptionalProperty -Value $Value -Name 'field_action_summary'
            remaining_difference_count = Get-OptionalProperty -Value $Value -Name 'remaining_difference_count'
            blocking_difference_count = Get-OptionalProperty -Value $Value -Name 'blocking_difference_count'
            non_blocking_difference_count = Get-OptionalProperty -Value $Value -Name 'non_blocking_difference_count'
            remaining_difference_summary = Get-OptionalProperty -Value $Value -Name 'remaining_difference_summary'
            warnings = Get-OptionalProperty -Value $Value -Name 'warnings'
        }
    }

    return $Value
}

function Write-ResponseObject {
    param(
        [string]$Label,
        [object]$Value,
        [switch]$Compact
    )

    if ($Label) {
        Write-Host $Label
    }

    $displayValue = Get-DisplayObject -Value $Value -Compact:$Compact
    $json = $displayValue | ConvertTo-Json -Depth 20
    Write-Host $json
}

function Invoke-HealthCheck {
    param(
        [string]$Url,
        [switch]$Compact
    )

    Write-Host "Checking sidecar health at $Url/health"

    $health = Invoke-RestMethod -Method Get -Uri "$Url/health"
    Write-ResponseObject -Value $health -Compact:$Compact
}

function Invoke-SidecarPost {
    param(
        [string]$Url,
        [string]$Path,
        [string]$BearerToken,
        [hashtable]$Payload,
        [switch]$Compact
    )

    if (-not $BearerToken) {
        throw "Token is required for sidecar request. Pass -Token or use health-only mode."
    }

    $headers = @{ Authorization = "Bearer $BearerToken" }
    $body = ($Payload | ConvertTo-Json -Depth 20)

    Write-Host "Posting request to $Url$Path"
    if ($Compact.IsPresent) {
        Write-Host ($Payload | ConvertTo-Json -Depth 10 -Compress)
    }
    else {
        Write-Host $body
    }

    try {
        $response = Invoke-RestMethod -Method Post -Uri "$Url$Path" -Headers $headers -ContentType 'application/json' -Body $body
        Write-ResponseObject -Label 'Response:' -Value $response -Compact:$Compact
    }
    catch {
        $errorBody = Get-ErrorResponseBody -Exception $_.Exception
        if ($errorBody) {
            Write-Error "Sidecar request failed: $errorBody"
        }
        else {
            throw
        }
    }
}

Invoke-HealthCheck -Url $BaseUrl -Compact:$CompactOutput

if ($SourceArchiveId -gt 0 -and $TargetArchiveId -gt 0) {
    $fieldGroups = Get-RequestedFieldGroups -SkipPhotos:$SkipPhotos

    if ($RunReenrich.IsPresent -and -not $Verify.IsPresent -and $Apply.IsPresent) {
        Write-Warning "Inline re-enrich couples restore apply to Home Assistant browser refresh. Prefer running restore/apply + verify first, then run re-enrich as a separate step once HA is stable."
    }

    if ($RemoveOriginal.IsPresent -and $ForceRemoveWithoutReenrich.IsPresent) {
        Write-Warning "Force-removing the original archive without completed enrichment bypasses the normal safety gate. Use only after verifying the replacement archive is otherwise complete."
    }

    if ($Verify.IsPresent) {
        $payload = @{
            source_archive_id = $SourceArchiveId
            target_archive_id = $TargetArchiveId
            field_groups = $fieldGroups
            remove_original = $RemoveOriginal.IsPresent
            force_remove_without_reenrich = $ForceRemoveWithoutReenrich.IsPresent
            dry_run = (-not $Apply.IsPresent)
        }
        Invoke-SidecarPost -Url $BaseUrl -Path "/admin/archive-restore-verify" -BearerToken $Token -Payload $payload -Compact:$CompactOutput
    }
    else {
        $payload = @{
            source_archive_id = $SourceArchiveId
            target_archive_id = $TargetArchiveId
            field_groups = $fieldGroups
            run_reenrich = $RunReenrich.IsPresent
            dry_run = (-not $Apply.IsPresent)
        }
        Invoke-SidecarPost -Url $BaseUrl -Path "/admin/archive-restore-from" -BearerToken $Token -Payload $payload -Compact:$CompactOutput
    }
}
else {
    Write-Host "Health check only. Pass -SourceArchiveId and -TargetArchiveId to exercise restore-from or restore-verify."
}