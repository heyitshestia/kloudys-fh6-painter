param(
    [Parameter(Mandatory = $true)][string]$Source,
    [Parameter(Mandatory = $true)][string]$Target,
    [string]$OldTarget = "",
    [string]$LogFile = "",
    [int]$Attempts = 300,
    [switch]$DeleteSelf
)

$ErrorActionPreference = "Continue"

function Write-KfpsLog {
    param([string]$Message)
    $line = "[launcher handoff] $Message"
    Write-Host $line
    if ($LogFile) {
        try {
            Add-Content -LiteralPath $LogFile -Value $line -Encoding UTF8
        } catch {
        }
    }
}

function Remove-SelfIfRequested {
    if (!$DeleteSelf -or !$PSCommandPath) {
        return
    }
    try {
        $quoted = $PSCommandPath.Replace('"', '""')
        Start-Process -WindowStyle Hidden -FilePath cmd.exe -ArgumentList "/c ping 127.0.0.1 -n 3 >nul & del /f /q ""$quoted"" >nul 2>nul"
    } catch {
    }
}

for ($i = 1; $i -le $Attempts; $i++) {
    try {
        if (!(Test-Path -LiteralPath $Source)) {
            Write-KfpsLog "Source launcher no longer exists: $Source"
            exit 1
        }
        Copy-Item -LiteralPath $Source -Destination $Target -Force
        if (Test-Path -LiteralPath $Target) {
            Remove-Item -LiteralPath $Source -Force -ErrorAction SilentlyContinue
            if ($OldTarget -and (Test-Path -LiteralPath $OldTarget)) {
                Remove-Item -LiteralPath $OldTarget -Force -ErrorAction SilentlyContinue
            }
            Write-KfpsLog "Parent launcher replaced: $Target"
            Remove-SelfIfRequested
            exit 0
        }
    } catch {
        if ($i -eq 1 -or ($i % 30) -eq 0) {
            Write-KfpsLog "Waiting for launcher to close before replacement. Attempt $i/$Attempts."
        }
    }
    Start-Sleep -Seconds 1
}

Write-KfpsLog "Timed out waiting to replace parent launcher. Manual copy may be needed."
Remove-SelfIfRequested
exit 1
