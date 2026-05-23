$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$src = Join-Path $root 'vendor\forza-painter-geometrize-gpu-patched'
$buildScript = Join-Path $src 'build-opencl.ps1'
$outputExe = Join-Path $src 'forza-painter-geometrize-go.exe'
$targetExe = Join-Path $root 'forza-painter-geometrize-go.exe'

if (!(Test-Path $buildScript)) {
    throw "Missing build script: $buildScript"
}

Push-Location $src
try {
    & powershell -ExecutionPolicy Bypass -File $buildScript
}
finally {
    Pop-Location
}

if (!(Test-Path $outputExe)) {
    throw "Expected build output not found: $outputExe"
}

if (Test-Path $targetExe) {
    $timestamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backupExe = Join-Path $root "forza-painter-geometrize-go.exe.bak-$timestamp"
    Copy-Item $targetExe $backupExe -Force
    Write-Host "Backed up existing generator to: $backupExe"
}

Copy-Item $outputExe $targetExe -Force
Write-Host "Updated bundled generator: $targetExe"

