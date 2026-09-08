# Background Remover Notices

KFPS's optional local remover uses the unmodified ISNet Anime ONNX model by
SkyTNT's anime-segmentation project. The model distributed through rembg is
identified by the exact SHA-256 in `engine.json`. The Apache-2.0 license is
included in `ISNET-LICENSE.txt`.

- Model source: https://github.com/SkyTNT/anime-segmentation
- Model distribution: https://github.com/danielgatis/rembg/releases/tag/v0.0.0
- ONNX Runtime CPU: https://github.com/microsoft/onnxruntime (MIT)
- Model-choice and preprocessing reference: https://github.com/duchil6063/ForzaSqueegee (MIT)

No ForzaSqueegee or rembg Python source is vendored, and neither project is a
runtime dependency. KFPS's cleanup is independently implemented, opt-in, and
does not use ForzaSqueegee's component/hull cleanup heuristic. The model and
preprocessing are anime-focused; universal text or photo segmentation is not
promised.

The optional runtime downloads exact PyPI wheels for ONNX Runtime, coloredlogs,
humanfriendly, pyreadline3, FlatBuffers, packaging, protobuf, SymPy, and mpmath.
All wheel files, including their original copyright and license notices, are
retained unchanged in the isolated runtime and verified archives. NumPy and
Pillow are existing KFPS dependencies; OpenCV is used only for opt-in cleanup.
No Python packages are installed into the application or system environment.

Runtime archive and installed-file integrity is checked against pinned archive
bytes, not a mutable local receipt. This does not replace signing of the KFPS
application/catalog itself. Upstream model files are not uploaded or modified.
