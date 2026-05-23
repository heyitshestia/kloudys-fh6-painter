$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$sdk = Join-Path $root 'OpenCL-SDK'
$include = Join-Path $sdk 'include'
$lib = Join-Path $sdk 'lib'

if (!(Test-Path (Join-Path $include 'CL\cl.h'))) {
    throw "OpenCL header not found: $include\CL\cl.h"
}
if (!(Test-Path (Join-Path $lib 'OpenCL.lib'))) {
    throw "OpenCL.lib not found: $lib\OpenCL.lib"
}

$env:CGO_CFLAGS = "-DCL_TARGET_OPENCL_VERSION=120 -DCL_DEPTH_STENCIL=0x10BE -DCL_UNORM_INT24=0x10DF -I$include"
$env:CGO_LDFLAGS = "-L$lib -lOpenCL"

Push-Location $root
try {
    go build -o "forza-painter-geometrize-go.exe" ./cmd/forza-painter-geometrize
    Write-Host "Built: $root\forza-painter-geometrize-go.exe"
}
finally {
    Pop-Location
}
