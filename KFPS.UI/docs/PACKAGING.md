# Packaging

KFPS now ships as loose QML/Python application files plus a small native launcher. The launcher is built from `tools/native_launcher/KFPSLauncher.cs` and only starts the bundled Python runtime against `KFPS.UI/app.py`; it does not embed QML, Python modules, backend scripts, or assets.

The standalone layout is:

```text
Standalone root/
├── KFPS.exe
├── Images/
└── KloudysFH6Painter/
    ├── VERSION
    ├── KFPS.exe
    ├── KloudysGalateaGenesis.exe
    ├── python/
    ├── generator_backend.py
    ├── KFPS.UI/
    ├── tools/
    ├── settings/
    └── imgs/
```

`Standalone root/KFPS.exe` is the user-facing launcher. `KloudysFH6Painter/KFPS.exe` is the tracked updater payload used to repair or replace the parent launcher. The updater verifies the parent launcher by SHA256 so an old large binary and the new small launcher cannot be confused just because both are named `KFPS.exe`.

Bundled releases must include:

- the parent `KFPS.exe`
- the full `KloudysFH6Painter` app folder
- `KloudysFH6Painter/KFPS.exe` as the launcher repair payload
- `KloudysFH6Painter/python/` with Python 3.12 and app dependencies
- an `Images/` folder beside `KFPS.exe`

The in-app updater closes `KFPS.exe` and invokes `03_update_from_github.bat`. The batch updater preserves generated/runtime/user data, mirrors program files from GitHub, verifies tracked files, then verifies the parent launcher hash.
