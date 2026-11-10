[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string[]]$Path,
    [string]$CertificateThumbprint = $env:YJJ_SIGNING_CERT_THUMBPRINT,
    [string]$SignTool = $env:YJJ_SIGNTOOL,
    [ValidateSet('CurrentUser','LocalMachine')][string]$StoreLocation = 'CurrentUser',
    [string]$TimestampServer = 'http://timestamp.digicert.com',
    [switch]$VerifyOnly
)

$ErrorActionPreference = 'Stop'
$files = @($Path | ForEach-Object {
    $resolved = (Resolve-Path -LiteralPath $_).Path
    if ([IO.Path]::GetExtension($resolved).ToLowerInvariant() -notin @('.exe','.dll','.msi')) {
        throw 'Only explicitly selected Windows application files may be signed.'
    }
    $resolved
})

if (-not $VerifyOnly) {
    if (-not $CertificateThumbprint) {
        throw 'No code-signing identity configured. Set YJJ_SIGNING_CERT_THUMBPRINT to an existing trusted code-signing certificate. No self-signed certificate is created.'
    }
    $thumbprint = $CertificateThumbprint.Replace(' ','')
    if ($thumbprint -notmatch '^[a-fA-F0-9]{40}$') { throw 'Invalid certificate thumbprint.' }
    $certificate = Get-Item -LiteralPath "Cert:\$StoreLocation\My\$thumbprint"
    if (-not $certificate.HasPrivateKey) { throw 'The selected certificate has no accessible private key.' }
    if ($certificate.NotBefore -gt (Get-Date) -or $certificate.NotAfter -le (Get-Date)) {
        throw 'The selected certificate is not currently valid.'
    }
    if ($certificate.Subject -eq $certificate.Issuer) {
        throw 'Self-signed certificates are not accepted for public releases.'
    }
    $usages = @($certificate.Extensions |
        Where-Object { $_.Oid.Value -eq '2.5.29.37' } |
        ForEach-Object { $_.EnhancedKeyUsages } | ForEach-Object { $_.Value })
    if ('1.3.6.1.5.5.7.3.3' -notin $usages) {
        throw 'The selected certificate is not authorized for code signing.'
    }
    $chain = New-Object Security.Cryptography.X509Certificates.X509Chain
    try {
        $chain.ChainPolicy.RevocationMode = 'Online'
        if (-not $chain.Build($certificate)) { throw 'The code-signing certificate chain is not trusted or cannot be verified.' }
    } finally { $chain.Dispose() }

    if (-not $SignTool) {
        $tool = Get-Command signtool.exe -ErrorAction SilentlyContinue
        if ($tool) { $SignTool = $tool.Source }
    }
    if (-not $SignTool) {
        $sdk = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
        if (Test-Path -LiteralPath $sdk) {
            $candidate = Get-ChildItem -LiteralPath $sdk -Directory |
                Sort-Object Name -Descending |
                ForEach-Object { Join-Path $_.FullName 'x64\signtool.exe' } |
                Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
            $SignTool = $candidate
        }
    }
    if (-not $SignTool -or -not (Test-Path -LiteralPath $SignTool)) {
        throw 'Windows SDK SignTool is required. Set YJJ_SIGNTOOL to the installed signtool.exe path.'
    }
    $timestamp = [Uri]$TimestampServer
    if (-not $timestamp.IsAbsoluteUri -or $timestamp.Scheme -notin @('https','http') -or $timestamp.UserInfo) {
        throw 'Invalid RFC 3161 timestamp server.'
    }
    foreach ($file in $files) {
        $arguments = @('sign','/fd','SHA256','/sha1',$thumbprint,'/s','My',
            '/tr',$TimestampServer,'/td','SHA256','/d','YangJianJian')
        if ($StoreLocation -eq 'LocalMachine') { $arguments += '/sm' }
        & $SignTool @arguments $file
        if ($LASTEXITCODE -ne 0) { throw 'Signing failed; this artifact must not be published as signed.' }
        & $SignTool verify /pa /all /tw $file
        if ($LASTEXITCODE -ne 0) { throw 'Authenticode verification or trusted timestamp verification failed.' }
    }
}

$report = @()
foreach ($file in $files) {
    $signature = Get-AuthenticodeSignature -LiteralPath $file
    if ($signature.Status -ne 'Valid' -or -not $signature.TimeStamperCertificate) {
        throw ('A valid, timestamped Authenticode signature is required: ' + [IO.Path]::GetFileName($file) +
            ' (status: ' + $signature.Status + ')')
    }
    if ($CertificateThumbprint -and
        $signature.SignerCertificate.Thumbprint -ne $CertificateThumbprint.Replace(' ','')) {
        throw 'The artifact was signed by an unexpected identity.'
    }
    $report += [ordered]@{
        name=[IO.Path]::GetFileName($file)
        status=$signature.Status.ToString()
        publisher=$signature.SignerCertificate.Subject
        certificateThumbprint=$signature.SignerCertificate.Thumbprint
        timestamped=$true
        sha256=(Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant()
    }
}
$report | ConvertTo-Json -Depth 4
