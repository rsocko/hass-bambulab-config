Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$schemeKey = 'HKCU:\Software\Classes\modelcatalog'
if (Test-Path -LiteralPath $schemeKey) {
    Remove-Item -LiteralPath $schemeKey -Recurse -Force
    Write-Host 'Removed modelcatalog:// protocol handler.'
} else {
    Write-Host 'modelcatalog:// protocol handler was not registered.'
}
