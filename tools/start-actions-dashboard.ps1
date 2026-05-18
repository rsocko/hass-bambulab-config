<# 
  GitHub Actions Dashboard Launcher
  Starts a local HTTP server and opens the dashboard in your default browser.
  Usage: Right-click → Run with PowerShell, or run from terminal.
#>

$port = 9090
$dir  = $PSScriptRoot
$url  = "http://localhost:$port/gh-actions-dashboard.html"

# Check if port is already in use
$inUse = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
if ($inUse) {
    Write-Host "Port $port already in use — opening browser to existing server" -ForegroundColor Yellow
    Start-Process $url
    exit
}

Write-Host "Starting HTTP server on port $port..." -ForegroundColor Cyan
Write-Host "Dashboard: $url" -ForegroundColor Green
Write-Host "Press Ctrl+C to stop.`n" -ForegroundColor DarkGray

# Open browser after a brief delay
Start-Job -ScriptBlock {
    param($u)
    Start-Sleep -Milliseconds 800
    Start-Process $u
} -ArgumentList $url | Out-Null

# Start Python HTTP server (blocking — Ctrl+C to stop)
try {
    python -m http.server $port --directory $dir 2>&1
} catch {
    Write-Host "`nServer stopped." -ForegroundColor DarkGray
}
