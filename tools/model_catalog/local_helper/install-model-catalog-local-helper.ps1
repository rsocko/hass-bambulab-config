param(
    [string]$SidecarBaseUrl = 'http://model-catalog.socko.us',
    [string]$SlicerExecutablePath = ''
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$helperPath = Join-Path $root 'model-catalog-local-helper.ps1'
$configPath = Join-Path $root 'config.json'

$config = @{ sidecarBaseUrl = $SidecarBaseUrl.TrimEnd('/'); slicerExecutablePath = $SlicerExecutablePath } | ConvertTo-Json
Set-Content -LiteralPath $configPath -Value $config -Encoding UTF8

$schemeKey = 'HKCU:\Software\Classes\modelcatalog'
$commandKey = Join-Path $schemeKey 'shell\open\command'
New-Item -Path $commandKey -Force | Out-Null
Set-Item -Path $schemeKey -Value 'URL:Model Catalog Protocol' -Force
Set-ItemProperty -Path $schemeKey -Name 'URL Protocol' -Value '' -Force
$command = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $helperPath + '" "%1"'
Set-Item -Path $commandKey -Value $command -Force
Write-Host 'Registered modelcatalog:// protocol handler.'
Write-Host ('Config written to ' + $configPath)
