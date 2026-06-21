param(
    [string]$Configuration = "Release"
)

$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path

function Test-KfpsAppRoot([string]$Path) {
    return (Test-Path (Join-Path $Path "VERSION")) -and (Test-Path (Join-Path $Path "KloudysGalateaGenesis.exe"))
}

function Find-KfpsAppRoot([string]$StartPath) {
    $current = Get-Item -LiteralPath $StartPath
    while ($null -ne $current) {
        if (Test-KfpsAppRoot $current.FullName) {
            return $current.FullName
        }

        $nested = Join-Path $current.FullName "KloudysFH6Painter"
        if (Test-KfpsAppRoot $nested) {
            return $nested
        }

        $current = $current.Parent
    }

    throw "Could not find KFPS app root from $StartPath"
}

$AppRoot = Find-KfpsAppRoot $ProjectDir
$StandaloneRoot = Split-Path -Parent $AppRoot
$OutDir = Join-Path $StandaloneRoot "KFPS Native Launcher"

if (Test-Path $OutDir) {
    Remove-Item $OutDir -Recurse -Force
}

dotnet publish (Join-Path $ProjectDir "KFPS.Wpf.csproj") `
    -c $Configuration `
    -r win-x64 `
    --self-contained false `
    -o $OutDir

if ($LASTEXITCODE -ne 0) {
    throw "dotnet publish failed with exit code $LASTEXITCODE"
}

Write-Host "Published WPF launcher to:"
Write-Host $OutDir
Write-Host ""
Write-Host "Run:"
Write-Host (Join-Path $OutDir "KFPS.exe")

$SingleFileDir = Join-Path $StandaloneRoot "KFPS Native Launcher SingleFile"
if (Test-Path $SingleFileDir) {
    Remove-Item $SingleFileDir -Recurse -Force
}

dotnet publish (Join-Path $ProjectDir "KFPS.Wpf.csproj") `
    -c $Configuration `
    -r win-x64 `
    --self-contained false `
    -p:PublishSingleFile=true `
    -p:IncludeNativeLibrariesForSelfExtract=true `
    -o $SingleFileDir

if ($LASTEXITCODE -ne 0) {
    throw "single-file dotnet publish failed with exit code $LASTEXITCODE"
}

$RootExe = Join-Path $StandaloneRoot "KFPS Native Launcher.exe"
Copy-Item -LiteralPath (Join-Path $SingleFileDir "KFPS.exe") -Destination $RootExe -Force
Write-Host ""
Write-Host "Convenience launcher copied to:"
Write-Host $RootExe

$SelfContainedDir = Join-Path $StandaloneRoot "KFPS Native Launcher SelfContained"
if (Test-Path $SelfContainedDir) {
    Remove-Item $SelfContainedDir -Recurse -Force
}

dotnet publish (Join-Path $ProjectDir "KFPS.Wpf.csproj") `
    -c $Configuration `
    -r win-x64 `
    --self-contained true `
    -p:PublishSingleFile=true `
    -p:IncludeNativeLibrariesForSelfExtract=true `
    -p:EnableCompressionInSingleFile=true `
    -o $SelfContainedDir

if ($LASTEXITCODE -ne 0) {
    throw "self-contained dotnet publish failed with exit code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Self-contained launcher copied to:"
Write-Host (Join-Path $SelfContainedDir "KFPS.exe")
