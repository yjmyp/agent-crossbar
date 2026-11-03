$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$nsisTemp = Join-Path $projectRoot ".build\nsis-temp"
$bundleRoot = Join-Path $projectRoot "src-tauri\target\release\bundle\nsis"

Push-Location $projectRoot
try {
    New-Item -ItemType Directory -Force -Path $nsisTemp | Out-Null

    $previousTemp = $env:TEMP
    $previousTmp = $env:TMP
    $env:TEMP = $nsisTemp
    $env:TMP = $nsisTemp

    try {
        $env:PATH = "$env:USERPROFILE\.cargo\bin;$env:PATH"
        & powershell -NoProfile -ExecutionPolicy Bypass -File scripts\build-sidecar.ps1
        if ($LASTEXITCODE -ne 0) {
            throw "Sidecar build failed with exit code $LASTEXITCODE."
        }

        & npm.cmd run tauri -- build --bundles nsis
        if ($LASTEXITCODE -ne 0) {
            throw "Desktop installer build failed with exit code $LASTEXITCODE."
        }
    }
    finally {
        $env:TEMP = $previousTemp
        $env:TMP = $previousTmp
    }

    $installer = Get-ChildItem -LiteralPath $bundleRoot -Filter "*-setup.exe" -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if ($null -eq $installer) {
        throw "The NSIS build completed without producing an installer."
    }

    $signature = Get-AuthenticodeSignature -LiteralPath $installer.FullName
    [pscustomobject]@{
        status = "passed"
        installer = $installer.FullName
        sizeBytes = $installer.Length
        lastWriteTime = $installer.LastWriteTime
        signatureStatus = $signature.Status
        sha256 = (Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256).Hash
    } | ConvertTo-Json -Depth 3
}
finally {
    Pop-Location
}
