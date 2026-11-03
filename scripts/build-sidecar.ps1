$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$rustcCommand = Get-Command rustc -ErrorAction SilentlyContinue
$rustc = if ($rustcCommand) {
    $rustcCommand.Source
} else {
    Join-Path $env:USERPROFILE ".cargo\bin\rustc.exe"
}
if (-not (Test-Path -LiteralPath $rustc)) {
    throw "rustc is missing. Install the Rust toolchain before building the sidecar."
}
$targetTriple = (& $rustc --print host-tuple).Trim()
if ($LASTEXITCODE -ne 0) {
    throw "rustc failed while resolving the host target."
}
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment is missing. Run 'uv sync' from $projectRoot first."
}

$buildRoot = Join-Path $projectRoot ".build\pyinstaller"
$distRoot = Join-Path $projectRoot ".build\sidecar-dist"
$binaryRoot = Join-Path $projectRoot "src-tauri\binaries"
$sourceBinary = Join-Path $distRoot "agent-crossbar-sidecar.exe"
$targetBinary = Join-Path $binaryRoot "agent-crossbar-sidecar-$targetTriple.exe"

Push-Location $projectRoot
try {
    Write-Host "[sidecar] Building standalone Python service for $targetTriple"
    & $python -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --console `
        --name agent-crossbar-sidecar `
        --paths backend `
        --collect-submodules uvicorn `
        --distpath $distRoot `
        --workpath $buildRoot `
        --specpath $buildRoot `
        backend\agent_crossbar\sidecar.py
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed with exit code $LASTEXITCODE."
    }

    New-Item -ItemType Directory -Force -Path $binaryRoot | Out-Null
    Copy-Item -LiteralPath $sourceBinary -Destination $targetBinary -Force
    Write-Host "[sidecar] Ready: $targetBinary"
}
finally {
    Pop-Location
}
