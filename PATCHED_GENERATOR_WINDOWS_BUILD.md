# Patched Windows Generator Build

Windows currently uses the bundled executable at:

- `forza-painter-geometrize-go.exe`

Linux testing here used a different binary built from a patched source tree. That patched source has been vendored into this repo at:

- `vendor/forza-painter-geometrize-gpu-patched`

## Source provenance

- Upstream repo: `https://github.com/zjl88858/forza-painter-geometrize-gpu`
- Upstream base commit in the local working tree: `c5daa3849113004fc844d8d27e9d8aa448e1057a`

Local generator changes exist in these source files:

- `internal/config/settings.go`
- `internal/engine/engine.go`
- `internal/gpu/kernels.go`
- `internal/gpu/opencl.go`
- `internal/imageutil/image.go`
- `internal/model/types.go`
- `internal/render/ellipse.go`

Those patches are what produced the better Linux-side results and performance.

## Build on Windows

Prerequisites:

- 64-bit Go installed and available in `PATH`
- OpenCL SDK unpacked at:
  - `vendor/forza-painter-geometrize-gpu-patched/OpenCL-SDK`
- `OpenCL-SDK/include/CL/cl.h`
- `OpenCL-SDK/lib/OpenCL.lib`

Then run from the repo root:

```powershell
powershell -ExecutionPolicy Bypass -File .\build_patched_generator_windows.ps1
```

What it does:

1. Builds the vendored patched generator using its own `build-opencl.ps1`
2. Backs up the current bundled exe as:
   - `forza-painter-geometrize-go.exe.bak-<timestamp>`
3. Replaces the app’s bundled:
   - `forza-painter-geometrize-go.exe`

After that, the FH6 app will use the rebuilt patched generator automatically.

## Why this matters

The FH6 Python/V2 layer was already synced, but Windows was still using the old bundled raw generator exe. That means:

- same GUI: yes
- same V2 wrapper: yes
- same presets: yes
- same raw generator behavior: no

Replacing the bundled exe with one built from the vendored patched source is the step required for true parity with the Linux results.

