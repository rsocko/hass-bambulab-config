[CmdletBinding()]
param(
    [ValidateSet('Inspect', 'Delete')]
    [string]$Mode = 'Inspect',

    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,

    [Parameter(Mandatory = $true)]
    [int]$HistoricalArchiveId,

    [Parameter(Mandatory = $true)]
    [int]$ReplacementArchiveId,

    [string]$ApiKey
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function New-Headers {
    param([string]$Key)

    $headers = @{}
    if (-not [string]::IsNullOrWhiteSpace($Key)) {
        $headers['X-API-Key'] = $Key
    }

    return $headers
}

function Get-ArchiveDetail {
    param(
        [string]$Url,
        [int]$ArchiveId,
        [hashtable]$Headers
    )

    $uri = ('{0}/api/v1/archives/{1}' -f $Url.TrimEnd('/'), $ArchiveId)
    return Invoke-RestMethod -Method Get -Uri $uri -Headers $Headers
}

function Remove-Archive {
    param(
        [string]$Url,
        [int]$ArchiveId,
        [hashtable]$Headers
    )

    $uri = ('{0}/api/v1/archives/{1}' -f $Url.TrimEnd('/'), $ArchiveId)
    return Invoke-RestMethod -Method Delete -Uri $uri -Headers $Headers
}

function Test-RecoveryAuditBlock {
    param([string]$Notes)

    $raw = [string]::Empty
    if ($null -ne $Notes) {
        $raw = [string]$Notes
    }

    return $raw.Contains('[RECOVERY_AUDIT_V1]')
}

$headers = New-Headers -Key $ApiKey
$historical = Get-ArchiveDetail -Url $BaseUrl -ArchiveId $HistoricalArchiveId -Headers $headers
$replacement = Get-ArchiveDetail -Url $BaseUrl -ArchiveId $ReplacementArchiveId -Headers $headers

$historicalTags = @()
if (-not [string]::IsNullOrWhiteSpace($historical.tags)) {
    $historicalTags = $historical.tags -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
}

$replacementTags = @()
if (-not [string]::IsNullOrWhiteSpace($replacement.tags)) {
    $replacementTags = $replacement.tags -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ }
}

$verification = [ordered]@{
    historical_archive_id = $historical.id
    replacement_archive_id = $replacement.id
    historical_exists = $null -ne $historical
    replacement_exists = $null -ne $replacement
    historical_has_replaced_by_tag = $historicalTags -contains ('replaced_by:{0}' -f $ReplacementArchiveId)
    replacement_has_recovered_from_tag = $replacementTags -contains ('recovered_from:{0}' -f $HistoricalArchiveId)
    replacement_has_recovery_source_tag = ($replacementTags | Where-Object { $_ -like 'recovery_source:*' }).Count -gt 0
    replacement_has_repair_recovered_tag = $replacementTags -contains 'repair:recovered'
    historical_has_recovery_audit = Test-RecoveryAuditBlock -Notes $historical.notes
    replacement_has_recovery_audit = Test-RecoveryAuditBlock -Notes $replacement.notes
    replacement_status = $replacement.status
    replacement_file_path = $replacement.file_path
    replacement_content_hash = $replacement.content_hash
}

[PSCustomObject]$verification | ConvertTo-Json -Depth 8

if ($Mode -eq 'Inspect') {
    return
}

if (-not $verification.historical_has_replaced_by_tag) {
    throw 'Historical archive is missing the expected replaced_by tag.'
}

if (-not $verification.replacement_has_recovered_from_tag) {
    throw 'Replacement archive is missing the expected recovered_from tag.'
}

if (-not $verification.replacement_has_recovery_audit) {
    throw 'Replacement archive is missing the recovery audit note block.'
}

if ($verification.replacement_has_repair_recovered_tag) {
    throw 'Replacement archive still has repair:recovered after completion cleanup.'
}

if ($verification.replacement_has_recovered_from_tag) {
    throw 'Replacement archive still has recovered_from:* after completion cleanup.'
}

if ($verification.replacement_has_recovery_source_tag) {
    throw 'Replacement archive still has recovery_source:* after completion cleanup.'
}

$deleteResult = Remove-Archive -Url $BaseUrl -ArchiveId $HistoricalArchiveId -Headers $headers

[PSCustomObject]@{
    deleted_archive_id = $HistoricalArchiveId
    replacement_archive_id = $ReplacementArchiveId
    delete_status = $deleteResult.status
} | ConvertTo-Json -Depth 8