param(
    [string]$BaseUrl = "http://127.0.0.1:8818",
    [string]$Token,
    [int]$SourceArchiveId = 0,
    [int]$TargetArchiveId = 0,
    [switch]$Apply,
    [switch]$Verify,
    [switch]$RemoveOriginal
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-HealthCheck {
    param([string]$Url)
    Write-Host "Checking sidecar health at $Url/health"
    Invoke-RestMethod -Method Get -Uri "$Url/health" | ConvertTo-Json -Depth 10
}

function Invoke-SidecarPost {
    param(
        [string]$Url,
        [string]$Path,
        [string]$BearerToken,
        [hashtable]$Payload
    )

    if (-not $BearerToken) {
        throw "Token is required for sidecar request. Pass -Token or use health-only mode."
    }

    $headers = @{ Authorization = "Bearer $BearerToken" }
    $body = ($Payload | ConvertTo-Json -Depth 20)

    Write-Host "Posting request to $Url$Path"
    Write-Host $body

    Invoke-RestMethod -Method Post -Uri "$Url$Path" -Headers $headers -ContentType 'application/json' -Body $body |
        ConvertTo-Json -Depth 20
}

Invoke-HealthCheck -Url $BaseUrl

if ($SourceArchiveId -gt 0 -and $TargetArchiveId -gt 0) {
    if ($Verify.IsPresent) {
        $payload = @{
            source_archive_id = $SourceArchiveId
            target_archive_id = $TargetArchiveId
            remove_original = $RemoveOriginal.IsPresent
            dry_run = (-not $Apply.IsPresent)
        }
        Invoke-SidecarPost -Url $BaseUrl -Path "/admin/archive-restore-verify" -BearerToken $Token -Payload $payload
    }
    else {
        $payload = @{
            source_archive_id = $SourceArchiveId
            target_archive_id = $TargetArchiveId
            dry_run = (-not $Apply.IsPresent)
        }
        Invoke-SidecarPost -Url $BaseUrl -Path "/admin/archive-restore-from" -BearerToken $Token -Payload $payload
    }
}
else {
    Write-Host "Health check only. Pass -SourceArchiveId and -TargetArchiveId to exercise restore-from or restore-verify."
}