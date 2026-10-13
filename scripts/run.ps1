param(
    [ValidateRange(1024, 65535)][int]$Port = 8080,
    [switch]$CheckOnly,
    [switch]$Offline
)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw 'Python environment missing. Follow README section 2 to create .venv and install dependencies.'
}
$previousGeminiMode = [Environment]::GetEnvironmentVariable('CULTUREBRIDGE_GEMINI_ENABLED', 'Process')
Push-Location -LiteralPath $projectRoot
try {
    if ($Offline) { [Environment]::SetEnvironmentVariable('CULTUREBRIDGE_GEMINI_ENABLED', 'false', 'Process') }
    & $pythonPath -c "import sys, fastapi, nicegui, google.genai, langgraph; from culturebridge.config import get_settings; s=get_settings(); print('Python:', sys.version.split()[0]); print('AI mode:', 'Gemini configured' if s.gemini_api_key and s.gemini_enabled else 'local data'); print('Imports: OK')"
    if ($LASTEXITCODE -ne 0) { throw 'Environment check failed. Reinstall project dependencies.' }
    if ($CheckOnly) { exit 0 }
    Write-Host "Web: http://127.0.0.1:$Port/"
    Write-Host "Kiosk: http://127.0.0.1:$Port/kiosk"
    Write-Host 'Stop the server with Ctrl+C. Keep this terminal open during the demo.'
    & $pythonPath -m uvicorn culturebridge.main:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Server exited with an error. Check whether the port is already in use.' }
} finally {
    [Environment]::SetEnvironmentVariable('CULTUREBRIDGE_GEMINI_ENABLED', $previousGeminiMode, 'Process')
    Pop-Location
}
