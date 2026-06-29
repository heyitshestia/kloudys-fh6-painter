param(
    [string]$Output = ""
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if (-not $Output) {
    $Output = Join-Path $Root "KFPS.exe"
}

$Compiler = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path -LiteralPath $Compiler)) {
    $Compiler = Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe"
}
if (-not (Test-Path -LiteralPath $Compiler)) {
    throw "Could not find the .NET Framework C# compiler."
}

$Icon = Join-Path $Root "assets\kfps-logo.ico"
$Source = Join-Path $PSScriptRoot "KFPSLauncher.cs"
$Args = @(
    "/nologo",
    "/target:winexe",
    "/platform:x86",
    "/optimize+",
    "/reference:System.dll",
    "/reference:System.Windows.Forms.dll",
    "/out:$Output"
)
if (Test-Path -LiteralPath $Icon) {
    $Args += "/win32icon:$Icon"
}
$Args += $Source

& $Compiler @Args
if ($LASTEXITCODE -ne 0) {
    throw "Launcher build failed with exit code $LASTEXITCODE"
}

Get-Item -LiteralPath $Output | Select-Object FullName,Length,LastWriteTime
Get-FileHash -Algorithm SHA256 -LiteralPath $Output | Select-Object Hash
