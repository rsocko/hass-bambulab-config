param(
    [string]$BaseUrl = "",
    [string]$PythonExe = "",
    [ValidateSet("text", "json")]
    [string]$Output = "text",
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$UploaderArgs = @()
)

$ErrorActionPreference = "Stop"

$defaultBaseUrl = "http://model-catalog.socko.us"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = [System.IO.Path]::GetFullPath((Join-Path $scriptDir "..\..\.."))
$uploaderPath = Join-Path $scriptDir "uploader.py"

if (-not $BaseUrl) {
    $BaseUrl = [string]$env:MODEL_CATALOG_STREAMDECK_BASE_URL
}

if (-not $BaseUrl) {
    $BaseUrl = $defaultBaseUrl
}

if (-not $PythonExe) {
    $venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        $PythonExe = $venvPython
    }
}

if (-not $PythonExe) {
    $pyCommand = Get-Command py -ErrorAction SilentlyContinue
    if ($pyCommand) {
        $PythonExe = $pyCommand.Source
    }
}

if (-not $PythonExe) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $PythonExe = $pythonCommand.Source
    }
}

if (-not $PythonExe) {
    Write-Error "Could not find a Python interpreter."
    exit 1
}

$arguments = @($uploaderPath, "--base-url", $BaseUrl, "--output", $Output) + $UploaderArgs

if ([System.IO.Path]::GetFileName($PythonExe).Equals("py.exe", [System.StringComparison]::OrdinalIgnoreCase)) {
    $arguments = @("-3") + $arguments
}

& $PythonExe @arguments
exit $LASTEXITCODE
