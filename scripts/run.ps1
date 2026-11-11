param(
    [ValidateRange(1024, 65535)][int]$Port = 8080,
    [switch]$CheckOnly,
    [switch]$Offline,
    [switch]$Online,
    [ValidateSet('.venv', '.venv313')][string]$Environment = '.venv'
)

$ErrorActionPreference = 'Stop'
if ($Offline -and $Online) {
    throw 'Choose either -Online (Gemini) or -Offline (local data), not both.'
}
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot "$Environment\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw 'Python environment missing. Follow README section 2 to create .venv and install dependencies.'
}
$pythonVersion = & $pythonPath --version 2>$null
if ($LASTEXITCODE -ne 0) {
    throw 'Python environment is broken: its base Python was moved or removed. Recreate .venv and install dependencies as in README section 2.'
}
$previousGeminiMode = [Environment]::GetEnvironmentVariable('CULTUREBRIDGE_GEMINI_ENABLED', 'Process')
Push-Location -LiteralPath $projectRoot
try {
    # Do not inherit a stale false value from a previous check/demo terminal.
    # Normal startup uses Gemini; local-only startup requires explicit -Offline.
    [Environment]::SetEnvironmentVariable('CULTUREBRIDGE_GEMINI_ENABLED', $(if ($Offline) { 'false' } else { 'true' }), 'Process')
    & $pythonPath -c "import sys, fastapi, nicegui, google.genai, langgraph; from culturebridge.config import get_settings; s=get_settings(); print('Python:', sys.version.split()[0]); print('AI mode:', ('Gemini configured (' + s.gemini_model + ')') if s.gemini_api_key and s.gemini_enabled else 'local data (Gemini disabled)' if not s.gemini_enabled else 'local data (GEMINI_API_KEY missing)'); print('Imports: OK')"
    if ($LASTEXITCODE -ne 0) { throw 'Environment check failed. Reinstall project dependencies.' }
    if (-not $Offline) {
        & $pythonPath -c "import sys; from culturebridge.config import get_settings; s=get_settings(); sys.exit(0 if s.gemini_enabled and s.gemini_api_key else 2)"
        if ($LASTEXITCODE -ne 0) { throw 'Gemini is not configured. Set GEMINI_API_KEY in the project .env, or use -Offline explicitly.' }
    }
    if ($CheckOnly) { exit 0 }
    $listeners = [System.Net.NetworkInformation.IPGlobalProperties]::GetIPGlobalProperties().GetActiveTcpListeners()
    if ($listeners | Where-Object { $_.Port -eq $Port -and ($_.Address.Equals([System.Net.IPAddress]::Loopback) -or $_.Address.Equals([System.Net.IPAddress]::Any)) }) {
        throw "Port $Port is already in use. Open http://127.0.0.1:$Port/ to use the running server, stop it with Ctrl+C in its terminal, or choose -Port 8081."
    }
    Write-Host "Web: http://127.0.0.1:$Port/"
    Write-Host "Kiosk: http://127.0.0.1:$Port/kiosk"
    Write-Host 'Stop the server with Ctrl+C. Keep this terminal open during the demo.'
    & $pythonPath -m uvicorn culturebridge.main:app --host 127.0.0.1 --port $Port
    if ($LASTEXITCODE -ne 0) { throw 'Server exited with an error. Check whether the port is already in use.' }
} finally {
    [Environment]::SetEnvironmentVariable('CULTUREBRIDGE_GEMINI_ENABLED', $previousGeminiMode, 'Process')
    Pop-Location
}
