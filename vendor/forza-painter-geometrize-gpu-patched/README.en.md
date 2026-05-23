# forza-painter geometrize GPU Version

**Forza is a trademark of Microsoft. This project is unofficial and is not affiliated with or endorsed by Microsoft.**

This is a third-party geometrize JSON generation tool for [forza-painter](https://github.com/forza-painter/forza-painter). Its goal is to improve JSON generation efficiency so that higher-quality liveries can be produced in the same amount of time.

## Differences from the original project

- Uses [OpenCL-SDK](https://github.com/KhronosGroup/OpenCL-SDK) to run error evaluation and primitive rasterization on the GPU for substantial speedups.
- Keeps only Rotated Ellipse rendering (other primitives are not needed for forza-painter).
- Supports PNG alpha input and protects transparent source pixels from being covered by generated geometry.
- Supports parallel batch candidate evaluation for additional performance gains.
- After each accepted primitive, it no longer recalculates full-image error; it computes the minimum delta only inside the ellipse and its bounding region.
- Rewritten in Go. After CGO compilation, binaries can be distributed directly across platforms.

## Build and install

### Requirements

```text
Go w/ CGO >= v1.24
OpenCL-SDK >= v3.0.19
```

### Build on Windows

Clone this project, download the Windows release of [OpenCL-SDK](https://github.com/KhronosGroup/OpenCL-SDK/releases/tag/v2025.07.23), and place it in `/OpenCL-SDK`.

```powershell
powershell -ExecutionPolicy Bypass -File "build-opencl.ps1"
```

For Linux/macOS, check `build-opencl.ps1` and set `CGO_CFLAGS` and `CGO_LDFLAGS` accordingly.

## Usage

### Command line arguments

```text
Usage of forza-painter-geometrize-go.exe:
  -output string
        Output path prefix (default: input image path)
  -preview string
        Optional preview PNG output path
  -profile string
        Profile name fragment under ./settings
  -seed int
        Optional RNG seed for reproducible output
  -settings string
        Path to settings ini file
```

### Example

Suppose the image you want to import into Forza is `C:\work\forza\test.png`,
the preview output path is `C:\work\forza\preview`,
and the config file is `C:\work\forza\settings\c.ini`.

Run:

```cmd
forza-painter-geometrize-go.exe C:\work\forza\test.png -preview "C:\work\forza\preview" -settings "C:\work\forza\settings\c.ini"
```

The tool will print generation progress in real time, and export JSON checkpoints at the shape counts listed in `saveAt` (JSON output path can be changed with `-output`).

After JSON generation is complete and the preview looks good, use your existing forza-painter branch to import it into the game.

FH4/FH5: https://github.com/forza-painter/forza-painter/

FH6: https://github.com/bvzrays/forza-painter-fh6/

## Performance tests

I tested on my work tablet. Even with only an iGPU, performance is still far better than CPU mode (using forza-painter-fh6).

Also, [DavidHuang](https://github.com/hjc4869) helped test on his Ryzen AIMAX395 device. The speedup was dramatic, showing that Xe iGPU performance is not yet this program's bottleneck.

```text
ayylmao.png - c.ini - i5-12500H+iGPU
cpu: ~966ms per ellipse
opencl: ~435ms per ellipse

maozai.jpg - c.ini - i5-12500H+iGPU
cpu: ~11175ms per ellipse
opencl: ~1364ms per ellipse

ayylmao.png - c.ini - aimax395+8060S
cpu: unknown (linux device)
opencl: ~37ms per ellipse

maozai.jpg - c.ini - aimax395+8060S
cpu: unknown (linux device)
opencl: ~340ms per ellipse
```

## Acknowledgements

Original project: https://github.com/forza-painter/forza-painter

Geometrize project (algorithm inspiration): https://github.com/Tw1ddle/geometrize

@hjc4869 for STXHalo performance testing help: https://github.com/hjc4869

## Generative AI disclosure

During development I used generative AI to help plan tasks and write code. The non-Chinese version of this document was also translated by generative AI. The following models were used during development:

- OpenAI GPT-5.5
- OpenAI GPT-5.3 Codex
- Moonshot K2.6
