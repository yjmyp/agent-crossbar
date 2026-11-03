$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$sidecar = Join-Path $projectRoot `
    "src-tauri\binaries\agent-crossbar-sidecar-x86_64-pc-windows-msvc.exe"
$mockServer = Join-Path $PSScriptRoot "mock-openai-server.py"
$smokeRoot = Join-Path $projectRoot ".build\provider-smoke"
$providerStdout = Join-Path $smokeRoot "provider-stdout.log"
$providerStderr = Join-Path $smokeRoot "provider-stderr.log"
$sidecarStdout = Join-Path $smokeRoot "sidecar-stdout.log"
$sidecarStderr = Join-Path $smokeRoot "sidecar-stderr.log"
$database = Join-Path $smokeRoot "provider-smoke.db"
$runtimeTemp = Join-Path $smokeRoot "runtime-temp"
$syntheticKey = "crossbar-e2e-synthetic-not-real-20261103"

function Get-Sha256 {
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

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment is missing. Run uv sync first."
}
if (-not (Test-Path -LiteralPath $sidecar)) {
    throw "Packaged sidecar is missing. Run npm run sidecar:build first."
}

New-Item -ItemType Directory -Force -Path $smokeRoot, $runtimeTemp | Out-Null
Remove-Item `
    -LiteralPath $providerStdout, $providerStderr, $sidecarStdout, $sidecarStderr, $database `
    -Force `
    -ErrorAction SilentlyContinue
Remove-Item `
    -LiteralPath "$database-wal", "$database-shm" `
    -Force `
    -ErrorAction SilentlyContinue

$previousProviderKey = [Environment]::GetEnvironmentVariable(
    "AGENT_CROSSBAR_TEST_PROVIDER_KEY",
    "Process"
)
$previousBaseUrl = [Environment]::GetEnvironmentVariable(
    "AGENT_CROSSBAR_OPENAI_BASE_URL",
    "Process"
)
$previousApiKey = [Environment]::GetEnvironmentVariable(
    "AGENT_CROSSBAR_OPENAI_API_KEY",
    "Process"
)
$previousModel = [Environment]::GetEnvironmentVariable(
    "AGENT_CROSSBAR_OPENAI_MODEL",
    "Process"
)
$previousTemp = $env:TEMP
$previousTmp = $env:TMP

$providerProcess = $null
$sidecarProcess = $null
try {
    $env:AGENT_CROSSBAR_TEST_PROVIDER_KEY = $syntheticKey
    $providerProcess = Start-Process `
        -FilePath $python `
        -ArgumentList @($mockServer) `
        -RedirectStandardOutput $providerStdout `
        -RedirectStandardError $providerStderr `
        -WindowStyle Hidden `
        -PassThru

    $providerDeadline = (Get-Date).AddSeconds(15)
    $providerHandshake = $null
    while ((Get-Date) -lt $providerDeadline -and -not $providerHandshake) {
        Start-Sleep -Milliseconds 100
        if ($providerProcess.HasExited) {
            throw "Mock provider exited before becoming ready."
        }
        if (Test-Path -LiteralPath $providerStdout) {
            $line = Get-Content -LiteralPath $providerStdout -ErrorAction SilentlyContinue |
                Select-Object -First 1
            if ($line) {
                $providerHandshake = $line | ConvertFrom-Json
            }
        }
    }
    if (-not $providerHandshake) {
        throw "Mock provider did not become ready within 15 seconds."
    }

    $tokenBytes = New-Object byte[] 32
    $random = [Security.Cryptography.RandomNumberGenerator]::Create()
    $random.GetBytes($tokenBytes)
    $random.Dispose()
    $launchToken = ([BitConverter]::ToString($tokenBytes) -replace "-", "").ToLowerInvariant()

    $env:AGENT_CROSSBAR_OPENAI_BASE_URL =
        "http://127.0.0.1:$($providerHandshake.port)/v1"
    $env:AGENT_CROSSBAR_OPENAI_API_KEY = $syntheticKey
    $env:AGENT_CROSSBAR_OPENAI_MODEL = "smoke-model"
    $env:TEMP = $runtimeTemp
    $env:TMP = $runtimeTemp

    $sidecarProcess = Start-Process `
        -FilePath $sidecar `
        -ArgumentList @(
            "--database",
            $database,
            "--token",
            $launchToken,
            "--port",
            "0",
            "--parent-pid",
            "$PID"
        ) `
        -RedirectStandardOutput $sidecarStdout `
        -RedirectStandardError $sidecarStderr `
        -WindowStyle Hidden `
        -PassThru

    $sidecarDeadline = (Get-Date).AddSeconds(30)
    $sidecarHandshake = $null
    while ((Get-Date) -lt $sidecarDeadline -and -not $sidecarHandshake) {
        Start-Sleep -Milliseconds 250
        if ($sidecarProcess.HasExited) {
            $stderr = Get-Content -LiteralPath $sidecarStderr -Raw -ErrorAction SilentlyContinue
            throw "Packaged sidecar exited before becoming ready: $stderr"
        }
        if (Test-Path -LiteralPath $sidecarStdout) {
            $line = Get-Content -LiteralPath $sidecarStdout -ErrorAction SilentlyContinue |
                Select-Object -First 1
            if ($line) {
                $sidecarHandshake = $line | ConvertFrom-Json
            }
        }
    }
    if (-not $sidecarHandshake) {
        throw "Packaged sidecar did not become ready within 30 seconds."
    }

    $baseUrl = "http://127.0.0.1:$($sidecarHandshake.port)"
    $headers = @{ Authorization = "Bearer $launchToken" }
    $providers = Invoke-RestMethod `
        -Uri "$baseUrl/v1/providers" `
        -Headers $headers
    $openAIProvider = $providers |
        Where-Object { $_.id -eq "openai.default" } |
        Select-Object -First 1
    if (-not $openAIProvider -or -not $openAIProvider.configured) {
        throw "Packaged sidecar did not load the environment-provided provider."
    }
    if ($openAIProvider.model -ne "smoke-model") {
        throw "Packaged sidecar reported an unexpected provider model."
    }

    $connectionTest = Invoke-RestMethod `
        -Uri "$baseUrl/v1/providers/openai.default/test" `
        -Method Post `
        -Headers $headers
    if (-not $connectionTest.ok -or $connectionTest.message -ne "Connection succeeded.") {
        throw "The explicit provider connection test did not succeed."
    }

    $specBody = @{
        name = "Provider Smoke Agent"
        version = "1.0.0"
        description = "Packaged provider smoke test"
        instructions = "Reply with exactly OK."
        model_profile = "openai.default"
        tools = @()
    } | ConvertTo-Json -Depth 10
    $spec = Invoke-RestMethod `
        -Uri "$baseUrl/v1/specs" `
        -Method Post `
        -Headers $headers `
        -ContentType "application/json" `
        -Body $specBody

    $runBody = @{
        spec_id = $spec.agent_id
        version = $spec.spec.version
        input = "Return OK."
    } | ConvertTo-Json
    $run = Invoke-RestMethod `
        -Uri "$baseUrl/v1/runs" `
        -Method Post `
        -Headers $headers `
        -ContentType "application/json" `
        -Body $runBody

    $runDeadline = (Get-Date).AddSeconds(20)
    $finalRun = $null
    while ((Get-Date) -lt $runDeadline) {
        $candidateRun = Invoke-RestMethod `
            -Uri "$baseUrl/v1/runs/$($run.run_id)" `
            -Headers $headers
        if ($candidateRun.status -in @("completed", "failed", "cancelled", "interrupted")) {
            $finalRun = $candidateRun
            break
        }
        Start-Sleep -Milliseconds 200
    }
    if (-not $finalRun) {
        throw "Provider-backed run did not reach a terminal state within 20 seconds."
    }
    if ($finalRun.status -ne "completed" -or $finalRun.output -ne "OK") {
        throw "Provider-backed run did not complete with the expected model output."
    }

    $secretPaths = @(
        $database,
        $providerStdout,
        $providerStderr,
        $sidecarStdout,
        $sidecarStderr
    ) | Where-Object { Test-Path -LiteralPath $_ }
    foreach ($secretPath in $secretPaths) {
        $match = Select-String `
            -LiteralPath $secretPath `
            -SimpleMatch `
            -Pattern $syntheticKey `
            -Quiet
        if ($match) {
            throw "The synthetic provider key appeared in $secretPath."
        }
    }

    [pscustomobject]@{
        status = "passed"
        providerConfigured = $openAIProvider.configured
        providerModel = $openAIProvider.model
        connectionTest = $connectionTest.message
        runId = $finalRun.run_id
        runStatus = $finalRun.status
        runOutput = $finalRun.output
        syntheticKeyAbsentFromDatabaseAndLogs = $true
        packageSha256 = Get-Sha256 -LiteralPath $sidecar
    } | ConvertTo-Json -Depth 4
}
finally {
    $env:TEMP = $previousTemp
    $env:TMP = $previousTmp
    [Environment]::SetEnvironmentVariable(
        "AGENT_CROSSBAR_TEST_PROVIDER_KEY",
        $previousProviderKey,
        "Process"
    )
    [Environment]::SetEnvironmentVariable(
        "AGENT_CROSSBAR_OPENAI_BASE_URL",
        $previousBaseUrl,
        "Process"
    )
    [Environment]::SetEnvironmentVariable(
        "AGENT_CROSSBAR_OPENAI_API_KEY",
        $previousApiKey,
        "Process"
    )
    [Environment]::SetEnvironmentVariable(
        "AGENT_CROSSBAR_OPENAI_MODEL",
        $previousModel,
        "Process"
    )
    if ($null -ne $sidecarProcess -and -not $sidecarProcess.HasExited) {
        Stop-Process -Id $sidecarProcess.Id -Force
    }
    if ($null -ne $providerProcess -and -not $providerProcess.HasExited) {
        Stop-Process -Id $providerProcess.Id -Force
    }
    Start-Sleep -Seconds 2
}
