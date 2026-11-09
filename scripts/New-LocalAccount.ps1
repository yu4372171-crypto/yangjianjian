[CmdletBinding()]
param(
    [string]$Username = "local-owner",
    [string]$OutputPath = ".env.local"
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Missing .venv. Run scripts/build.ps1 first."
}
if (-not [IO.Path]::IsPathRooted($OutputPath)) {
    $OutputPath = Join-Path $repoRoot $OutputPath
}

$secure = Read-Host "Password for $Username" -AsSecureString
$pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $password = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    $hash = $password | & $python (Join-Path $PSScriptRoot "hash-password.py")
    if ($LASTEXITCODE -ne 0) {
        throw "Password hash generation failed."
    }
}
finally {
    if ($pointer -ne [IntPtr]::Zero) {
        [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer)
    }
    $password = $null
}

$content = @(
    "YJJ_ADMIN_USER=$Username"
    "YJJ_ADMIN_PASSWORD_HASH=$($hash.Trim())"
) -join [Environment]::NewLine
Set-Content -LiteralPath $OutputPath -Value ($content + [Environment]::NewLine) -Encoding utf8
Write-Host "Local account configuration written to $OutputPath"
Write-Host "This file is ignored by Git. Do not send it to customers."
