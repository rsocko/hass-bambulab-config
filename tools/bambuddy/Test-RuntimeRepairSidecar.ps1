param(
    [string]$BaseUrl = "http://127.0.0.1:8818",
    [string]$Token,
    [int]$ArchiveId = 0,
    [string]$StartedAt,
    [string]$CompletedAt,
    [string]$CreatedAt,
    [string]$Status,
    [string]$FailureReason,
    [string]$AuditNote = "Smoke test from Test-RuntimeRepairSidecar.ps1",
    [switch]$Apply,
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

    if (Test-HasProperty -Value $Value -Name 'archive_id') {
        return [ordered]@{
            archive_id = $Value.archive_id
            applied = Get-OptionalProperty -Value $Value -Name 'applied'
            changed = Get-OptionalProperty -Value $Value -Name 'changed'
            updated_fields = Get-OptionalProperty -Value $Value -Name 'updated_fields'
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

function Invoke-RuntimeRepair {
    param(
        [string]$Url,
        [string]$BearerToken,
        [hashtable]$Payload,
        [switch]$Compact
    )

    if (-not $BearerToken) {
        throw "Token is required for repair request. Pass -Token or use health-only mode."
    }

    $headers = @{ Authorization = "Bearer $BearerToken" }
    $body = ($Payload | ConvertTo-Json -Depth 10)

    Write-Host "Posting runtime repair request to $Url/admin/archive-runtime-repair"
    if ($Compact.IsPresent) {
        Write-Host ($Payload | ConvertTo-Json -Depth 10 -Compress)
    }
    else {
        Write-Host $body
    }

    try {
        $response = Invoke-RestMethod -Method Post -Uri "$Url/admin/archive-runtime-repair" -Headers $headers -ContentType 'application/json' -Body $body
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

if ($ArchiveId -gt 0) {
    $payload = @{
        archive_id = $ArchiveId
        started_at = $(if ($StartedAt) { $StartedAt } else { $null })
        completed_at = $(if ($CompletedAt) { $CompletedAt } else { $null })
        created_at = $(if ($CreatedAt) { $CreatedAt } else { $null })
        status = $(if ($Status) { $Status } else { $null })
        failure_reason = $(if ($FailureReason) { $FailureReason } else { $null })
        audit_note = $AuditNote
        dry_run = (-not $Apply.IsPresent)
    }

    Invoke-RuntimeRepair -Url $BaseUrl -BearerToken $Token -Payload $payload -Compact:$CompactOutput
}
else {
    Write-Host "Health check only. Pass -ArchiveId to exercise the repair endpoint."
}