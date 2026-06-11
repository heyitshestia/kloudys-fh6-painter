$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VersionFile = Join-Path $Root "VERSION"
$Version = "dev"
if (Test-Path -LiteralPath $VersionFile) {
    $Version = (Get-Content -LiteralPath $VersionFile -Raw).Trim()
}
$SafeVersion = ($Version -replace '[^A-Za-z0-9._-]', '-')

$DistRoot = Join-Path $Root "dist"
$Stage = Join-Path $DistRoot "release-$SafeVersion"
$AppDir = Join-Path $Stage "KloudysFH6Painter"
$ZipPath = Join-Path $DistRoot "Kloudys-FH6-Painter-$SafeVersion.zip"

$ProjectItems = @(
    ".gitattributes",
    ".gitignore",
    "00_launcher.bat",
    "01_add_python312_to_path.bat",
    "02_install_dependencies.bat",
    "03_update_from_github.bat",
    "update_from_github.bat",
    "04_start_app.bat",
    "05_check_environment.bat",
    "99_clean_runtime_data.bat",
    "README.md",
    "README.zh-CN.md",
    "CHANGELOG.md",
    "VERSION",
    "LICENSE",
    "LICENSE.custom-importer",
    "LICENSE.geometrize-gpu",
    "requirements.txt",
    "requirements-preview.txt",
    "app.py",
    "app_qt.py",
    "launcher_qt.py",
    "generator_backend.py",
    "forza_generator_v2.py",
    "KloudysGalateaGenesis.exe",
    "geometry_json.py",
    "game_profiles.py",
    "internal_classes.py",
    "main.py",
    "fh6_probe.py",
    "fh6_group1000_probe.py",
    "fh6_export_typecode_json.py",
    "fh6_import_typecode_json.py",
    "fh6_trim_group_count.py",
    "fh6_shape_experiment.py",
    "fh6_shape_experiment_remote.py",
    "native.py",
    "version_info.py",
    "make_release.ps1",
    "make_release.py",
    "docs",
    "assets",
    "data",
    "settings",
    "tools"
)

$OptionalItems = @(
    "python"
)

function Copy-ProjectItem {
    param(
        [Parameter(Mandatory=$true)][string]$RelativePath
    )
    $Source = Join-Path $Root $RelativePath
    if (!(Test-Path -LiteralPath $Source)) {
        Write-Warning "Skipping missing item: $RelativePath"
        return
    }
    $Destination = Join-Path $AppDir $RelativePath
    $Parent = Split-Path -Parent $Destination
    if ($Parent -and !(Test-Path -LiteralPath $Parent)) {
        New-Item -ItemType Directory -Path $Parent -Force | Out-Null
    }
    Copy-Item -LiteralPath $Source -Destination $Destination -Recurse -Force
    if ((Test-Path -LiteralPath $Destination -PathType Leaf) -and ($Destination -match '\.(bat|cmd|ps1|ini)$')) {
        $Text = [System.IO.File]::ReadAllText($Destination)
        $Text = (($Text -replace "`r`n", "`n") -replace "`r", "`n") -replace "`n", "`r`n"
        [System.IO.File]::WriteAllText($Destination, $Text, [System.Text.UTF8Encoding]::new($false))
    }
}

if (Test-Path -LiteralPath $Stage) {
    Remove-Item -LiteralPath $Stage -Recurse -Force
}
New-Item -ItemType Directory -Path $AppDir -Force | Out-Null

$Launcher = Join-Path $Root "Kloudys Painter Launcher.exe"
if (!(Test-Path -LiteralPath $Launcher)) {
    throw "Missing launcher executable: $Launcher"
}
$LauncherBytes = [System.IO.File]::ReadAllBytes($Launcher)
$LauncherText = [System.Text.Encoding]::ASCII.GetString($LauncherBytes)
foreach ($Marker in @("PyInstaller", "_MEIPASS", "Failed to remove temporary directory", "pyi-runtime-tmpdir")) {
    if ($LauncherText.Contains($Marker)) {
        throw "Release verification failed: launcher is still a PyInstaller one-file executable ($Marker). Rebuild tools/native-launcher before packaging."
    }
}
Copy-Item -LiteralPath $Launcher -Destination (Join-Path $Stage "Kloudys Painter Launcher.exe") -Force

foreach ($Item in $ProjectItems) {
    Copy-ProjectItem -RelativePath $Item
}
foreach ($Item in $OptionalItems) {
    if (Test-Path -LiteralPath (Join-Path $Root $Item)) {
        Copy-ProjectItem -RelativePath $Item
    }
}

$BlockedPatterns = @(
    "\\.git\\",
    "\\runtime\\",
    "\\imgs\\generated\\",
    "\\webui-data\\",
    "\\docs\\development\\",
    "\\__pycache__\\",
    "\\dist\\"
)

$Leaked = Get-ChildItem -LiteralPath $Stage -Recurse -Force | Where-Object {
    $Full = $_.FullName
    foreach ($Pattern in $BlockedPatterns) {
        if ($Full -match $Pattern) { return $true }
    }
    return $false
}
if ($Leaked) {
    $Leaked | Select-Object -First 20 | ForEach-Object { Write-Host "Blocked release file: $($_.FullName)" }
    throw "Release verification failed: blocked generated/runtime files were staged."
}

if (Test-Path -LiteralPath $ZipPath) {
    Remove-Item -LiteralPath $ZipPath -Force
}
Compress-Archive -Path (Join-Path $Stage "*") -DestinationPath $ZipPath -Force

Add-Type -AssemblyName System.IO.Compression.FileSystem
$Zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
try {
    $Names = $Zip.Entries | ForEach-Object { $_.FullName }
    $Required = @(
        "Kloudys Painter Launcher.exe",
        "KloudysFH6Painter/00_launcher.bat",
        "KloudysFH6Painter/03_update_from_github.bat",
        "KloudysFH6Painter/app_qt.py",
        "KloudysFH6Painter/forza_generator_v2.py",
        "KloudysFH6Painter/KloudysGalateaGenesis.exe",
        "KloudysFH6Painter/fh6_export_typecode_json.py",
        "KloudysFH6Painter/fh6_import_typecode_json.py",
        "KloudysFH6Painter/fh6_trim_group_count.py",
        "KloudysFH6Painter/settings/a.flat-colors.ini",
        "KloudysFH6Painter/tools/fabric-editor/index.html",
        "KloudysFH6Painter/tools/fabric-editor/editor.js",
        "KloudysFH6Painter/tools/fabric-editor/vendor/fabric.min.js"
    )
    foreach ($RequiredName in $Required) {
        if ($Names -notcontains $RequiredName) {
            throw "Release verification failed: missing $RequiredName"
        }
    }
    foreach ($Name in $Names) {
        if ($Name -match '(^|/)runtime/' -or $Name -match '(^|/)imgs/generated/' -or $Name -match '(^|/)webui-data/' -or $Name -match '(^|/)__pycache__/') {
            throw "Release verification failed: blocked path in zip: $Name"
        }
        if ($Name -match '(^|/)docs/development/') {
            throw "Release verification failed: development docs in zip: $Name"
        }
    }
    foreach ($UpdaterName in @("KloudysFH6Painter/03_update_from_github.bat", "KloudysFH6Painter/update_from_github.bat")) {
        $Entry = $Zip.GetEntry($UpdaterName)
        if (-not $Entry) {
            throw "Release verification failed: missing updater $UpdaterName"
        }
        $Reader = New-Object System.IO.StreamReader($Entry.Open())
        try {
            $Text = $Reader.ReadToEnd()
        }
        finally {
            $Reader.Dispose()
        }
        foreach ($Label in @(":backup_existing_files", ":ensure_git", ":cleanup_retired_files")) {
            if ($Text.ToLowerInvariant().IndexOf($Label) -lt 0) {
                throw "Release verification failed: updater label missing $Label in $UpdaterName"
            }
        }
    }
}
finally {
    $Zip.Dispose()
}

Write-Host "Release package written to $ZipPath"
Write-Host "Verified: launcher, app folder, required files, and no generated/runtime data."
