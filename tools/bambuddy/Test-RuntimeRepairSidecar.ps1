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
    [switch]$Apply
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-HealthCheck {
    param([string]$Url)
    Write-Host "Checking sidecar health at $Url/health"
    $health = Invoke-RestMethod -Method Get -Uri "$Url/health"
    $health | ConvertTo-Json -Depth 5
}

function Invoke-RuntimeRepair {
    param(
        [string]$Url,
        [string]$BearerToken,
        [hashtable]$Payload
    )

    if (-not $BearerToken) {
        throw "Token is required for repair request. Pass -Token or use health-only mode."
    }

    $headers = @{ Authorization = "Bearer $BearerToken" }
    $body = ($Payload | ConvertTo-Json -Depth 10)

    Write-Host "Posting runtime repair request to $Url/admin/archive-runtime-repair"
    Write-Host $body

    Invoke-RestMethod -Method Post -Uri "$Url/admin/archive-runtime-repair" -Headers $headers -ContentType 'application/json' -Body $body |
        ConvertTo-Json -Depth 10
}

Invoke-HealthCheck -Url $BaseUrl

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

    Invoke-RuntimeRepair -Url $BaseUrl -BearerToken $Token -Payload $payload
}
else {
    Write-Host "Health check only. Pass -ArchiveId to exercise the repair endpoint."
}