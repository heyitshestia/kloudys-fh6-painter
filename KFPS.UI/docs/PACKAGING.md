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

The in-app updater closes `KFPS.exe` and invokes the existing `03_update_from_github.bat` visibly. The batch updater preserves runtime/generated data and leaves relaunching to the user so the freshly replaced single-file executable is not started from a transient update handoff.
