param(
    [int] $Seconds = 180,
    [string] $Output = "outputs/agent-crossbar-human-demo.mp4",
    [string] $Camera = "Integrated Camera",
    [string] $Microphone = "麦克风阵列 (Realtek(R) Audio)",
    [int] $CameraWidth = 480,
    [int] $FrameRate = 30,
    [switch] $NoCamera,
    [switch] $NoMicrophone,
    [switch] $ListDevices,
    [switch] $Validate,
    [switch] $SelfTest
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot

$ffmpegCommand = Get-Command ffmpeg -ErrorAction SilentlyContinue
if ($null -eq $ffmpegCommand) {
    throw "ffmpeg is not on PATH. Install it first (winget install Gyan.FFmpeg) and reopen the terminal."
}

function Get-DeviceList {
    Invoke-FfmpegText @("-hide_banner", "-list_devices", "true", "-f", "dshow", "-i", "dummy")
}

function Invoke-FfmpegText {
    param([string[]] $Arguments)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        ffmpeg @Arguments 2>&1 | ForEach-Object {
            if ($_ -is [System.Management.Automation.ErrorRecord]) {
                $_.Exception.Message
            } else {
                $_.ToString()
            }
        }
    } finally {
        $ErrorActionPreference = $previous
    }
}

if ($ListDevices) {
    Get-DeviceList | Select-Object -First 80
    exit 0
}

if ($Validate) {
    Write-Host "[validate] ffmpeg: $($ffmpegCommand.Source)"
    Invoke-FfmpegText @("-hide_banner", "-version") | Select-Object -First 1
    $devices = Get-DeviceList | Out-String
    if (-not $NoCamera) {
        if ($devices -notmatch [regex]::Escape($Camera)) {
            throw "Camera not found: $Camera. Run with -ListDevices to see the exact names."
        }
        Write-Host "[validate] camera: $Camera"
    }
    if (-not $NoMicrophone) {
        if ($devices -notmatch [regex]::Escape($Microphone)) {
            throw "Microphone not found: $Microphone. Run with -ListDevices to see the exact names."
        }
        Write-Host "[validate] microphone: $Microphone"
    }
    if (-not $NoCamera) {
        $overlay = Invoke-FfmpegText @("-hide_banner", "-filters") | Select-String -Pattern "overlay"
        if (-not $overlay) { throw "ffmpeg build is missing the overlay filter." }
    }
    $gdigrab = Invoke-FfmpegText @("-hide_banner", "-devices") | Select-String -Pattern "gdigrab"
    if (-not $gdigrab) { throw "This ffmpeg build has no gdigrab screen capture device." }
    Write-Host "[validate] gdigrab available."
    Write-Host "[validate] all inputs resolve; run without -Validate to record."
    exit 0
}

if ($SelfTest) {
    $selfTestPath = Join-Path $projectRoot "outputs\_record-selftest.mp4"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $selfTestPath) | Out-Null
    $selfTestFilter = "[1:v]scale=$($CameraWidth):-2[pip];[0:v][pip]overlay=W-w-40:H-h-40[v]"
    $selfTestArguments = @(
        "-y",
        "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=$FrameRate",
        "-f", "lavfi", "-i", "testsrc2=size=640x480:rate=$FrameRate",
        "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=48000",
        "-filter_complex", $selfTestFilter,
        "-map", "[v]", "-map", "2:a",
        "-t", "6",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-c:a", "aac", "-b:a", "160k",
        $selfTestPath
    )
    Write-Host "[selftest] synthesising a 6 second clip with the same filter graph..."
    Invoke-FfmpegText $selfTestArguments | Select-Object -Last 3 | ForEach-Object { Write-Host $_ }
    if (-not (Test-Path -LiteralPath $selfTestPath)) { throw "selftest did not write $selfTestPath" }
    $probe = Invoke-FfmpegText @("-hide_banner", "-i", $selfTestPath) | Select-String -Pattern "Duration|Stream #"
    $probe | ForEach-Object { Write-Host "[selftest] $_" }
    Write-Host "[selftest] wrote $selfTestPath"
    exit 0
}

$outputPath = Join-Path $projectRoot $Output
$outputDir = Split-Path -Parent $outputPath
New-Item -ItemType Directory -Force -Path $outputDir | Out-Null

$arguments = @(
    "-y",
    "-f", "gdigrab",
    "-framerate", "$FrameRate",
    "-i", "desktop"
)

$filter = $null
if (-not $NoCamera) {
    $arguments += @("-f", "dshow", "-i", "video=$Camera")
    $filter = "[1:v]scale=$($CameraWidth):-2[pip];[0:v][pip]overlay=W-w-40:H-h-40[v]"
}
if (-not $NoMicrophone) {
    $arguments += @("-f", "dshow", "-i", "audio=$Microphone")
}

$arguments += @("-t", "$Seconds", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22")
if ($filter) {
    $arguments += @("-filter_complex", $filter)
    $arguments += @("-map", "[v]")
} else {
    $arguments += @("-map", "0:v")
}
if (-not $NoMicrophone) {
    $audioInput = if ($NoCamera) { "1:a" } else { "2:a" }
    $arguments += @("-map", $audioInput, "-c:a", "aac", "-b:a", "160k")
}
$arguments += @($outputPath)

Write-Host "[record] output: $outputPath"
Write-Host "[record] duration: $Seconds seconds"
Write-Host "[record] close private windows before recording."
Write-Host "[record] starting in 5 seconds..."
Start-Sleep -Seconds 5

& ffmpeg @arguments
if ($LASTEXITCODE -ne 0) {
    throw "ffmpeg failed with exit code $LASTEXITCODE"
}
Write-Host "[record] wrote $outputPath"

