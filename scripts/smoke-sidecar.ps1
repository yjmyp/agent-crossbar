$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$smokeRoot = Join-Path $projectRoot ".build\sidecar-smoke"
$stdoutPath = Join-Path $smokeRoot "stdout.log"
$stderrPath = Join-Path $smokeRoot "stderr.log"
$databasePath = Join-Path $smokeRoot "smoke.db"
$runtimeTemp = Join-Path $smokeRoot "runtime-temp"
$binaryPath = Join-Path $projectRoot "src-tauri\binaries\agent-crossbar-sidecar-x86_64-pc-windows-msvc.exe"

if (-not (Test-Path -LiteralPath $binaryPath)) {
    throw "Packaged sidecar is missing. Run npm run sidecar:build first."
}

New-Item -ItemType Directory -Force -Path $smokeRoot, $runtimeTemp | Out-Null
Remove-Item -LiteralPath $stdoutPath, $stderrPath, $databasePath -Force -ErrorAction SilentlyContinue
Remove-Item `
    -LiteralPath "$databasePath-wal", "$databasePath-shm" `
    -Force `
    -ErrorAction SilentlyContinue

$tokenBytes = New-Object byte[] 32
$random = [Security.Cryptography.RandomNumberGenerator]::Create()
$random.GetBytes($tokenBytes)
$random.Dispose()
$token = ([BitConverter]::ToString($tokenBytes) -replace "-", "").ToLowerInvariant()

$previousTemp = $env:TEMP
$previousTmp = $env:TMP
$env:TEMP = $runtimeTemp
$env:TMP = $runtimeTemp

$process = Start-Process `
    -FilePath $binaryPath `
    -ArgumentList @(
        "--database",
        $databasePath,
        "--token",
        $token,
        "--port",
        "0",
        "--parent-pid",
        "$PID"
    ) `
    -RedirectStandardOutput $stdoutPath `
    -RedirectStandardError $stderrPath `
    -WindowStyle Hidden `
    -PassThru

try {
    $deadline = (Get-Date).AddSeconds(30)
    $handshake = $null
    while ((Get-Date) -lt $deadline -and -not $handshake) {
        Start-Sleep -Milliseconds 250
        if ($process.HasExited) {
            $stderr = Get-Content -LiteralPath $stderrPath -Raw -ErrorAction SilentlyContinue
            throw "Sidecar exited with code $($process.ExitCode): $stderr"
        }
        if (Test-Path -LiteralPath $stdoutPath) {
            $line = Get-Content -LiteralPath $stdoutPath -ErrorAction SilentlyContinue |
                Select-Object -First 1
            if ($line) {
                $handshake = $line | ConvertFrom-Json
            }
        }
    }
    if (-not $handshake) {
        throw "Sidecar did not publish a ready handshake within 30 seconds."
    }

    $baseUrl = "http://127.0.0.1:$($handshake.port)"
    $headers = @{ Authorization = "Bearer $token" }

    $health = Invoke-RestMethod -Uri "$baseUrl/health" -Headers $headers
    $specBody = @{
        name = "Smoke Agent"
        version = "1.0.0"
        description = "Packaged sidecar smoke test"
        instructions = "Answer accurately."
    } | ConvertTo-Json
    $spec = Invoke-RestMethod `
        -Uri "$baseUrl/v1/specs" `
        -Method Post `
        -Headers $headers `
        -ContentType "application/json" `
        -Body $specBody

    $runBody = @{
        spec_id = $spec.agent_id
        version = $spec.spec.version
        input = "hello world"
    } | ConvertTo-Json
    $run = Invoke-RestMethod `
        -Uri "$baseUrl/v1/runs" `
        -Method Post `
        -Headers $headers `
        -ContentType "application/json" `
        -Body $runBody

    Start-Sleep -Seconds 1
    $finalRun = Invoke-RestMethod -Uri "$baseUrl/v1/runs/$($run.run_id)" -Headers $headers
    $eventText = & curl.exe `
        --silent `
        --show-error `
        --fail `
        --max-time 10 `
        -H "Authorization: Bearer $token" `
        "$baseUrl/v1/runs/$($run.run_id)/events"
    if ($LASTEXITCODE -ne 0) {
        throw "Could not read the packaged sidecar event stream."
    }
    $eventText = $eventText -join "`n"

    if ($health.status -ne "ok") {
        throw "Health check did not report ok."
    }
    if ($finalRun.status -ne "completed" -or $finalRun.output -ne "Echo: hello world") {
        throw "Packaged runtime did not complete with the expected deterministic output."
    }
    if (-not $eventText.Contains("run_started") -or
        -not $eventText.Contains("run_completed")) {
        throw "Packaged event stream did not contain start and completion events."
    }
    if (-not (Test-Path -LiteralPath $databasePath)) {
        throw "Packaged sidecar did not create the SQLite database."
    }

    [pscustomobject]@{
        status = "passed"
        health = $health.status
        specDigest = $spec.digest
        runStatus = $finalRun.status
        runOutput = $finalRun.output
        databaseCreated = $true
    } | ConvertTo-Json -Depth 4
}
finally {
    $env:TEMP = $previousTemp
    $env:TMP = $previousTmp
    if ($null -ne $process -and -not $process.HasExited) {
        Stop-Process -Id $process.Id -Force
    }
    Start-Sleep -Seconds 2
}
