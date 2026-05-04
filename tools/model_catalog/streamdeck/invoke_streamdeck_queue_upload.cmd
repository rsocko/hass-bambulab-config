@echo off
setlocal

rem Default sidecar URL is http://model-catalog.socko.us.
rem Uncomment the next line only if you want the button to target a different sidecar host.
rem set "MODEL_CATALOG_STREAMDECK_BASE_URL=http://YOUR-SIDECAR-HOST:8314"

set "SCRIPT_DIR=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT_DIR%invoke_streamdeck_queue_upload.ps1" %*
exit /b %ERRORLEVEL%