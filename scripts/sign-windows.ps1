param(
    [Parameter(Mandatory = $true)]
    [string[]] $Files,

    [string] $CertificateThumbprint,

    [string] $PfxPath,

    [SecureString] $PfxPassword,

    [string] $TimestampUrl = "http://timestamp.digicert.com",

    [ValidateSet("auto", "signtool", "powershell")]
    [string] $Method = "auto",

    [switch] $NoTimestamp
)

$ErrorActionPreference = "Stop"

function Normalize-Thumbprint {
    param([string] $Value)

    return ($Value -replace "\s", "").ToUpperInvariant()
}

function Find-SignTool {
    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($null -ne $command) {
        return $command.Source
    }

    $kitRoots = @(
        (Join-Path ${env:ProgramFiles(x86)} "Windows Kits\10\bin"),
        (Join-Path $env:ProgramFiles "Windows Kits\10\bin")
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    foreach ($kitRoot in $kitRoots) {
        $versionDirectories = Get-ChildItem `
            -LiteralPath $kitRoot `
            -Directory `
            -ErrorAction SilentlyContinue |
            Sort-Object Name -Descending
        foreach ($versionDirectory in $versionDirectories) {
            $candidate = Join-Path $versionDirectory.FullName "x64\signtool.exe"
            if (Test-Path -LiteralPath $candidate -PathType Leaf) {
                return $candidate
            }
        }
    }

    return $null
}

function Get-SignatureReport {
    param([string] $LiteralPath)

    $signature = Get-AuthenticodeSignature -LiteralPath $LiteralPath
    $certificate = $signature.SignerCertificate
    return [pscustomobject]@{
        path = [System.IO.Path]::GetFullPath($LiteralPath)
        status = $signature.Status.ToString()
        valid = $signature.Status -eq [System.Management.Automation.SignatureStatus]::Valid
        subject = if ($null -eq $certificate) { $null } else { $certificate.Subject }
        thumbprint = if ($null -eq $certificate) { $null } else { $certificate.Thumbprint }
        message = switch ($signature.Status.ToString()) {
            "Valid" { "Authenticode signature is valid." }
            "NotSigned" { "The file is not Authenticode signed." }
            "HashMismatch" { "The file hash does not match its signature." }
            "NotTrusted" { "The signing certificate is not trusted." }
            "UnknownError" { "Windows could not verify the signature." }
            default { "The signature status is not suitable for production." }
        }
    }
}

function Get-SecureStringFromEnvironment {
    $value = [Environment]::GetEnvironmentVariable(
        "AGENT_CROSSBAR_PFX_PASSWORD",
        "Process"
    )
    if ([string]::IsNullOrEmpty($value)) {
        return $null
    }
    $secure = ConvertTo-SecureString -String $value -AsPlainText -Force
    [Environment]::SetEnvironmentVariable(
        "AGENT_CROSSBAR_PFX_PASSWORD",
        $null,
        "Process"
    )
    return $secure
}

$resolvedFiles = foreach ($file in $Files) {
    $resolved = Resolve-Path -LiteralPath $file -ErrorAction Stop
    if (-not (Test-Path -LiteralPath $resolved.Path -PathType Leaf)) {
        throw "Signing target is not a file: $($resolved.Path)"
    }
    $resolved.Path
}

$configuredThumbprint = Normalize-Thumbprint -Value $CertificateThumbprint
$configuredPfx = if ($PfxPath) {
    (Resolve-Path -LiteralPath $PfxPath -ErrorAction Stop).Path
} else {
    $null
}

if (-not $configuredThumbprint -and -not $configuredPfx) {
    $reports = @($resolvedFiles | ForEach-Object { Get-SignatureReport -LiteralPath $_ })
    [pscustomobject]@{
        status = "not_configured"
        message = "No certificate thumbprint or PFX was supplied. Nothing was signed."
        certificateThumbprint = $null
        certificateSubject = $null
        files = $reports
    } | ConvertTo-Json -Depth 5
    exit 0
}

$signTool = Find-SignTool
$effectiveMethod = $Method
if ($effectiveMethod -eq "auto") {
    $effectiveMethod = if ($null -ne $signTool) { "signtool" } else { "powershell" }
}
if ($effectiveMethod -eq "signtool" -and $null -eq $signTool) {
    throw "signtool.exe was requested but was not found. Install the Windows SDK signing tools."
}

$effectivePassword = $PfxPassword
if ($null -eq $effectivePassword) {
    $effectivePassword = Get-SecureStringFromEnvironment
}

$imported = $null
try {
    if ($configuredPfx) {
        if ($null -eq $effectivePassword) {
            if (-not [Environment]::UserInteractive) {
                throw "PFX signing requires -PfxPassword in non-interactive sessions."
            }
            $effectivePassword = Read-Host "PFX password" -AsSecureString
        }
        $imported = Import-PfxCertificate `
            -FilePath $configuredPfx `
            -CertStoreLocation "Cert:\CurrentUser\My" `
            -Password $effectivePassword `
            -Exportable:$false
        if ($null -eq $imported) {
            throw "PFX import did not return a certificate."
        }
        $configuredThumbprint = Normalize-Thumbprint -Value $imported.Thumbprint
    }

    $certificate = Get-Item -LiteralPath "Cert:\CurrentUser\My\$configuredThumbprint"
    if (-not $certificate.HasPrivateKey) {
        throw "The selected certificate does not have an accessible private key."
    }
    $configuredThumbprint = Normalize-Thumbprint -Value $certificate.Thumbprint
    $configuredSubject = $certificate.Subject

    foreach ($file in $resolvedFiles) {
        if ($effectiveMethod -eq "signtool") {
            $signArguments = @(
                "sign",
                "/fd", "SHA256",
                "/s", "My",
                "/sha1", $configuredThumbprint
            )
            if (-not $NoTimestamp -and -not [string]::IsNullOrWhiteSpace($TimestampUrl)) {
                $signArguments += @("/tr", $TimestampUrl, "/td", "SHA256")
            }
            $signArguments += $file
            & $signTool @signArguments
            if ($LASTEXITCODE -ne 0) {
                throw "signtool failed for $file with exit code $LASTEXITCODE."
            }
        } else {
            $signParameters = @{
                FilePath = $file
                Certificate = $certificate
                HashAlgorithm = "SHA256"
            }
            if (-not $NoTimestamp -and -not [string]::IsNullOrWhiteSpace($TimestampUrl)) {
                $signParameters.TimestampServer = $TimestampUrl
            }
            Set-AuthenticodeSignature @signParameters | Out-Null
        }
    }

    $reports = @($resolvedFiles | ForEach-Object { Get-SignatureReport -LiteralPath $_ })
    $invalid = @($reports | Where-Object { -not $_.valid })
    [pscustomobject]@{
        status = if ($invalid.Count -eq 0) { "signed" } else { "verification_failed" }
        message = if ($invalid.Count -eq 0) {
            "All files were signed with $effectiveMethod and validated with Authenticode."
        } else {
            "Signing ran, but at least one file failed Authenticode validation."
        }
        method = $effectiveMethod
        timestamped = -not $NoTimestamp -and -not [string]::IsNullOrWhiteSpace($TimestampUrl)
        certificateThumbprint = $configuredThumbprint
        certificateSubject = $configuredSubject
        files = $reports
    } | ConvertTo-Json -Depth 5

    if ($invalid.Count -ne 0) {
        exit 1
    }
}
finally {
    if ($null -ne $imported) {
        $importedPath = "Cert:\CurrentUser\My\$($imported.Thumbprint)"
        if (Test-Path -LiteralPath $importedPath) {
            Remove-Item -LiteralPath $importedPath -Force
        }
    }
    $effectivePassword = $null
}
