$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Get-WindowsPowerShellPath {
    $path = Join-Path `
        $env:SystemRoot `
        "System32\WindowsPowerShell\v1.0\powershell.exe"
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Windows PowerShell 5.1 is required for Authenticode validation: $path"
    }
    return $path
}

function Select-SidecarArtifact {
    param(
        [Parameter(Mandatory = $true)]
        [string] $BinaryRoot,
        [Parameter(Mandatory = $true)]
        [string] $HostTriple
    )

    $expectedPath = Join-Path `
        $BinaryRoot `
        "agent-crossbar-sidecar-$HostTriple.exe"
    if (-not (Test-Path -LiteralPath $expectedPath -PathType Leaf)) {
        throw "The sidecar build did not produce the artifact for host triple '$HostTriple': $expectedPath"
    }
    return Get-Item -LiteralPath $expectedPath
}

function Select-SingleNewMsi {
    param(
        [Parameter(Mandatory = $true)]
        [string] $BundleDirectory,
        [string[]] $BeforePaths = @(),
        [Parameter(Mandatory = $true)]
        [datetime] $BuildStartedAt
    )

    if (-not (Test-Path -LiteralPath $BundleDirectory -PathType Container)) {
        throw "The MSI bundle directory does not exist: $BundleDirectory"
    }

    $existing = @(
        $BeforePaths |
            ForEach-Object { [System.IO.Path]::GetFullPath($_) }
    )
    $created = @(
        Get-ChildItem `
            -LiteralPath $BundleDirectory `
            -Filter "*.msi" `
            -File |
            Where-Object {
                $fullName = [System.IO.Path]::GetFullPath($_.FullName)
                $fullName -notin $existing -or (
                    $fullName -in $existing -and
                    $_.LastWriteTimeUtc -ge $BuildStartedAt.ToUniversalTime()
                )
            }
    )
    if ($created.Count -ne 1) {
        throw "The MSI bundle command must create or replace exactly one installer; found $($created.Count)."
    }
    return $created[0]
}

function Normalize-ReleaseThumbprint {
    param([AllowNull()][string] $Value)

    if ([string]::IsNullOrWhiteSpace($Value)) {
        return $null
    }
    return ($Value -replace "\s", "").ToUpperInvariant()
}

function Test-SigningReport {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Report,
        [AllowNull()]
        [string] $ExpectedThumbprint,
        [AllowNull()]
        [string] $ExpectedSubject
    )

    if ($Report.status -ne "signed") {
        return $false
    }
    $files = @($Report.files)
    if ($files.Count -eq 0) {
        return $false
    }

    $normalizedThumbprint = Normalize-ReleaseThumbprint -Value $ExpectedThumbprint
    foreach ($file in $files) {
        if (-not $file.valid) {
            return $false
        }
        if (
            $normalizedThumbprint -and
            (Normalize-ReleaseThumbprint -Value $file.thumbprint) -ne $normalizedThumbprint
        ) {
            return $false
        }
        if (
            -not [string]::IsNullOrWhiteSpace($ExpectedSubject) -and
            [string]::Equals(
                $file.subject,
                $ExpectedSubject,
                [System.StringComparison]::OrdinalIgnoreCase
            ) -eq $false
        ) {
            return $false
        }
    }
    return $true
}

function Get-ReleaseSha256 {
    param(
        [Parameter(Mandatory = $true)]
        [string] $LiteralPath
    )

    $stream = [System.IO.File]::OpenRead($LiteralPath)
    try {
        $sha256 = [System.Security.Cryptography.SHA256]::Create()
        try {
            $bytes = $sha256.ComputeHash($stream)
        } finally {
            $sha256.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
    return ([BitConverter]::ToString($bytes) -replace "-", "").ToUpperInvariant()
}

function Assert-ReleaseManifestIntegrity {
    param(
        [Parameter(Mandatory = $true)]
        [object] $Manifest
    )

    foreach ($artifactName in @("installer", "desktopBinary", "sidecarBinary")) {
        $property = $Manifest.PSObject.Properties[$artifactName]
        if ($null -eq $property) {
            throw "Release manifest is missing the '$artifactName' artifact."
        }
        $artifact = $property.Value
        if (-not (Test-Path -LiteralPath $artifact.path -PathType Leaf)) {
            throw "Release manifest artifact is missing: $($artifact.path)"
        }
        $actualSize = (Get-Item -LiteralPath $artifact.path).Length
        if ($actualSize -ne [long]$artifact.sizeBytes) {
            throw "Release manifest size mismatch for $artifactName."
        }
        $actualHash = Get-ReleaseSha256 -LiteralPath $artifact.path
        if ($actualHash -ne ([string]$artifact.sha256).ToUpperInvariant()) {
            throw "Release manifest SHA-256 mismatch for $artifactName."
        }
    }
}
