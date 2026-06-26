# Building and running

## Requirements

- Windows 10 or 11 x64
- 64-bit Python 3.12
- Dependencies from the root `requirements.txt`
- The normal KFPS backend files and `KloudysGalateaGenesis.exe`

## Development run

```powershell
py -3.12 -m pip install -r requirements.txt
py -3.12 KFPS.UI\app.py
```

The source app discovers the KFPS root by searching for `VERSION` and the generator/backend files. Set `KFPS_APP_ROOT` only for unusual local layouts.

## Tests

```powershell
py -3.12 -m unittest discover -s KFPS.UI\tests -v
```

Tests create temporary folders and never invoke game-memory writes.

## Visual capture

```powershell
py -3.12 KFPS.UI\tools\capture_pages.py
```

This launches the real Qt application in deterministic demo mode and captures every page at the required reference sizes.
