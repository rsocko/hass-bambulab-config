param(
    [string]$BaseUrl = "http://127.0.0.1:8818",
    [string]$Token,
    [int]$ArchiveId = 0
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Invoke-HealthCheck {
    param([string]$Url)
    Write-Host "Checking sidecar health at $Url/health"
    Invoke-RestMethod -Method Get -Uri "$Url/health" | ConvertTo-Json -Depth 10
}

function Invoke-ArchiveInspection {
    param(
        [string]$Url,
        [string]$BearerToken,
        [int]$RequestedArchiveId
    )

    if (-not $BearerToken) {
        throw "Token is required for archive inspection. Pass -Token or use health-only mode."
    }

    $headers = @{ Authorization = "Bearer $BearerToken" }
    $path = "/admin/archive-spool-linkage/$RequestedArchiveId"

    Write-Host "Requesting archive spool linkage at $Url$path"
    Invoke-RestMethod -Method Get -Uri "$Url$path" -Headers $headers | ConvertTo-Json -Depth 20
}

Invoke-HealthCheck -Url $BaseUrl

if ($ArchiveId -gt 0) {
    Invoke-ArchiveInspection -Url $BaseUrl -BearerToken $Token -RequestedArchiveId $ArchiveId
}
else {
    Write-Host "Health check only. Pass -ArchiveId to inspect native spool linkage for one archive."
}