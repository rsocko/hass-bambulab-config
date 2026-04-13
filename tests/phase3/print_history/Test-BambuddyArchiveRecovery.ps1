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

    [string]$BatchId,

    [ValidateSet('Inspect', 'Upload', 'Full')]
    [string]$BackfillAction = 'Inspect',

    [string]$ManifestEntryId,

    [switch]$AllowSourceProjectImport,

    [ValidateSet('sd_cache_3mf', 'bambu_studio_exported_sliced_3mf', 'bambu_studio_source_3mf')]
    [string]$RecoverySource = 'sd_cache_3mf',

    [switch]$UpdateManifest,

    [string]$ResultPath,

    [ValidateSet('None', 'Preview', 'Apply')]
    [string]$RepairAction = 'None',

    [string]$RepairSidecarBaseUrl = 'http://127.0.0.1:8818',

    [string]$RepairSidecarToken,

    [ValidateSet('Full', 'Summary')]
    [string]$RepairResponseDetail = 'Summary',

    [switch]$RepairSetCompletedStatus,

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

function Add-NotesBlock {
    param(
        [string]$ExistingNotes,
        [string]$Block
    )

    if ([string]::IsNullOrWhiteSpace($ExistingNotes)) {
        return $Block
    }

    return ($ExistingNotes.TrimEnd() + "`n`n" + $Block)
}

function Set-ObjectPropertyValue {
    param(
        [object]$InputObject,
        [string]$Name,
        [object]$Value
    )

    if ($InputObject.PSObject.Properties.Name -contains $Name) {
        $InputObject.$Name = $Value
        return
    }

    $InputObject | Add-Member -NotePropertyName $Name -NotePropertyValue $Value
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

function Get-ManifestDocument {
    param([string]$Path)

    $manifest = Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    Normalize-ManifestDocument -Manifest $manifest
    return $manifest
}

function Save-ManifestDocument {
    param(
        [string]$Path,
        [object]$Manifest
    )

    $json = $Manifest | ConvertTo-Json -Depth 16
    Set-Content -LiteralPath $Path -Value ($json + "`n") -Encoding utf8
}

function Find-ManifestCandidate {
    param(
        [object]$Manifest,
        [string]$EntryId
    )

    foreach ($candidate in @($Manifest.candidates)) {
        if ($candidate.entry_id -eq $EntryId) {
            return $candidate
        }
    }

    return $null
}

function Get-NormalizedRelativePathForEntryId {
    param([object]$Candidate)

    $value = [string]$Candidate.relative_path
    if ([string]::IsNullOrWhiteSpace($value)) {
        $value = [string]$Candidate.source_path
    }

    return $value.Replace('\', '/').Trim().ToLowerInvariant()
}

function Get-StringSha256 {
    param([string]$Value)

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Value)
        $hashBytes = $sha.ComputeHash($bytes)
        return ([System.BitConverter]::ToString($hashBytes)).Replace('-', '').ToUpperInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Get-CanonicalManifestEntryId {
    param(
        [object]$Candidate,
        [int]$Index = 0
    )

    $sha256 = [string]$Candidate.source_sha256
    if ([string]::IsNullOrWhiteSpace($sha256)) {
        $sha256 = Get-StringSha256 -Value (Get-NormalizedRelativePathForEntryId -Candidate $Candidate)
    }

    if ($Index -le 0) {
        return $sha256
    }

    $pathHash = Get-StringSha256 -Value (Get-NormalizedRelativePathForEntryId -Candidate $Candidate)
    return ('{0}::{1}' -f $sha256, $pathHash.Substring(0, 12))
}

function Normalize-ManifestDocument {
    param([object]$Manifest)

    $grouped = @{}
    foreach ($candidate in @($Manifest.candidates)) {
        $groupKey = [string]$candidate.source_sha256
        if ([string]::IsNullOrWhiteSpace($groupKey)) {
            $groupKey = Get-NormalizedRelativePathForEntryId -Candidate $candidate
        }

        if (-not $grouped.ContainsKey($groupKey)) {
            $grouped[$groupKey] = New-Object System.Collections.ArrayList
        }

        [void]$grouped[$groupKey].Add($candidate)

        if (-not ($candidate.PSObject.Properties.Name -contains 'allow_same_content_reimport')) {
            Set-ObjectPropertyValue -InputObject $candidate -Name 'allow_same_content_reimport' -Value $false
        }
    }

    foreach ($groupKey in $grouped.Keys) {
        $ordered = @($grouped[$groupKey] | Sort-Object { Get-NormalizedRelativePathForEntryId -Candidate $_ })
        for ($index = 0; $index -lt $ordered.Count; $index++) {
            $candidate = $ordered[$index]
            Set-ObjectPropertyValue -InputObject $candidate -Name 'entry_id' -Value (Get-CanonicalManifestEntryId -Candidate $candidate -Index $index)
            Set-ObjectPropertyValue -InputObject $candidate -Name 'same_hash_group_size' -Value $ordered.Count
            Set-ObjectPropertyValue -InputObject $candidate -Name 'same_hash_group_index' -Value $index
        }
    }

    Set-ObjectPropertyValue -InputObject $Manifest -Name 'schema_version' -Value 3
    Update-ManifestSummary -Manifest $Manifest
}

function Get-ProcessingBucketForStatus {
    param(
        [string]$Status,
        [string]$CurrentBucket
    )

    switch ($Status) {
        'skipped_existing_content_hash' { return 'already_in_archive' }
        'batch_ready_same_hash_allowed' { return 'batch_ready' }
        'manual_review_source_only' { return 'manual_review' }
        'manual_review_non_importable' { return 'manual_review' }
        'batch_ready' { return 'batch_ready' }
        'uploaded' { return 'completed' }
        'uploaded_and_annotated' { return 'completed' }
        'runtime_repaired' { return 'completed' }
        'error' { return 'deferred' }
        default { return $CurrentBucket }
    }
}

function Update-ManifestSummary {
    param([object]$Manifest)

    $bucketCounts = @{}
    $batchCounts = @{}

    foreach ($candidate in @($Manifest.candidates)) {
        $bucket = [string]$candidate.processing_bucket
        if ([string]::IsNullOrWhiteSpace($bucket)) {
            $bucket = 'unclassified'
            $candidate.processing_bucket = $bucket
        }

        if ($bucketCounts.ContainsKey($bucket)) {
            $bucketCounts[$bucket] += 1
        }
        else {
            $bucketCounts[$bucket] = 1
        }

        if (-not [string]::IsNullOrWhiteSpace([string]$candidate.batch_id)) {
            $candidateBatchId = [string]$candidate.batch_id
            if ($batchCounts.ContainsKey($candidateBatchId)) {
                $batchCounts[$candidateBatchId] += 1
            }
            else {
                $batchCounts[$candidateBatchId] = 1
            }
        }
    }

    Set-ObjectPropertyValue -InputObject $Manifest -Name 'candidate_count' -Value (@($Manifest.candidates).Count)
    Set-ObjectPropertyValue -InputObject $Manifest -Name 'candidate_counts_by_bucket' -Value ([pscustomobject]$bucketCounts)
    Set-ObjectPropertyValue -InputObject $Manifest -Name 'batch_counts' -Value ([pscustomobject]$batchCounts)
}

function Set-ManifestCandidateState {
    param(
        [object]$Manifest,
        [string]$EntryId,
        [string]$Status,
        [string]$Reason,
        [Nullable[int]]$MatchedArchiveId = $null,
        [Nullable[int]]$CreatedArchiveId = $null
    )

    $candidate = Find-ManifestCandidate -Manifest $Manifest -EntryId $EntryId
    if ($null -eq $candidate) {
        return
    }

    Set-ObjectPropertyValue -InputObject $candidate -Name 'import_status' -Value $Status
    Set-ObjectPropertyValue -InputObject $candidate -Name 'processing_bucket' -Value (Get-ProcessingBucketForStatus -Status $Status -CurrentBucket ([string]$candidate.processing_bucket))
    Set-ObjectPropertyValue -InputObject $candidate -Name 'last_attempted_at' -Value ((Get-Date).ToUniversalTime().ToString('o'))
    Set-ObjectPropertyValue -InputObject $candidate -Name 'operator_note' -Value $Reason

    if ($PSBoundParameters.ContainsKey('MatchedArchiveId')) {
        Set-ObjectPropertyValue -InputObject $candidate -Name 'matched_archive_id' -Value $(if ($null -ne $MatchedArchiveId -and [int]$MatchedArchiveId -gt 0) { [int]$MatchedArchiveId } else { $null })
    }

    if ($PSBoundParameters.ContainsKey('CreatedArchiveId')) {
        Set-ObjectPropertyValue -InputObject $candidate -Name 'created_archive_id' -Value $(if ($null -ne $CreatedArchiveId -and [int]$CreatedArchiveId -gt 0) { [int]$CreatedArchiveId } else { $null })
    }

    Update-ManifestSummary -Manifest $Manifest
}

function Write-OptionalJsonFile {
    param(
        [string]$Path,
        [object]$Value
    )

    if ([string]::IsNullOrWhiteSpace($Path)) {
        return
    }

    $json = $Value | ConvertTo-Json -Depth 16
    Set-Content -LiteralPath $Path -Value ($json + "`n") -Encoding utf8
}

function ConvertTo-CompactRepairPreview {
    param([object]$Preview)

    if ($null -eq $Preview) {
        return $null
    }

    return [ordered]@{
        archive_id = $Preview.archive_id
        timing_confidence = $Preview.timing_confidence
        can_apply = $Preview.can_apply
        status = $Preview.status
        started_at = $Preview.started_at
        completed_at = $Preview.completed_at
        created_at = $Preview.created_at
        print_time_seconds = $Preview.print_time_seconds
    }
}

function ConvertTo-CompactRepairResult {
    param([object]$RepairResult)

    if ($null -eq $RepairResult) {
        return $null
    }

    $responseDetail = $null
    if ($RepairResult.PSObject.Properties.Name -contains 'response_detail') {
        $responseDetail = $RepairResult.response_detail
    }

    return [ordered]@{
        archive_id = $RepairResult.archive_id
        applied = $RepairResult.applied
        changed = $RepairResult.changed
        response_detail = $responseDetail
        updated_fields = @($RepairResult.updated_fields)
    }
}

function ConvertTo-BackfillConsoleResult {
    param([object]$Result)

    $payload = [ordered]@{
        entry_id = $Result.entry_id
        source_path = $Result.source_path
        source_type = $Result.source_type
        confidence = $Result.confidence
        status = $Result.status
        reason = $Result.reason
        matched_archive_id = $Result.matched_archive_id
        created_archive_id = $Result.created_archive_id
    }

    if ($Result.PSObject.Properties.Name -contains 'repair_preview') {
        $payload['repair_preview'] = ConvertTo-CompactRepairPreview -Preview $Result.repair_preview
    }

    if ($Result.PSObject.Properties.Name -contains 'repair_result') {
        $payload['repair_result'] = ConvertTo-CompactRepairResult -RepairResult $Result.repair_result
    }

    return $payload
}

function ConvertTo-BackfillConsoleOutput {
    param([object]$Output)

    return [ordered]@{
        mode = $Output.mode
        action = $Output.action
        manifest_path = $Output.manifest_path
        batch_id = $Output.batch_id
        candidate_count = $Output.candidate_count
        existing_archive_count = $Output.existing_archive_count
        results = @($Output.results | ForEach-Object { [pscustomobject](ConvertTo-BackfillConsoleResult -Result $_) })
    }
}

function Test-ManifestCandidateAlreadyHandled {
    param([object]$Candidate)

    if ($Candidate.created_archive_id -or $Candidate.matched_archive_id) {
        return $true
    }

    switch ([string]$Candidate.import_status) {
        'skipped_existing_content_hash' { return $true }
        'manual_review_non_importable' { return $true }
        'uploaded' { return $true }
        'uploaded_and_annotated' { return $true }
        'runtime_repaired' { return $true }
        default { return $false }
    }
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

function Get-LatestTimestampValue {
    param(
        [object[]]$Candidates,
        [string[]]$SourcePrefixes
    )

    $matches = @($Candidates | Where-Object {
        $source = [string]$_.source
        foreach ($prefix in $SourcePrefixes) {
            if ($source.StartsWith($prefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                return $true
            }
        }
        return $false
    })

    if ($matches.Count -eq 0) {
        return $null
    }

    return ($matches | Sort-Object { [datetimeoffset]$_.normalized } | Select-Object -Last 1)
}

function New-RuntimeRepairProposal {
    param(
        [object]$Candidate,
        [object]$Archive,
        [switch]$SetCompletedStatus
    )

    $timestampCandidates = @()
    if ($Candidate.timestamp_evidence -and $Candidate.timestamp_evidence.timestamp_candidates) {
        $timestampCandidates = @($Candidate.timestamp_evidence.timestamp_candidates)
    }

    $filesystemCompleted = $null
    if ($Candidate.timestamp_evidence -and $Candidate.timestamp_evidence.filesystem_last_modified) {
        $filesystemCompleted = [string]$Candidate.timestamp_evidence.filesystem_last_modified
    }

    $zipCandidate = Get-LatestTimestampValue -Candidates $timestampCandidates -SourcePrefixes @('3mf:')
    $bblCandidate = Get-LatestTimestampValue -Candidates $timestampCandidates -SourcePrefixes @('bbl:')

    $completedAt = $null
    $completedSource = $null
    if ($filesystemCompleted) {
        $completedAt = $filesystemCompleted
        $completedSource = 'filesystem_last_modified'
    }
    elseif ($zipCandidate) {
        $completedAt = [string]$zipCandidate.normalized
        $completedSource = [string]$zipCandidate.source
    }

    $startedAt = $null
    $startedSource = $null
    $startedEstimated = $false
    $printTimeSeconds = 0
    if ($Archive.print_time_seconds) {
        $printTimeSeconds = [int]$Archive.print_time_seconds
    }
    if ($completedAt -and $printTimeSeconds -gt 0) {
        $startedAt = ([datetimeoffset]$completedAt).AddSeconds(-1 * $printTimeSeconds).ToString('o')
        $startedSource = 'completed_at_minus_print_time_seconds'
        $startedEstimated = $true
    }

    $createdAt = $completedAt
    $createdSource = $completedSource

    $timingConfidence = 'low'
    if (($Candidate.source_type -eq 'sd_cache_3mf' -or $Candidate.source_type -eq 'bambu_studio_exported_sliced_3mf') -and $completedAt) {
        if ($zipCandidate -or $bblCandidate) {
            $timingConfidence = 'medium'
        }
    }

    $statusValue = $null
    if ($SetCompletedStatus.IsPresent -and $timingConfidence -ne 'low' -and [string]$Archive.status -eq 'archived') {
        $statusValue = 'completed'
    }

    return [ordered]@{
        archive_id = $Archive.id
        timing_confidence = $timingConfidence
        completed_at = $completedAt
        completed_at_source = $completedSource
        started_at = $startedAt
        started_at_source = $startedSource
        started_at_estimated = $startedEstimated
        created_at = $createdAt
        created_at_source = $createdSource
        status = $statusValue
        failure_reason = $null
        print_time_seconds = $printTimeSeconds
        can_apply = [bool]($timingConfidence -ne 'low' -and $completedAt)
        review_reason = $(if ($timingConfidence -eq 'low') { 'Only weak timestamp evidence is available; keep as preview-only provenance.' } else { 'Candidate has enough evidence for an operator-approved runtime repair.' })
    }
}

function Invoke-RuntimeRepair {
    param(
        [hashtable]$Proposal,
        [string]$SidecarBaseUrl,
        [string]$SidecarToken,
        [switch]$Apply,
        [string]$AuditNote,
        [string]$ResponseDetail = 'Summary'
    )

    if ([string]::IsNullOrWhiteSpace($SidecarToken)) {
        throw 'Runtime repair via sidecar requires -RepairSidecarToken or REPAIR_API_TOKEN.'
    }

    $payload = [ordered]@{
        archive_id = [int]$Proposal.archive_id
        started_at = $(if ($Proposal.started_at) { [string]$Proposal.started_at } else { $null })
        completed_at = $(if ($Proposal.completed_at) { [string]$Proposal.completed_at } else { $null })
        created_at = $(if ($Proposal.created_at) { [string]$Proposal.created_at } else { $null })
        status = $(if ($Proposal.status) { [string]$Proposal.status } else { $null })
        failure_reason = $(if ($Proposal.failure_reason) { [string]$Proposal.failure_reason } else { $null })
        audit_note = $AuditNote
        dry_run = (-not $Apply.IsPresent)
        response_detail = $ResponseDetail.ToLowerInvariant()
    }

    $headers = @{ Authorization = "Bearer $SidecarToken" }
    $body = $payload | ConvertTo-Json -Depth 10
    return Invoke-RestMethod -Method Post -Uri ($SidecarBaseUrl.TrimEnd('/') + '/admin/archive-runtime-repair') -Headers $headers -ContentType 'application/json' -Body $body
}

function Set-ManifestCandidateRepairState {
    param(
        [object]$Manifest,
        [string]$EntryId,
        [string]$RepairStatus,
        [object]$RepairPreview = $null,
        [string]$RepairConfidence = $null,
        [bool]$MarkApplied = $false
    )

    $candidate = Find-ManifestCandidate -Manifest $Manifest -EntryId $EntryId
    if ($null -eq $candidate) {
        return
    }

    Set-ObjectPropertyValue -InputObject $candidate -Name 'repair_status' -Value $RepairStatus
    Set-ObjectPropertyValue -InputObject $candidate -Name 'repair_preview' -Value $RepairPreview
    Set-ObjectPropertyValue -InputObject $candidate -Name 'repair_confidence' -Value $RepairConfidence
    if ($MarkApplied) {
        Set-ObjectPropertyValue -InputObject $candidate -Name 'repair_applied_at' -Value ((Get-Date).ToUniversalTime().ToString('o'))
    }
}

function Get-ExistingCandidateRepairResult {
    param(
        [object]$Candidate,
        [string]$Url,
        [hashtable]$Headers,
        [string]$RequestedRepairAction,
        [string]$SidecarBaseUrl,
        [string]$SidecarToken,
        [string]$ResponseDetail,
        [switch]$SetCompletedStatus
    )

    if (-not $Candidate.created_archive_id) {
        return $null
    }

    $archiveDetail = Get-ArchiveDetail -Url $Url -ArchiveId ([int]$Candidate.created_archive_id) -Headers $Headers
    $repairPreview = New-RuntimeRepairProposal -Candidate $Candidate -Archive $archiveDetail -SetCompletedStatus:$SetCompletedStatus
    $repairResult = $null

    if ($RequestedRepairAction -eq 'Apply') {
        if (-not $repairPreview.can_apply) {
            throw 'Repair apply requested, but inferred timing confidence is too low for canonical runtime changes.'
        }

        $auditNote = ('Historical import runtime repair from {0} ({1})' -f $Candidate.relative_path, $repairPreview.timing_confidence)
        $repairResult = Invoke-RuntimeRepair -Proposal $repairPreview -SidecarBaseUrl $SidecarBaseUrl -SidecarToken $SidecarToken -Apply -AuditNote $auditNote -ResponseDetail $ResponseDetail
    }
    elseif ($RequestedRepairAction -eq 'Preview') {
        $auditNote = ('Historical import runtime repair preview from {0} ({1})' -f $Candidate.relative_path, $repairPreview.timing_confidence)
        $repairResult = Invoke-RuntimeRepair -Proposal $repairPreview -SidecarBaseUrl $SidecarBaseUrl -SidecarToken $SidecarToken -AuditNote $auditNote -ResponseDetail $ResponseDetail
    }

    return [ordered]@{
        preview = $repairPreview
        result = $repairResult
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
        [switch]$AllowSourceImport,
        [string]$TargetBatchId,
        [switch]$PersistManifestState,
        [string]$OutputPath
    )

    Assert-Required -Value $Url -Name 'BaseUrl'
    Assert-Required -Value $TargetPrinterId -Name 'PrinterId'
    Assert-Required -Value $Path -Name 'ManifestPath'

    $manifestDocument = Get-ManifestDocument -Path $Path
    $candidates = @($manifestDocument.candidates)
    if (-not [string]::IsNullOrWhiteSpace($EntryId)) {
        $candidates = @($candidates | Where-Object { $_.entry_id -eq $EntryId -or $_.source_sha256 -eq $EntryId -or $_.source_path -eq $EntryId })
    }
    if (-not [string]::IsNullOrWhiteSpace($TargetBatchId)) {
        $candidates = @($candidates | Where-Object { $_.batch_id -eq $TargetBatchId })
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
        try {
            $existing = Find-ExistingArchiveByHash -Archives $existingArchives -Sha256 ([string]$candidate.source_sha256)
            if ($existing) {
                if ($RepairAction -ne 'None' -and $candidate.created_archive_id -and [int]$existing.id -eq [int]$candidate.created_archive_id) {
                    $repairOutcome = Get-ExistingCandidateRepairResult -Candidate $candidate -Url $Url -Headers $Headers -RequestedRepairAction $RepairAction -SidecarBaseUrl $RepairSidecarBaseUrl -SidecarToken $(if ($RepairSidecarToken) { $RepairSidecarToken } else { $env:REPAIR_API_TOKEN }) -ResponseDetail $RepairResponseDetail -SetCompletedStatus:$RepairSetCompletedStatus
                    $resultPayload = ConvertTo-BackfillResult -Candidate $candidate -Status $(if ($RepairAction -eq 'Apply') { 'runtime_repaired' } else { 'repair_previewed' }) -Reason $(if ($RepairAction -eq 'Apply') { 'Existing imported archive received runtime repair.' } else { 'Existing imported archive evaluated for runtime repair.' }) -MatchedArchiveId ([int]$candidate.matched_archive_id) -CreatedArchiveId ([int]$candidate.created_archive_id)
                    $resultPayload['repair_preview'] = $repairOutcome.preview
                    if ($repairOutcome.result) {
                        $resultPayload['repair_result'] = $repairOutcome.result
                    }
                    $results += [pscustomobject]$resultPayload

                    if ($PersistManifestState.IsPresent) {
                        Set-ManifestCandidateRepairState -Manifest $manifestDocument -EntryId ([string]$candidate.entry_id) -RepairStatus $(if ($RepairAction -eq 'Apply') { 'applied' } else { 'previewed' }) -RepairPreview $repairOutcome.preview -RepairConfidence ([string]$repairOutcome.preview.timing_confidence) -MarkApplied:($RepairAction -eq 'Apply')
                        Save-ManifestDocument -Path $Path -Manifest $manifestDocument
                    }
                    continue
                }

                $allowSameContentReimport = $false
                if ($candidate.PSObject.Properties.Name -contains 'allow_same_content_reimport') {
                    $allowSameContentReimport = [bool]$candidate.allow_same_content_reimport
                }

                if ($allowSameContentReimport) {
                    if ($Action -eq 'Inspect') {
                        $result = [pscustomobject](ConvertTo-BackfillResult -Candidate $candidate -Status 'batch_ready_same_hash_allowed' -Reason ('Candidate shares content_hash with archive {0}, but manifest explicitly allows same-content reimport.' -f [int]$existing.id) -MatchedArchiveId ([int]$existing.id))
                        $results += $result
                        if ($PersistManifestState.IsPresent) {
                            Set-ManifestCandidateState -Manifest $manifestDocument -EntryId ([string]$candidate.entry_id) -Status 'batch_ready_same_hash_allowed' -Reason ('Candidate shares content_hash with archive {0}, but manifest explicitly allows same-content reimport.' -f [int]$existing.id)
                            Save-ManifestDocument -Path $Path -Manifest $manifestDocument
                        }
                        continue
                    }
                }
                else {
                    $result = [pscustomobject](ConvertTo-BackfillResult -Candidate $candidate -Status 'skipped_existing_content_hash' -Reason 'Existing Bambuddy archive has matching content_hash.' -MatchedArchiveId ([int]$existing.id))
                    $results += $result
                    if ($PersistManifestState.IsPresent) {
                        Set-ManifestCandidateState -Manifest $manifestDocument -EntryId ([string]$candidate.entry_id) -Status 'skipped_existing_content_hash' -Reason 'Existing Bambuddy archive has matching content_hash.' -MatchedArchiveId ([int]$existing.id)
                        Save-ManifestDocument -Path $Path -Manifest $manifestDocument
                    }
                    continue
                }
            }

            if (Test-ManifestCandidateAlreadyHandled -Candidate $candidate) {
                if ($RepairAction -ne 'None' -and $candidate.created_archive_id) {
                    $repairOutcome = Get-ExistingCandidateRepairResult -Candidate $candidate -Url $Url -Headers $Headers -RequestedRepairAction $RepairAction -SidecarBaseUrl $RepairSidecarBaseUrl -SidecarToken $(if ($RepairSidecarToken) { $RepairSidecarToken } else { $env:REPAIR_API_TOKEN }) -ResponseDetail $RepairResponseDetail -SetCompletedStatus:$RepairSetCompletedStatus
                    $resultPayload = ConvertTo-BackfillResult -Candidate $candidate -Status $(if ($RepairAction -eq 'Apply') { 'runtime_repaired' } else { 'repair_previewed' }) -Reason $(if ($RepairAction -eq 'Apply') { 'Existing imported archive received runtime repair.' } else { 'Existing imported archive evaluated for runtime repair.' }) -MatchedArchiveId ([int]$candidate.matched_archive_id) -CreatedArchiveId ([int]$candidate.created_archive_id)
                    $resultPayload['repair_preview'] = $repairOutcome.preview
                    if ($repairOutcome.result) {
                        $resultPayload['repair_result'] = $repairOutcome.result
                    }
                    $results += [pscustomobject]$resultPayload

                    if ($PersistManifestState.IsPresent) {
                        Set-ManifestCandidateRepairState -Manifest $manifestDocument -EntryId ([string]$candidate.entry_id) -RepairStatus $(if ($RepairAction -eq 'Apply') { 'applied' } else { 'previewed' }) -RepairPreview $repairOutcome.preview -RepairConfidence ([string]$repairOutcome.preview.timing_confidence) -MarkApplied:($RepairAction -eq 'Apply')
                        Save-ManifestDocument -Path $Path -Manifest $manifestDocument
                    }
                }
                else {
                    $results += [pscustomobject](ConvertTo-BackfillResult -Candidate $candidate -Status 'skipped_manifest_state' -Reason 'Manifest already records a completed or matched state.' -MatchedArchiveId ([int]$candidate.matched_archive_id) -CreatedArchiveId ([int]$candidate.created_archive_id))
                }
                continue
            }

            if ($candidate.source_type -eq 'bambu_studio_source_3mf' -and -not $AllowSourceImport.IsPresent) {
                $result = [pscustomobject](ConvertTo-BackfillResult -Candidate $candidate -Status 'manual_review_source_only' -Reason 'Source-project 3mf skipped by default. Pass -AllowSourceProjectImport to upload it.')
                $results += $result
                if ($PersistManifestState.IsPresent) {
                    Set-ManifestCandidateState -Manifest $manifestDocument -EntryId ([string]$candidate.entry_id) -Status 'manual_review_source_only' -Reason 'Source-project 3mf skipped by default. Pass -AllowSourceProjectImport to upload it.'
                    Save-ManifestDocument -Path $Path -Manifest $manifestDocument
                }
                continue
            }

            if ($Action -eq 'Inspect') {
                $result = [pscustomobject](ConvertTo-BackfillResult -Candidate $candidate -Status 'batch_ready' -Reason 'Candidate passed hash dedupe and is eligible for upload.')
                $results += $result
                if ($PersistManifestState.IsPresent) {
                    Set-ManifestCandidateState -Manifest $manifestDocument -EntryId ([string]$candidate.entry_id) -Status 'batch_ready' -Reason 'Candidate passed hash dedupe and is eligible for upload.'
                    Save-ManifestDocument -Path $Path -Manifest $manifestDocument
                }
                continue
            }

            $created = Invoke-ArchiveUpload -Url $Url -TargetPrinterId $TargetPrinterId -Path ([string]$candidate.source_path) -Headers $Headers
            $existingArchives += $created
            if ($Action -eq 'Upload') {
                $result = [pscustomobject](ConvertTo-BackfillResult -Candidate $candidate -Status 'uploaded' -Reason 'Archive created from manifest candidate.' -CreatedArchiveId ([int]$created.id))
                $results += $result
                if ($PersistManifestState.IsPresent) {
                    Set-ManifestCandidateState -Manifest $manifestDocument -EntryId ([string]$candidate.entry_id) -Status 'uploaded' -Reason 'Archive created from manifest candidate.' -CreatedArchiveId ([int]$created.id)
                    Save-ManifestDocument -Path $Path -Manifest $manifestDocument
                }
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
                notes = (Add-NotesBlock -ExistingNotes $created.notes -Block (New-HistoricalImportBlock -Payload $notePayload))
            })

            $repairPreview = $null
            $repairResult = $null
            if ($RepairAction -ne 'None') {
                $archiveDetail = Get-ArchiveDetail -Url $Url -ArchiveId ([int]$updated.id) -Headers $Headers
                $repairPreview = New-RuntimeRepairProposal -Candidate $candidate -Archive $archiveDetail -SetCompletedStatus:$RepairSetCompletedStatus

                if ($RepairAction -eq 'Apply') {
                    if (-not $repairPreview.can_apply) {
                        throw 'Repair apply requested, but inferred timing confidence is too low for canonical runtime changes.'
                    }

                    $auditNote = ('Historical import runtime repair from {0} ({1})' -f $candidate.relative_path, $repairPreview.timing_confidence)
                    $repairResult = Invoke-RuntimeRepair -Proposal $repairPreview -SidecarBaseUrl $RepairSidecarBaseUrl -SidecarToken $(if ($RepairSidecarToken) { $RepairSidecarToken } else { $env:REPAIR_API_TOKEN }) -Apply -AuditNote $auditNote -ResponseDetail $RepairResponseDetail
                }
                elseif ($RepairAction -eq 'Preview') {
                    $auditNote = ('Historical import runtime repair preview from {0} ({1})' -f $candidate.relative_path, $repairPreview.timing_confidence)
                    $repairResult = Invoke-RuntimeRepair -Proposal $repairPreview -SidecarBaseUrl $RepairSidecarBaseUrl -SidecarToken $(if ($RepairSidecarToken) { $RepairSidecarToken } else { $env:REPAIR_API_TOKEN }) -AuditNote $auditNote -ResponseDetail $RepairResponseDetail
                }
            }

            $resultPayload = ConvertTo-BackfillResult -Candidate $candidate -Status 'uploaded_and_annotated' -Reason 'Archive created and annotated with historical import provenance.' -CreatedArchiveId ([int]$updated.id)
            if ($repairPreview) {
                $resultPayload['repair_preview'] = $repairPreview
            }
            if ($repairResult) {
                $resultPayload['repair_result'] = $repairResult
            }
            $result = [pscustomobject]$resultPayload
            $results += $result
            if ($PersistManifestState.IsPresent) {
                Set-ManifestCandidateState -Manifest $manifestDocument -EntryId ([string]$candidate.entry_id) -Status 'uploaded_and_annotated' -Reason 'Archive created and annotated with historical import provenance.' -CreatedArchiveId ([int]$updated.id)
                if ($repairPreview -and $repairResult) {
                    Set-ManifestCandidateRepairState -Manifest $manifestDocument -EntryId ([string]$candidate.entry_id) -RepairStatus 'applied' -RepairPreview $repairPreview -RepairConfidence ([string]$repairPreview.timing_confidence) -MarkApplied $true
                }
                elseif ($repairPreview) {
                    Set-ManifestCandidateRepairState -Manifest $manifestDocument -EntryId ([string]$candidate.entry_id) -RepairStatus 'previewed' -RepairPreview $repairPreview -RepairConfidence ([string]$repairPreview.timing_confidence)
                }
                Save-ManifestDocument -Path $Path -Manifest $manifestDocument
            }
        }
        catch {
            $message = $_.Exception.Message
            $results += [pscustomobject](ConvertTo-BackfillResult -Candidate $candidate -Status 'error' -Reason $message -MatchedArchiveId ([int]$candidate.matched_archive_id) -CreatedArchiveId ([int]$candidate.created_archive_id))
            if ($PersistManifestState.IsPresent) {
                Set-ManifestCandidateState -Manifest $manifestDocument -EntryId ([string]$candidate.entry_id) -Status 'error' -Reason $message -MatchedArchiveId ([int]$candidate.matched_archive_id) -CreatedArchiveId ([int]$candidate.created_archive_id)
                    Save-ManifestDocument -Path $Path -Manifest $manifestDocument
            }
        }
    }

    $output = [PSCustomObject]@{
        mode = 'Backfill'
        action = $Action
        manifest_path = (Resolve-Path -LiteralPath $Path).Path
        batch_id = $TargetBatchId
        candidate_count = $candidates.Count
        existing_archive_count = $existingArchives.Count
        results = $results
    }

    Write-OptionalJsonFile -Path $OutputPath -Value $output
    (ConvertTo-BackfillConsoleOutput -Output $output) | ConvertTo-Json -Depth 8
}

$headers = New-Headers -Key $ApiKey
$isBackfillMode = $Mode -eq 'Backfill'

if ($isBackfillMode) {
    Invoke-BackfillMode -Url $BaseUrl -TargetPrinterId $PrinterId -Path $ManifestPath -Action $BackfillAction -Headers $headers -EntryId $ManifestEntryId -AllowSourceImport:$AllowSourceProjectImport -TargetBatchId $BatchId -PersistManifestState:$UpdateManifest -OutputPath $ResultPath
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
    notes = Add-NotesBlock -ExistingNotes $newArchive.notes -Block $newArchiveNoteBlock
})

$updatedOld = Update-Archive -Url $BaseUrl -ArchiveId $fallback.id -Headers $headers -Body ([ordered]@{
    tags = $oldArchiveTags
    notes = Add-NotesBlock -ExistingNotes $fallback.notes -Block $oldArchiveNoteBlock
})

[PSCustomObject]@{
    fallback_archive_id = $updatedOld.id
    replacement_archive_id = $updatedNew.id
    fallback_tags = $updatedOld.tags
    replacement_tags = $updatedNew.tags
} | ConvertTo-Json -Depth 8