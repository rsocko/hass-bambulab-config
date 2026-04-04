[CmdletBinding()]
param(
    [ValidateSet('Inspect', 'Upload', 'Full')]
    [string]$Mode = 'Inspect',

    [Parameter(Mandatory = $true)]
    [string]$BaseUrl,

    [Parameter(Mandatory = $true)]
    [int]$PrinterId,

    [Parameter(Mandatory = $true)]
    [int]$FallbackArchiveId,

    [Parameter(Mandatory = $true)]
    [string]$SourceFilePath,

    [ValidateSet('sd_cache_3mf', 'bambu_studio_exported_sliced_3mf', 'bambu_studio_source_3mf')]
    [string]$RecoverySource = 'sd_cache_3mf',

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

function Get-FileHashes {
    param([string]$Path)

    return [PSCustomObject]@{
        MD5 = (Get-FileHash -LiteralPath $Path -Algorithm MD5).Hash
        SHA256 = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
    }
}

function Join-TagString {
    param(
        [string]$ExistingTags,
        [string[]]$AdditionalTags
    )

    $tags = @()
    if (-not [string]::IsNullOrWhiteSpace($ExistingTags)) {
        $tags += ($ExistingTags -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })
    }
    $tags += $AdditionalTags | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }
    return (($tags | Select-Object -Unique) -join ',')
}

function Append-NotesBlock {
    param(
        [string]$ExistingNotes,
        [string]$Block
    )

    if ([string]::IsNullOrWhiteSpace($ExistingNotes)) {
        return $Block
    }

    return ($ExistingNotes.TrimEnd() + "`n`n" + $Block)
}

function New-RecoveryAuditBlock {
    param(
        [hashtable]$Payload
    )

    return "[RECOVERY_AUDIT_V1]`n$($Payload | ConvertTo-Json -Compress -Depth 8)"
}

function Invoke-ArchiveUpload {
    param(
        [string]$Url,
        [int]$TargetPrinterId,
        [string]$Path,
        [hashtable]$Headers
    )

    Add-Type -AssemblyName System.Net.Http

    $client = New-Object System.Net.Http.HttpClient
    try {
        foreach ($key in $Headers.Keys) {
            $client.DefaultRequestHeaders.Remove($key) | Out-Null
            $client.DefaultRequestHeaders.Add($key, [string]$Headers[$key])
        }

        $uri = '{0}/api/v1/archives/upload?printer_id={1}' -f $Url.TrimEnd('/'), $TargetPrinterId
        $multipart = New-Object System.Net.Http.MultipartFormDataContent
        try {
            $bytes = [System.IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $Path))
            $content = New-Object System.Net.Http.ByteArrayContent($bytes)
            $content.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse('application/octet-stream')
            $fileName = [System.IO.Path]::GetFileName($Path)
            $multipart.Add($content, 'file', $fileName)

            $response = $client.PostAsync($uri, $multipart).GetAwaiter().GetResult()
            $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            if (-not $response.IsSuccessStatusCode) {
                throw "Upload failed with status $([int]$response.StatusCode): $body"
            }

            return ($body | ConvertFrom-Json)
        }
        finally {
            $multipart.Dispose()
        }
    }
    finally {
        $client.Dispose()
    }
}

function Update-Archive {
    param(
        [string]$Url,
        [int]$ArchiveId,
        [hashtable]$Headers,
        [hashtable]$Body
    )

    $uri = ('{0}/api/v1/archives/{1}' -f $Url.TrimEnd('/'), $ArchiveId)
    $json = $Body | ConvertTo-Json -Compress -Depth 8
    return Invoke-RestMethod -Method Patch -Uri $uri -Headers $Headers -ContentType 'application/json' -Body $json
}

$headers = New-Headers -Key $ApiKey
$resolvedSourcePath = (Resolve-Path -LiteralPath $SourceFilePath).Path
$fallback = Get-ArchiveDetail -Url $BaseUrl -ArchiveId $FallbackArchiveId -Headers $headers
$hashes = Get-FileHashes -Path $resolvedSourcePath

$inspection = [ordered]@{
    mode = $Mode
    fallback_archive_id = $fallback.id
    fallback_filename = $fallback.filename
    fallback_print_name = $fallback.print_name
    fallback_status = $fallback.status
    fallback_started_at = $fallback.started_at
    fallback_completed_at = $fallback.completed_at
    fallback_actual_time_seconds = $fallback.actual_time_seconds
    source_file_path = $resolvedSourcePath
    source_file_md5 = $hashes.MD5
    source_file_sha256 = $hashes.SHA256
    recovery_source = $RecoverySource
}

$newArchiveNoteBlock = New-RecoveryAuditBlock -Payload ([ordered]@{
    recovered_from_archive_id = $fallback.id
    recovery_source = $RecoverySource
    original_status = $fallback.status
    original_started_at = $fallback.started_at
    original_completed_at = $fallback.completed_at
    original_actual_time_seconds = $fallback.actual_time_seconds
})

$oldArchiveNoteTemplate = [ordered]@{
    replaced_by_archive_id = $null
    replacement_status = 'archived'
    recovery_source = $RecoverySource
}

if ($Mode -eq 'Inspect') {
    [PSCustomObject]$inspection | ConvertTo-Json -Depth 8
    ""
    $newArchiveNoteBlock
    return
}

$newArchive = Invoke-ArchiveUpload -Url $BaseUrl -TargetPrinterId $PrinterId -Path $resolvedSourcePath -Headers $headers
[PSCustomObject]@{
    uploaded_archive_id = $newArchive.id
    uploaded_status = $newArchive.status
    uploaded_file_path = $newArchive.file_path
    uploaded_thumbnail_path = $newArchive.thumbnail_path
    uploaded_content_hash = $newArchive.content_hash
} | ConvertTo-Json -Depth 8

if ($Mode -eq 'Upload') {
    return
}

$oldArchiveNoteBlock = New-RecoveryAuditBlock -Payload ([ordered]@{
    replaced_by_archive_id = $newArchive.id
    replacement_status = $newArchive.status
    replacement_completed_at = $newArchive.completed_at
    recovery_source = $RecoverySource
})

$newArchiveTags = Join-TagString -ExistingTags $newArchive.tags -AdditionalTags @(
    'repair:recovered',
    ('recovered_from:{0}' -f $fallback.id),
    ('recovery_source:{0}' -f $RecoverySource)
)

$oldArchiveTags = Join-TagString -ExistingTags $fallback.tags -AdditionalTags @(
    'exception:missing_3mf',
    ('replaced_by:{0}' -f $newArchive.id)
)

$updatedNew = Update-Archive -Url $BaseUrl -ArchiveId $newArchive.id -Headers $headers -Body ([ordered]@{
    tags = $newArchiveTags
    notes = Append-NotesBlock -ExistingNotes $newArchive.notes -Block $newArchiveNoteBlock
})

$updatedOld = Update-Archive -Url $BaseUrl -ArchiveId $fallback.id -Headers $headers -Body ([ordered]@{
    tags = $oldArchiveTags
    notes = Append-NotesBlock -ExistingNotes $fallback.notes -Block $oldArchiveNoteBlock
})

[PSCustomObject]@{
    fallback_archive_id = $updatedOld.id
    replacement_archive_id = $updatedNew.id
    fallback_tags = $updatedOld.tags
    replacement_tags = $updatedNew.tags
} | ConvertTo-Json -Depth 8