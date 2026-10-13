param([ValidateSet('.venv', '.venv313')][string]$Environment = '.venv')

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot "$Environment\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $pythonPath -PathType Leaf)) {
    throw 'Python environment missing. Follow README section 2.'
}
$previousGeminiMode = [Environment]::GetEnvironmentVariable('CULTUREBRIDGE_GEMINI_ENABLED', 'Process')
Push-Location -LiteralPath $projectRoot
try {
    [Environment]::SetEnvironmentVariable('CULTUREBRIDGE_GEMINI_ENABLED', 'false', 'Process')
    & $pythonPath -m ruff check .
    if ($LASTEXITCODE -ne 0) { throw 'Code checks failed.' }
    & $pythonPath -m ruff format --check .
    if ($LASTEXITCODE -ne 0) { throw 'Formatting check failed.' }
    & $pythonPath -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed.' }
    Write-Host 'All checks passed. No live Gemini call was made.'
} finally {
    [Environment]::SetEnvironmentVariable('CULTUREBRIDGE_GEMINI_ENABLED', $previousGeminiMode, 'Process')
    Pop-Location
}
