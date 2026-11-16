<#
.SYNOPSIS
  One-command trial run for an external tester. Produces a report that can be
  attached to docs/verification/user-trials.md without hand editing.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts/trial.ps1 -WheelPath .\dist\agent_crossbar-0.1.0-py3-none-any.whl
#>
param(
    [string] $WheelPath,
    [string] $ReportPath,
    [string] $PipIndexUrl
)

$ErrorActionPreference = "Stop"
$started = Get-Date
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$trialRoot = Join-Path $env:TEMP "crossbar-trial-$stamp"
$venv = Join-Path $trialRoot ".venv"
$python = Join-Path $venv "Scripts\python.exe"
$cli = Join-Path $venv "Scripts\crossbar-security.exe"
$sample = Join-Path $trialRoot "sample"
$log = New-Object System.Collections.Generic.List[string]
$failures = New-Object System.Collections.Generic.List[string]

function Write-Step {
    param([string] $Message)
    Write-Host "[trial] $Message"
    $log.Add("## $Message") | Out-Null
}

function Invoke-Logged {
    param(
        [string] $Name,
        [scriptblock] $Action
    )
    $startedAt = Get-Date
    try {
        $output = & $Action 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) {
                $_.Exception.Message
            } else {
                $_.ToString()
            }
        } | Out-String
        $elapsed = [int]((Get-Date) - $startedAt).TotalMilliseconds
        $log.Add("- OK   $Name ($elapsed ms)") | Out-Null
        if ($output.Trim()) { $log.Add("``````text`n$($output.Trim())`n``````") | Out-Null }
        return $true
    } catch {
        $elapsed = [int]((Get-Date) - $startedAt).TotalMilliseconds
        $failures.Add($Name) | Out-Null
        $log.Add("- FAIL $Name ($elapsed ms): $($_.Exception.Message)") | Out-Null
        $log.Add("``````text`n$($_ | Out-String)`n``````") | Out-Null
        return $false
    }
}

Write-Step "environment"
$os = Get-CimInstance Win32_OperatingSystem
$log.Add("- OS: $($os.Caption) $($os.Version)") | Out-Null
$log.Add("- PowerShell: $($PSVersionTable.PSVersion)") | Out-Null
$log.Add("- Python on PATH: $(try { (Get-Command python -ErrorAction Stop).Source } catch { 'not found' })") | Out-Null
$log.Add("- Working copy: $trialRoot") | Out-Null

if (-not $WheelPath) {
    $searchRoots = @(
        (Join-Path $PSScriptRoot "..\build\wheels"),
        (Join-Path $PSScriptRoot "..\dist"),
        (Join-Path $PSScriptRoot "..")
    )
    $candidates = @(@(
        foreach ($root in $searchRoots) {
            if (Test-Path -LiteralPath $root) {
                Get-ChildItem -Path $root -Filter "*.whl" -File -ErrorAction SilentlyContinue
            }
        }
    ) | Sort-Object LastWriteTime -Descending)
    if ($candidates.Count -ge 1) {
        $WheelPath = $candidates[0].FullName
    } else {
        throw "Pass -WheelPath pointing at a built .whl file (try: uv run --with build python -m build --wheel -o build/wheels)."
    }
}
$WheelPath = (Resolve-Path -LiteralPath $WheelPath).Path

New-Item -ItemType Directory -Force -Path $trialRoot, $sample | Out-Null

Write-Step "install into a fresh virtual environment"
Invoke-Logged "python -m venv" {
    python -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "venv creation failed with exit code $LASTEXITCODE" }
} | Out-Null
Invoke-Logged "pip install wheel" {
    & $python -m pip install --upgrade pip --quiet --timeout 60 --retries 5
    $pipArgs = @("-m", "pip", "install", "--timeout", "60", "--retries", "5")
    if ($PipIndexUrl) { $pipArgs += @("--index-url", $PipIndexUrl) }
    $pipArgs += $WheelPath
    & $python @pipArgs
    if ($LASTEXITCODE -ne 0) { throw "pip install failed with exit code $LASTEXITCODE" }
} | Out-Null
Invoke-Logged "crossbar-security --help" {
    & $cli --help
    if ($LASTEXITCODE -ne 0) { throw "CLI --help failed with exit code $LASTEXITCODE" }
} | Out-Null

Write-Step "run the gate against a deliberately unsafe sample"
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "trial-sample\deploy.py") -Destination (Join-Path $sample "deploy.py")

$gateExit = $null
Invoke-Logged "crossbar-security on unsafe sample (expected exit 1)" {
    & $cli --root $sample --format sarif -o (Join-Path $trialRoot "security.sarif")
    $script:gateExit = $LASTEXITCODE
    if ($script:gateExit -eq 0) { throw "gate did not block the unsafe sample" }
    if (-not (Test-Path (Join-Path $trialRoot "security.sarif"))) { throw "SARIF output was not written" }
    if ($script:gateExit -ne 1) { throw "unexpected exit code: $($script:gateExit)" }
} | Out-Null

Write-Step "run the 10 minute demo"
Invoke-Logged "demo" {
    & $python (Join-Path $PSScriptRoot "demo.py")
    if ($LASTEXITCODE -ne 0) { throw "demo failed with exit code $LASTEXITCODE" }
} | Out-Null

$finished = Get-Date
$duration = [int]($finished - $started).TotalSeconds
$verdict = if ($failures.Count -eq 0) { "PASS" } else { "FAIL" }

$report = @"
# Trial report ($stamp)

- Verdict: **$verdict**
- Total time: $duration seconds
- Tester: (fill in your name or handle)
- Machine: (fill in CPU / RAM / Windows edition)

$($log -join "`n")

## Questions for the tester

1. Which step was the first one you did not understand without help?
2. Paste any error message verbatim (do not paraphrase).
3. Did you need administrator rights at any point?
4. Would you install this on a work repository? Why or why not?
"@

if (-not $ReportPath) {
    $ReportPath = Join-Path $trialRoot "report.md"
}
$report | Set-Content -Encoding utf8 $ReportPath

Write-Host ""
Write-Host "[trial] $verdict in $duration s"
Write-Host "[trial] report: $ReportPath"
Write-Host "[trial] artifacts kept at $trialRoot"
if ($failures.Count -gt 0) {
    Write-Host "[trial] failed steps: $($failures -join ', ')" -ForegroundColor Red
    exit 1
}
exit 0
