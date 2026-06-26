# Packaging

`KFPS.UI/packaging/KFPS.spec` builds one `KFPS.exe` with QML, artwork, SVG icons, and the frontend Python package embedded. Backend scripts and large user/runtime folders remain outside the executable in the normal KFPS package.

The executable expects the established standalone layout:

```text
Standalone root/
├── KFPS.exe
├── Images/
└── KloudysFH6Painter/
    ├── VERSION
    ├── KloudysGalateaGenesis.exe
    ├── python/
    ├── generator_backend.py
    ├── KFPS.UI/
    ├── tools/
    ├── settings/
    └── imgs/
```

The in-app updater closes `KFPS.exe`, invokes the existing `03_update_from_github.bat`, preserves runtime/generated data through that existing updater, and relaunches the root executable on success.
