param(
    [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)]
    [string[]] $Files,

    [switch] $Json,

    [switch] $AllowUnsigned
)

$ErrorActionPreference = "Stop"

$reports = foreach ($file in $Files) {
    $resolved = Resolve-Path -LiteralPath $file -ErrorAction Stop
    if (-not (Test-Path -LiteralPath $resolved.Path -PathType Leaf)) {
        throw "Not a file: $($resolved.Path)"
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $resolved.Path
    $certificate = $signature.SignerCertificate
    [pscustomobject]@{
        path = $resolved.Path
        status = $signature.Status.ToString()
        valid = $signature.Status -eq [System.Management.Automation.SignatureStatus]::Valid
        subject = if ($null -eq $certificate) { $null } else { $certificate.Subject }
        thumbprint = if ($null -eq $certificate) { $null } else { $certificate.Thumbprint }
        timestamp = if ($null -eq $signature.TimeStamperCertificate) { $null } else { $signature.TimeStamperCertificate.Subject }
    }
}

if ($Json) {
    $reports | ConvertTo-Json -Depth 4
} else {
    $reports | Format-Table -AutoSize | Out-String | Write-Host
}

$failures = @($reports | Where-Object {
    $_.valid -or ($AllowUnsigned -and $_.status -eq "NotSigned")
})
if ($failures.Count -ne $reports.Count) {
    Write-Host "[authenticode] one or more files are not validly signed." -ForegroundColor Red
    exit 1
}

Write-Host "[authenticode] all $($reports.Count) file(s) passed."
exit 0