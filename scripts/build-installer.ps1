param(
    [switch] $SkipTests,
    [switch] $RequireProduction
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $PSScriptRoot
$buildRoot = Join-Path $projectRoot ".build"
$releaseRoot = Join-Path $buildRoot "release"
$configuredCargoTarget = $env:CARGO_TARGET_DIR
if ([string]::IsNullOrWhiteSpace($configuredCargoTarget)) {
    $cargoTargetRoot = Join-Path $projectRoot "src-tauri\target"
} elseif ([System.IO.Path]::IsPathRooted($configuredCargoTarget)) {
    $cargoTargetRoot = [System.IO.Path]::GetFullPath($configuredCargoTarget)
} else {
    $cargoTargetRoot = [System.IO.Path]::GetFullPath(
        (Join-Path $projectRoot $configuredCargoTarget)
    )
}
$bundleRoot = Join-Path $cargoTargetRoot "release\bundle"
$mainBinary = Join-Path $cargoTargetRoot "release\agent-crossbar.exe"
$signer = Join-Path $PSScriptRoot "sign-windows.ps1"
$releaseHelpers = Join-Path $PSScriptRoot "build-installer.helpers.ps1"
$certificateThumbprint = $env:AGENT_CROSSBAR_CERT_THUMBPRINT
$pfxPath = $env:AGENT_CROSSBAR_PFX_PATH
$updatePrivateKey = $env:TAURI_SIGNING_PRIVATE_KEY
$updatePrivateKeyPath = $env:TAURI_SIGNING_PRIVATE_KEY_PATH
$updatePublicKey = $env:AGENT_CROSSBAR_UPDATE_PUBKEY

. $releaseHelpers
$windowsPowerShell = Get-WindowsPowerShellPath

function Get-Base64Text {
    param(
        [Parameter(Mandatory = $true)]
        [string] $LiteralPath
    )

    $bytes = [System.IO.File]::ReadAllBytes($LiteralPath)
    return [Convert]::ToBase64String($bytes)
}

function Write-Base64DecodedFile {
    param(
        [Parameter(Mandatory = $true)]
        [string] $LiteralPath,
        [Parameter(Mandatory = $true)]
        [string] $Base64
    )

    [System.IO.File]::WriteAllBytes($LiteralPath, [Convert]::FromBase64String($Base64))
}

function Write-Utf8File {
    param(
        [Parameter(Mandatory = $true)]
        [string] $LiteralPath,
        [Parameter(Mandatory = $true)]
        [string] $Content
    )

    $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($LiteralPath, $Content, $utf8WithoutBom)
}

function Invoke-Signing {
    param(
        [Parameter(Mandatory = $true)]
        [string[]] $Files
    )

    $arguments = @{
        Files = $Files
    }
    if ($certificateThumbprint) {
        $arguments.CertificateThumbprint = $certificateThumbprint
    }
    if ($pfxPath) {
        $arguments.PfxPath = $pfxPath
    }

    $output = & $windowsPowerShell `
        -NoProfile `
        -ExecutionPolicy Bypass `
        -File $signer `
        @arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Authenticode signing failed with exit code $LASTEXITCODE."
    }
    return ($output -join "`n") | ConvertFrom-Json
}

function Resolve-UpdateArtifactUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string] $FileName
    )

    $configuredUrl = $env:AGENT_CROSSBAR_UPDATE_ARTIFACT_URL
    if (-not [string]::IsNullOrWhiteSpace($configuredUrl)) {
        $parsed = [Uri]$configuredUrl
        if ($parsed.Scheme -ne "https") {
            throw "AGENT_CROSSBAR_UPDATE_ARTIFACT_URL must use HTTPS."
        }
        return $parsed.AbsoluteUri
    }

    $endpointValue = $env:AGENT_CROSSBAR_UPDATE_ENDPOINTS
    if ([string]::IsNullOrWhiteSpace($endpointValue)) {
        return $null
    }
    $firstEndpoint = @(
        $endpointValue -split "[;,\r\n]+" |
            ForEach-Object { $_.Trim() } |
            Where-Object { $_ }
    ) | Select-Object -First 1
    if ([string]::IsNullOrWhiteSpace($firstEndpoint)) {
        return $null
    }
    $endpoint = [Uri]$firstEndpoint
    if ($endpoint.Scheme -ne "https") {
        throw "Release update endpoints must use HTTPS."
    }
    if (-not $endpoint.AbsolutePath.EndsWith("/")) {
        $lastSeparator = $endpoint.AbsolutePath.LastIndexOf("/")
        $directoryPath = if ($lastSeparator -ge 0) {
            $endpoint.AbsolutePath.Substring(0, $lastSeparator + 1)
        } else {
            "/"
        }
    } else {
        $directoryPath = $endpoint.AbsolutePath
    }
    return ([Uri]::new($endpoint, "$directoryPath$FileName")).AbsoluteUri
}

Push-Location $projectRoot
$previousTemp = $env:TEMP
$previousTmp = $env:TMP
$previousReleaseDebug = [Environment]::GetEnvironmentVariable(
    "CARGO_PROFILE_RELEASE_DEBUG",
    "Process"
)
$previousDevDebug = [Environment]::GetEnvironmentVariable(
    "CARGO_PROFILE_DEV_DEBUG",
    "Process"
)
try {
    New-Item -ItemType Directory -Force -Path $releaseRoot | Out-Null
    $env:CARGO_PROFILE_RELEASE_DEBUG = "0"
    $env:CARGO_PROFILE_DEV_DEBUG = "0"
    $env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"

    if (-not $SkipTests) {
        & npm.cmd run verify
        if ($LASTEXITCODE -ne 0) {
            throw "The full quality gate failed with exit code $LASTEXITCODE."
        }
    }

    & npm.cmd run sidecar:build
    if ($LASTEXITCODE -ne 0) {
        throw "Sidecar build failed with exit code $LASTEXITCODE."
    }

    $rustcCommand = Get-Command rustc -ErrorAction SilentlyContinue
    $rustc = if ($rustcCommand) {
        $rustcCommand.Source
    } else {
        Join-Path $env:USERPROFILE ".cargo\bin\rustc.exe"
    }
    if (-not (Test-Path -LiteralPath $rustc -PathType Leaf)) {
        throw "rustc is missing. Install the Rust toolchain before building the installer."
    }
    $targetTriple = (& $rustc --print host-tuple).Trim()
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($targetTriple)) {
        throw "rustc failed while resolving the host target."
    }
    $sidecar = Select-SidecarArtifact `
        -BinaryRoot (Join-Path $projectRoot "src-tauri\binaries") `
        -HostTriple $targetTriple

    if (-not $SkipTests) {
        & npm.cmd run sidecar:smoke
        if ($LASTEXITCODE -ne 0) {
            throw "The packaged sidecar smoke test failed with exit code $LASTEXITCODE."
        }
    }

    $sidecarSignature = Invoke-Signing -Files @($sidecar.FullName)

    & npm.cmd run tauri -- build --no-bundle
    if ($LASTEXITCODE -ne 0) {
        throw "Desktop executable build failed with exit code $LASTEXITCODE."
    }
    if (-not (Test-Path -LiteralPath $mainBinary)) {
        throw "The desktop executable is missing after the Tauri build."
    }

    $desktopSignature = Invoke-Signing -Files @($mainBinary)

    $msiDirectory = Join-Path $bundleRoot "msi"
    $msiBeforeBuild = if (Test-Path -LiteralPath $msiDirectory -PathType Container) {
        @(
            Get-ChildItem `
                -LiteralPath $msiDirectory `
                -Filter "*.msi" `
                -File |
                ForEach-Object { $_.FullName }
        )
    } else {
        @()
    }
    $msiBuildStartedAt = Get-Date
    & npm.cmd run tauri -- bundle `
        --bundles msi `
        --no-binary-patching `
        --no-sign
    if ($LASTEXITCODE -ne 0) {
        throw "MSI bundle generation failed with exit code $LASTEXITCODE."
    }

    $installer = Select-SingleNewMsi `
        -BundleDirectory $msiDirectory `
        -BeforePaths $msiBeforeBuild `
        -BuildStartedAt $msiBuildStartedAt

    # Authenticode changes the installer bytes, so it must happen before the updater
    # artifact is signed and hashed.
    $installerSignature = Invoke-Signing -Files @($installer.FullName)
    $installerAuthenticode = @($installerSignature.files)[0]

    $version = (Get-Content -Raw src-tauri\tauri.conf.json | ConvertFrom-Json).version
    $updateSignaturePath = "$($installer.FullName).sig"
    if (Test-Path -LiteralPath $updateSignaturePath) {
        Remove-Item -LiteralPath $updateSignaturePath -Force
    }

    $updateSigningConfigured =
        -not [string]::IsNullOrWhiteSpace($updatePrivateKey) -or
        -not [string]::IsNullOrWhiteSpace($updatePrivateKeyPath)
    $updateManifest = $null
    $updateVerification = $null
    $updateError = $null

    if ($updateSigningConfigured) {
        if ([string]::IsNullOrWhiteSpace($updatePublicKey)) {
            throw "TAURI_SIGNING_PRIVATE_KEY is configured but AGENT_CROSSBAR_UPDATE_PUBKEY is missing."
        }

        & npm.cmd run tauri -- signer sign $installer.FullName --app-version $version
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $updateSignaturePath)) {
            throw "Updater artifact signing failed."
        }

        $temporaryPublicKey = Join-Path $releaseRoot "updater-public-key.tmp"
        $temporarySignature = Join-Path $releaseRoot "updater-signature.tmp"
        try {
            $decodedPublicKey = [Text.Encoding]::UTF8.GetString(
                [Convert]::FromBase64String($updatePublicKey)
            )
            Write-Utf8File `
                -LiteralPath $temporaryPublicKey `
                -Content $decodedPublicKey
            Write-Base64DecodedFile `
                -LiteralPath $temporarySignature `
                -Base64 (Get-Content -LiteralPath $updateSignaturePath -Raw).Trim()
            & $env:USERPROFILE\.cargo\bin\cargo.exe run `
                --quiet `
                --manifest-path src-tauri\Cargo.toml `
                --bin verify-updater-signature `
                -- `
                --artifact $installer.FullName `
                --signature $temporarySignature `
                --public-key $temporaryPublicKey `
                --version $version
            if ($LASTEXITCODE -ne 0) {
                throw "The updater signature did not verify."
            }
            $updateVerification = [pscustomobject]@{
                status = "verified"
                signedVersion = $version
                signatureFile = $updateSignaturePath
            }
        } finally {
            Remove-Item -LiteralPath $temporaryPublicKey -Force -ErrorAction SilentlyContinue
            Remove-Item -LiteralPath $temporarySignature -Force -ErrorAction SilentlyContinue
        }

        $artifactUrl = Resolve-UpdateArtifactUrl -FileName $installer.Name
        if (-not [string]::IsNullOrWhiteSpace($artifactUrl)) {
            $signatureForManifest = Get-Base64Text -LiteralPath $updateSignaturePath
            $updateManifestObject = [ordered]@{
                version = $version
                pub_date = (Get-Date).ToUniversalTime().ToString("o")
                platforms = [ordered]@{
                    "windows-x86_64" = [ordered]@{
                        signature = $signatureForManifest
                        url = $artifactUrl
                    }
                }
            }
            $manifestPath = Join-Path $releaseRoot "latest.json"
            Write-Utf8File `
                -LiteralPath $manifestPath `
                -Content ($updateManifestObject | ConvertTo-Json -Depth 8)
            $updateManifest = [pscustomobject]@{
                status = "generated"
                path = $manifestPath
                artifactUrl = $artifactUrl
            }
        } else {
            $updateError = "Updater artifact was signed, but no HTTPS artifact URL was configured."
        }
    } else {
        $updateError = "No Tauri updater signing private key was configured."
    }

    $installerAuthenticodeValid = [bool] $installerAuthenticode.valid
    $sidecarAuthenticodeValid = Test-SigningReport `
        -Report $sidecarSignature `
        -ExpectedThumbprint $sidecarSignature.certificateThumbprint `
        -ExpectedSubject $sidecarSignature.certificateSubject
    $desktopAuthenticodeValid = Test-SigningReport `
        -Report $desktopSignature `
        -ExpectedThumbprint $desktopSignature.certificateThumbprint `
        -ExpectedSubject $desktopSignature.certificateSubject
    $installerAuthenticodeValid =
        $installerAuthenticodeValid -and
        (Test-SigningReport `
            -Report $installerSignature `
            -ExpectedThumbprint $installerSignature.certificateThumbprint `
            -ExpectedSubject $installerSignature.certificateSubject)
    $updaterReady = $null -ne $updateVerification -and $null -ne $updateManifest
    $productionReady =
        $installerAuthenticodeValid -and
        $sidecarAuthenticodeValid -and
        $desktopAuthenticodeValid -and
        $updaterReady

    if ($RequireProduction -and -not $productionReady) {
        throw "Production release requirements were not met."
    }

    $updateArtifact = [pscustomobject]@{
        status = if ($updateVerification) {
            if ($updateManifest) { "verified_and_manifested" } else { "signed_only" }
        } else {
            "not_configured"
        }
        signingConfigured = $updateSigningConfigured
        publicKeyConfigured = -not [string]::IsNullOrWhiteSpace($updatePublicKey)
        signaturePath = if (Test-Path -LiteralPath $updateSignaturePath) {
            $updateSignaturePath
        } else {
            $null
        }
        verification = $updateVerification
        manifest = $updateManifest
        error = $updateError
    }

    $manifest = [pscustomobject]@{
        status = if ($productionReady) { "passed" } else { "engineering_preview" }
        productionReady = $productionReady
        builtAt = (Get-Date).ToUniversalTime().ToString("o")
        version = $version
        packageFormat = "msi"
        installer = [pscustomobject]@{
            path = $installer.FullName
            sizeBytes = $installer.Length
            sha256 = Get-ReleaseSha256 -LiteralPath $installer.FullName
            targetTriple = $targetTriple
            signatureStatus = $installerAuthenticode.status
            signatureValid = $installerAuthenticodeValid
            signerSubject = $installerAuthenticode.subject
        }
        desktopBinary = [pscustomobject]@{
            path = $mainBinary
            sizeBytes = (Get-Item -LiteralPath $mainBinary).Length
            sha256 = Get-ReleaseSha256 -LiteralPath $mainBinary
            signatureValid = $desktopAuthenticodeValid
        }
        sidecarBinary = [pscustomobject]@{
            path = $sidecar.FullName
            sizeBytes = $sidecar.Length
            sha256 = Get-ReleaseSha256 -LiteralPath $sidecar.FullName
            targetTriple = $targetTriple
            signatureValid = $sidecarAuthenticodeValid
        }
        signing = [pscustomobject]@{
            sidecar = $sidecarSignature
            desktop = $desktopSignature
            installer = $installerSignature
        }
        updater = $updateArtifact
        boundaries = @(
            "Authenticode proves Windows publisher identity and file integrity.",
            "Tauri Minisign proves updater artifact integrity and binds the signed app version.",
            "Production signing credentials, an HTTPS update endpoint, and production update keys are supplied outside source control."
        )
    }

    $manifestPath = Join-Path $releaseRoot "release-manifest.json"
    Write-Utf8File `
        -LiteralPath $manifestPath `
        -Content ($manifest | ConvertTo-Json -Depth 12)
    $writtenManifest = Get-Content -LiteralPath $manifestPath -Raw |
        ConvertFrom-Json
    Assert-ReleaseManifestIntegrity -Manifest $writtenManifest
    $manifest | ConvertTo-Json -Depth 12
}
finally {
    $env:TEMP = $previousTemp
    $env:TMP = $previousTmp
    [Environment]::SetEnvironmentVariable(
        "CARGO_PROFILE_RELEASE_DEBUG",
        $previousReleaseDebug,
        "Process"
    )
    [Environment]::SetEnvironmentVariable(
        "CARGO_PROFILE_DEV_DEBUG",
        $previousDevDebug,
        "Process"
    )
    Pop-Location
}
