param()

$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$hookPath = Join-Path $repoRoot '.githooks'
$prePushHook = Join-Path $hookPath 'pre-push'

if (-not (Test-Path $prePushHook)) {
    throw "Expected hook file was not found: $prePushHook"
}

git -C $repoRoot config core.hooksPath .githooks

Write-Host 'Configured local Git hooks path to .githooks'
Write-Host 'Pre-push hook:' $prePushHook
Write-Host 'VS Code task: Run Lovelace Resource Cache-Bust Check'