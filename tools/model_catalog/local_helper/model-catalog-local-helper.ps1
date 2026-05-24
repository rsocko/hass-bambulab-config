param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$ProtocolUri
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Show-HelperError {
    param([string]$Message)
    Add-Type -AssemblyName PresentationFramework -ErrorAction SilentlyContinue
    [void][System.Windows.MessageBox]::Show($Message, 'Model Catalog Local Helper')
}

function Get-HelperRoot {
    if (-not [string]::IsNullOrWhiteSpace($PSScriptRoot)) {
        return $PSScriptRoot
    }
    if (-not [string]::IsNullOrWhiteSpace($PSCommandPath)) {
        return Split-Path -Parent $PSCommandPath
    }
    throw 'Could not determine helper script root.'
}

function Get-Config {
    $root = Get-HelperRoot
    $configPath = Join-Path $root 'config.json'
    if (-not (Test-Path -LiteralPath $configPath)) {
        throw "Helper config not found at $configPath. Copy config.example.json to config.json and set sidecarBaseUrl."
    }
    $raw = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $baseUrl = [string]($raw.sidecarBaseUrl)
    if ([string]::IsNullOrWhiteSpace($baseUrl)) {
        throw 'Helper config sidecarBaseUrl is empty.'
    }
    return @{ sidecarBaseUrl = $baseUrl.TrimEnd('/') }
}

function Get-ProtocolRequest {
    param([string]$UriText)
    $uri = [System.Uri]$UriText
    $actionHost = [string]$uri.Host
    $query = [System.Web.HttpUtility]::ParseQueryString($uri.Query)
    $token = [string]$query.Get('token')
    if ([string]::IsNullOrWhiteSpace($token)) {
        throw 'Protocol URI did not include token.'
    }
    return @{ action = $actionHost; token = $token }
}

function Resolve-LocalAction {
    param(
        [string]$BaseUrl,
        [string]$Token
    )
    $payload = @{ token = $Token } | ConvertTo-Json -Compress
    return Invoke-RestMethod -Method Post -Uri ($BaseUrl + '/api/local-actions/resolve') -ContentType 'application/json' -Body $payload
}

function Resolve-ClientPath {
    param($PathPayload)
    $oneDriveRelative = [string]($PathPayload.one_drive_consumer_relative_path)
    $oneDriveRoot = if (-not [string]::IsNullOrWhiteSpace($env:OneDriveConsumer)) {
        $env:OneDriveConsumer
    } elseif (-not [string]::IsNullOrWhiteSpace($env:OneDrive)) {
        $env:OneDrive
    } else {
        ''
    }
    if (-not [string]::IsNullOrWhiteSpace($oneDriveRelative) -and -not [string]::IsNullOrWhiteSpace($oneDriveRoot)) {
        return Join-Path $oneDriveRoot $oneDriveRelative
    }
    $windowsPath = [string]($PathPayload.windows_path)
    if (-not [string]::IsNullOrWhiteSpace($windowsPath)) {
        return $windowsPath
    }
    throw 'Resolve payload did not include a usable local path.'
}

function Invoke-OpenFolder {
    param(
        [string]$ResolvedPath,
        $PathPayload
    )
    $targetPath = $ResolvedPath
    if (-not [bool]$PathPayload.is_dir -and [bool]$PathPayload.is_file) {
        $targetPath = Split-Path -Parent $ResolvedPath
    }
    if (-not (Test-Path -LiteralPath $targetPath)) {
        throw "Folder path does not exist: $targetPath"
    }
    Start-Process -FilePath 'explorer.exe' -ArgumentList ('"' + $targetPath + '"') | Out-Null
}

function Invoke-OpenLocalFile {
    param(
        [string]$ResolvedPath,
        $PathPayload
    )
    if (-not [bool]$PathPayload.is_file) {
        throw 'Resolved local action is not a file.'
    }
    if (-not (Test-Path -LiteralPath $ResolvedPath)) {
        throw "File path does not exist: $ResolvedPath"
    }
    Start-Process -FilePath $ResolvedPath | Out-Null
}

try {
    $config = Get-Config
    $request = Get-ProtocolRequest -UriText $ProtocolUri
    $resolved = Resolve-LocalAction -BaseUrl $config.sidecarBaseUrl -Token $request.token
    if (-not $resolved.success) {
        throw 'Helper resolve request failed.'
    }
    $pathPayload = $resolved.path
    $clientPath = Resolve-ClientPath -PathPayload $pathPayload
    switch ([string]$resolved.action) {
        'open_folder' { Invoke-OpenFolder -ResolvedPath $clientPath -PathPayload $pathPayload }
        'open_local' { Invoke-OpenLocalFile -ResolvedPath $clientPath -PathPayload $pathPayload }
        default { throw "Unsupported local action: $($resolved.action)" }
    }
} catch {
    Show-HelperError -Message ([string]$_.Exception.Message)
    exit 1
}
