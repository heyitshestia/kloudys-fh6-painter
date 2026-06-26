param(
    [string]$Python = "py",
    [string]$PythonArgs = "-3.12"
)
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $Root

if ($Python -eq "py") {
    & py -3.12 -c "import sys; assert sys.version_info[:2] == (3,12) and sys.maxsize > 2**32"
    & py -3.12 -m pip install -r requirements.txt
    & py -3.12 -m unittest discover -s KFPS.UI\tests -v
    & py -3.12 -m PyInstaller --noconfirm --clean KFPS.UI\packaging\KFPS.spec
} else {
    & $Python -c "import sys; assert sys.version_info[:2] == (3,12) and sys.maxsize > 2**32"
    & $Python -m pip install -r requirements.txt
    & $Python -m unittest discover -s KFPS.UI\tests -v
    & $Python -m PyInstaller --noconfirm --clean KFPS.UI\packaging\KFPS.spec
}
if ($LASTEXITCODE -ne 0) { throw "KFPS build failed with exit code $LASTEXITCODE" }
Write-Host "Built: $Root\dist\KFPS.exe"
