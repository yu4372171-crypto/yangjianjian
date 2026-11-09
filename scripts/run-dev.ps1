[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing .venv. Run scripts/build.ps1 first."
}

$localEnvironment = Join-Path $repoRoot ".env.local"
if (Test-Path -LiteralPath $localEnvironment) {
    foreach ($line in Get-Content -LiteralPath $localEnvironment -Encoding utf8) {
        if ($line -match '^([A-Za-z_][A-Za-z0-9_]*)=(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1], $matches[2], "Process")
        }
    }
}

if (-not $env:YJJ_ADMIN_USER -or
    (-not $env:YJJ_ADMIN_PASSWORD_HASH -and -not $env:YJJ_ADMIN_PASSWORD)) {
    throw "Run scripts/New-LocalAccount.ps1 once to configure the local administrator."
}

$env:AIVE_PYTHON = $python
$env:PYTHONUTF8 = "1"
$dotnet = if ($env:YJJ_DOTNET) { $env:YJJ_DOTNET } else { "dotnet" }
& $dotnet run --project (Join-Path $repoRoot "apps\desktop\YangJianJian.Desktop.csproj")
