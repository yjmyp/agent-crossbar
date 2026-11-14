$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$ruff = Join-Path $projectRoot ".venv\Scripts\ruff.exe"
$cargo = Join-Path $env:USERPROFILE ".cargo\bin\cargo.exe"

if (-not (Test-Path -LiteralPath $python)) {
    throw "[verify] Python environment is missing. Run 'uv sync' from $projectRoot first."
}
if (-not (Test-Path -LiteralPath $ruff)) {
    throw "[verify] Ruff is missing. Run 'uv sync' from $projectRoot first."
}
if (-not (Test-Path -LiteralPath $cargo)) {
    throw "[verify] Cargo is missing from $cargo."
}

function Assert-StagePassed {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Stage
    )

    if ($LASTEXITCODE -ne 0) {
        throw "[verify] $Stage failed with exit code $LASTEXITCODE."
    }
}

function Invoke-Stage {
    param(
        [Parameter(Mandatory = $true)]
        [string] $Name,
        [Parameter(Mandatory = $true)]
        [scriptblock] $Action
    )

    Write-Host "[verify] $Name"
    & $Action
    Assert-StagePassed -Stage $Name
}

Push-Location $projectRoot
try {
    Invoke-Stage "TypeScript typecheck" {
        & npm.cmd run typecheck
    }
    Invoke-Stage "Frontend lint" {
        & npm.cmd run lint
    }
    Invoke-Stage "Frontend tests" {
        & npm.cmd run test:run
    }
    Invoke-Stage "Frontend production build" {
        & npm.cmd run build
    }
    Invoke-Stage "Python lint" {
        & $ruff check backend
    }
    Invoke-Stage "Python tests" {
        & $python -m pytest backend -q
    }
    Invoke-Stage "Security gate" {
        & $python -m agent_crossbar.security.cli --root backend/agent_crossbar --format sarif -o work\security.sarif
    }
    Invoke-Stage "Rust formatting" {
        & $cargo fmt --manifest-path src-tauri\Cargo.toml -- --check
    }
    Invoke-Stage "Rust tests" {
        & $cargo test --manifest-path src-tauri\Cargo.toml
    }
    Invoke-Stage "Rust check" {
        & $cargo check --manifest-path src-tauri\Cargo.toml
    }

    Write-Host "[verify] All quality gates passed."
}
finally {
    Pop-Location
}
