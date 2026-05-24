$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$DistRoot = Join-Path $Root "dist"
$PackageDir = Join-Path $DistRoot "kloudys-fh6-painter"
$ZipPath = Join-Path $DistRoot "kloudys-fh6-painter.zip"

$include = @(
    "README.md",
    "README.zh-CN.md",
    "docs/USER_MANUAL.md",
    "docs/examples",
    "requirements.txt",
    "requirements-preview.txt",
    "VERSION",
    "install_dependencies.bat",
    "update_from_github.bat",
    "check_environment.bat",
    "clean_runtime_data.bat",
    "LICENSE",
    "LICENSE.geometrize-gpu",
    ".gitignore",
    "1. drag_image_file_here.bat",
    "start_app.bat",
    "forza-painter-geometrize-go.exe",
    "forza_generator_v2.py",
    "app.py",
    "main.py",
    "generator_backend.py",
    "version_info.py",
    "fh6_probe.py",
    "game_profiles.py",
    "internal_classes.py",
    "native.py",
    "settings",
    "imgs"
)

if (Test-Path $PackageDir) {
    Remove-Item -LiteralPath $PackageDir -Recurse -Force
}
New-Item -ItemType Directory -Path $PackageDir | Out-Null

foreach ($item in $include) {
    $source = Join-Path $Root $item
    if (!(Test-Path $source)) {
        Write-Warning "Skipping missing item: $item"
        continue
    }
    $destination = Join-Path $PackageDir $item
    if ((Get-Item $source).PSIsContainer) {
        Copy-Item -LiteralPath $source -Destination $destination -Recurse
    } else {
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath $source -Destination $destination
    }
}

if (Test-Path $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -Path (Join-Path $PackageDir "*") -DestinationPath $ZipPath
Write-Host "Release package written to $ZipPath"
