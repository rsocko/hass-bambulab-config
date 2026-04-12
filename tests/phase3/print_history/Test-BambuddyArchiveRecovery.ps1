[CmdletBinding()]
param(
    [ValidateSet('Inspect', 'Upload', 'Full', 'Backfill')]
    [string]$Mode = 'Inspect',

    [string]$BaseUrl,

    [int]$PrinterId,

    [int]$FallbackArchiveId,

    [string]$SourceFilePath,

    [int]$ExistingReplacementArchiveId,

    [string]$ManifestPath,

    [ValidateSet('Inspect', 'Upload', 'Full')]
    [string]$BackfillAction = 'Inspect',

    [string]$ManifestEntryId,

    [switch]$AllowSourceProjectImport,

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

function Get-ArchivePage {
    param(
        [string]$Url,
        [int]$Limit,
        [int]$Offset,
        [hashtable]$Headers
    )

    $uri = ('{0}/api/v1/archives/?limit={1}&offset={2}' -f $Url.TrimEnd('/'), $Limit, $Offset)
    return Invoke-RestMethod -Method Get -Uri $uri -Headers $Headers
}

function Get-AllArchives {
    param(
        [string]$Url,
        [hashtable]$Headers,
        [int]$PageSize = 100
    )

    $offset = 0
    $items = @()

    while ($true) {
        $page = Get-ArchivePage -Url $Url -Limit $PageSize -Offset $offset -Headers $Headers
        if ($null -eq $page) {
            $page = @()
        }
        elseif ($page -isnot [System.Array]) {
            $page = @($page)
        }

        if ($page.Count -eq 0) {
            break
        }

        $items += $page
        if ($page.Count -lt $PageSize) {
            break
        }

        $offset += $PageSize
    }

    return $items
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

function New-HistoricalImportBlock {
    param(
        [hashtable]$Payload
    )

    return "[HISTORICAL_IMPORT_V1]`n$($Payload | ConvertTo-Json -Compress -Depth 10)"
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
            $content = New-Object System.Net.Http.ByteArrayContent -ArgumentList @(,$bytes)
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

function Assert-Required {
    param(
        [object]$Value,
        [string]$Name
    )

    if ($null -eq $Value) {
        throw "$Name is required."
    }

    if ($Value -is [string] -and [string]::IsNullOrWhiteSpace($Value)) {
        throw "$Name is required."
    }

    if ($Value -is [int] -and $Value -le 0) {
        throw "$Name is required."
    }
}

function Get-ManifestCandidates {
    param([string]$Path)

    $manifest = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    if ($manifest -is [System.Collections.IEnumerable] -and -not ($manifest.PSObject.Properties.Name -contains 'candidates')) {
        return @($manifest)
    }

    if (-not $manifest.candidates) {
        throw 'Manifest does not contain a candidates array.'
    }

    return @($manifest.candidates)
}

function Find-ExistingArchiveByHash {
    param(
        [object[]]$Archives,
        [string]$Sha256
    )

    if ([string]::IsNullOrWhiteSpace($Sha256)) {
        return $null
    }

    foreach ($archive in $Archives) {
        if ([string]::Equals([string]$archive.content_hash, $Sha256, [System.StringComparison]::OrdinalIgnoreCase)) {
            return $archive
        }
    }

    return $null
}

function ConvertTo-BackfillResult {
    param(
        [object]$Candidate,
        [string]$Status,
        [string]$Reason,
        [int]$MatchedArchiveId = 0,
        [int]$CreatedArchiveId = 0
    )

    return [ordered]@{
        entry_id = $Candidate.entry_id
        source_path = $Candidate.source_path
        source_type = $Candidate.source_type
        confidence = $Candidate.confidence
        status = $Status
        reason = $Reason
        matched_archive_id = $(if ($MatchedArchiveId -gt 0) { $MatchedArchiveId } else { $null })
        created_archive_id = $(if ($CreatedArchiveId -gt 0) { $CreatedArchiveId } else { $null })
    }
}

function Invoke-BackfillMode {
    param(
        [string]$Url,
        [int]$TargetPrinterId,
        [string]$Path,
        [string]$Action,
        [hashtable]$Headers,
        [string]$EntryId,
        [switch]$AllowSourceImport
    )

    Assert-Required -Value $Url -Name 'BaseUrl'
    Assert-Required -Value $TargetPrinterId -Name 'PrinterId'
    Assert-Required -Value $Path -Name 'ManifestPath'

    $candidates = @(Get-ManifestCandidates -Path $Path)
    if (-not [string]::IsNullOrWhiteSpace($EntryId)) {
        $candidates = @($candidates | Where-Object { $_.entry_id -eq $EntryId -or $_.source_sha256 -eq $EntryId -or $_.source_path -eq $EntryId })
    }

    $existingArchives = Get-AllArchives -Url $Url -Headers $Headers
    if ($null -eq $existingArchives) {
        $existingArchives = @()
    }
    elseif ($existingArchives -isnot [System.Array]) {
        $existingArchives = @($existingArchives)
    }
    $results = @()

    foreach ($candidate in $candidates) {
        $existing = Find-ExistingArchiveByHash -Archives $existingArchives -Sha256 ([string]$candidate.source_sha256)
        if ($existing) {
            $results += [pscustomobject](ConvertTo-BackfillResult -Candidate $candidate -Status 'skipped_existing_content_hash' -Reason 'Existing Bambuddy archive has matching content_hash.' -MatchedArchiveId ([int]$existing.id))
            continue
        }

        if ($candidate.import_status -and $candidate.import_status -ne 'pending' -and $candidate.created_archive_id) {
            $results += [pscustomobject](ConvertTo-BackfillResult -Candidate $candidate -Status 'skipped_manifest_state' -Reason 'Manifest already records a non-pending import state.' -CreatedArchiveId ([int]$candidate.created_archive_id))
            continue
        }

        if ($candidate.source_type -eq 'bambu_studio_source_3mf' -and -not $AllowSourceImport.IsPresent) {
            $results += [pscustomobject](ConvertTo-BackfillResult -Candidate $candidate -Status 'manual_review_source_only' -Reason 'Source-project 3mf skipped by default. Pass -AllowSourceProjectImport to upload it.')
            continue
        }

        if ($Action -eq 'Inspect') {
            $results += [pscustomobject](ConvertTo-BackfillResult -Candidate $candidate -Status 'inspect_ready' -Reason 'Candidate passed hash dedupe and is eligible for upload.')
            continue
        }

        $created = Invoke-ArchiveUpload -Url $Url -TargetPrinterId $TargetPrinterId -Path ([string]$candidate.source_path) -Headers $Headers
        if ($Action -eq 'Upload') {
            $results += [pscustomobject](ConvertTo-BackfillResult -Candidate $candidate -Status 'uploaded' -Reason 'Archive created from manifest candidate.' -CreatedArchiveId ([int]$created.id))
            continue
        }

        $notePayload = [ordered]@{
            import_source = $candidate.source_type
            source_sha256 = $candidate.source_sha256
            source_md5 = $candidate.source_md5
            source_path = $candidate.relative_path
            confidence = $candidate.confidence
            last_write_time = $candidate.last_write_time
            timestamp_evidence = $candidate.timestamp_evidence
        }

        $updated = Update-Archive -Url $Url -ArchiveId ([int]$created.id) -Headers $Headers -Body ([ordered]@{
            tags = (Join-TagString -ExistingTags $created.tags -AdditionalTags @('historical_import', ('import_source:{0}' -f $candidate.source_type)))
            notes = (Append-NotesBlock -ExistingNotes $created.notes -Block (New-HistoricalImportBlock -Payload $notePayload))
        })

        $results += [pscustomobject](ConvertTo-BackfillResult -Candidate $candidate -Status 'uploaded_and_annotated' -Reason 'Archive created and annotated with historical import provenance.' -CreatedArchiveId ([int]$updated.id))
    }

    [PSCustomObject]@{
        mode = 'Backfill'
        action = $Action
        manifest_path = (Resolve-Path -LiteralPath $Path).Path
        candidate_count = $candidates.Count
        existing_archive_count = $existingArchives.Count
        results = $results
    } | ConvertTo-Json -Depth 12
}

$headers = New-Headers -Key $ApiKey
$isBackfillMode = $Mode -eq 'Backfill'

if ($isBackfillMode) {
    Invoke-BackfillMode -Url $BaseUrl -TargetPrinterId $PrinterId -Path $ManifestPath -Action $BackfillAction -Headers $headers -EntryId $ManifestEntryId -AllowSourceImport:$AllowSourceProjectImport
    return
}

Assert-Required -Value $BaseUrl -Name 'BaseUrl'
Assert-Required -Value $PrinterId -Name 'PrinterId'
Assert-Required -Value $FallbackArchiveId -Name 'FallbackArchiveId'
Assert-Required -Value $SourceFilePath -Name 'SourceFilePath'

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

if ($ExistingReplacementArchiveId -gt 0) {
    if ($Mode -ne 'Full') {
        throw 'ExistingReplacementArchiveId is only supported with Mode Full.'
    }

    $newArchive = Get-ArchiveDetail -Url $BaseUrl -ArchiveId $ExistingReplacementArchiveId -Headers $headers
}
else {
    $newArchive = Invoke-ArchiveUpload -Url $BaseUrl -TargetPrinterId $PrinterId -Path $resolvedSourcePath -Headers $headers
    [PSCustomObject]@{
        uploaded_archive_id = $newArchive.id
        uploaded_status = $newArchive.status
        uploaded_file_path = $newArchive.file_path
        uploaded_thumbnail_path = $newArchive.thumbnail_path
        uploaded_content_hash = $newArchive.content_hash
    } | ConvertTo-Json -Depth 8
}

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