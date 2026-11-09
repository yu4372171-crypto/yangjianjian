[CmdletBinding()]
param(
    [switch]$SkipPythonInstall
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$artifactRoot = Join-Path $repoRoot "artifacts"
$desktopOutput = Join-Path $artifactRoot "desktop"
$venvPython = Join-Path $repoRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    python -m venv (Join-Path $repoRoot ".venv")
}

if (-not $SkipPythonInstall) {
    & $venvPython -m pip install --disable-pip-version-check -r `
        (Join-Path $repoRoot "backend\requirements.txt")
}

& $venvPython -m compileall -q (Join-Path $repoRoot "backend")
if ($LASTEXITCODE -ne 0) {
    throw "Python source validation failed."
}

dotnet restore (Join-Path $repoRoot "apps\desktop\YangJianJian.Desktop.csproj")
if ($LASTEXITCODE -ne 0) {
    throw "Desktop restore failed."
}

dotnet build (Join-Path $repoRoot "apps\desktop\YangJianJian.Desktop.csproj") `
    -c Release --no-restore -o $desktopOutput
if ($LASTEXITCODE -ne 0) {
    throw "Desktop build failed."
}

Write-Host "Desktop build: $desktopOutput"
Write-Host "Models, FFmpeg and release binaries are not included."
