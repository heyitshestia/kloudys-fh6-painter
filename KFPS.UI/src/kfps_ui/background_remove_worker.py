"""Short-lived CPU worker. Invoked by the local tool, not the generator."""
from __future__ import annotations

import json
import importlib.util
import os
from pathlib import Path
import struct
import sys
import time


def main():
    if sys.version_info[:2] != (3, 12) or struct.calcsize("P") != 8:
        raise RuntimeError("This engine needs KFPS's 64-bit Python 3.12 runtime. Repair or update KFPS.")
    directory, model, source, target, options_path = map(Path, sys.argv[1:])
    sys.path.insert(0, str(directory))
    sys.path.insert(1, str(Path(__file__).parent))
    # Qt already ships the VC++ runtime in the KFPS bundle. The separate worker
    # has not loaded Qt, so explicitly include that trusted dependency directory.
    dll_handles = []
    qt = importlib.util.find_spec("PySide6")
    if os.name == "nt" and qt and qt.submodule_search_locations:
        for location in qt.submodule_search_locations:
            dll_handles.append(os.add_dll_directory(location))
    import numpy as np
    from PIL import Image
    import cv2
    from background_remove_processing import (alpha_from_prediction, background_color, color_result,
                                               compose_result, model_input, refine_illustration)

    options = json.loads(options_path.read_text(encoding="utf-8"))
    with Image.open(source) as opened:
        image = opened.convert("RGBA")
    threads = min(options["threads"], os.cpu_count() or 1)
    cv2.setNumThreads(threads)
    started = time.monotonic()
    mode = options.get("mode", "anime")
    engine_version = "not required"
    color = options.get("color", "auto")
    if mode == "color":
        print("INFERENCE Flat colour, CPU", flush=True)
        color = background_color(image) if color == "auto" else color
        result = color_result(image, color, options["tolerance"], options["enclosed"], options["decontaminate"])
    else:
        try:
            import onnxruntime as ort
        except ImportError as exc:
            raise RuntimeError("The CPU engine could not load. Repair KFPS's bundled Python/Qt runtime, then retry. " + str(exc)) from exc
        session_options = ort.SessionOptions()
        session_options.enable_cpu_mem_arena = False
        session_options.intra_op_num_threads = threads
        session_options.inter_op_num_threads = 1
        session_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        print("INFERENCE ISNet Anime, CPU", flush=True)
        session = ort.InferenceSession(str(model), sess_options=session_options, providers=["CPUExecutionProvider"])
        prediction = session.run(None, {session.get_inputs()[0].name: model_input(image)})[0]
        del session
        alpha = alpha_from_prediction(prediction, image.size)
        if mode == "illustration":
            print("REFINE Illustration boundaries", flush=True)
            alpha = refine_illustration(image, alpha)
        result = compose_result(image, alpha, options["cleanup"])
        engine_version = ort.__version__
    elapsed = time.monotonic() - started
    result.save(target, format="PNG")
    values = np.asarray(result.getchannel("A"))
    summary = dict(onnxruntime=engine_version, numpy=np.__version__, provider="CPUExecutionProvider" if mode != "color" else "OpenCV CPU",
                   threads=threads, mode=mode, background_color=color, inference_seconds=round(elapsed, 3),
                   foreground_fraction=round(float((values >= 128).mean()), 5),
                   python=sys.version.split()[0], pid=os.getpid())
    (target.parent / "worker-result.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("COMPLETE " + json.dumps(summary), flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("ERROR " + str(exc), flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)
