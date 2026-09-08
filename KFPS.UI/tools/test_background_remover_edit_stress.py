"""Opt-in 16MP correction responsiveness, bounded history and process-restart check."""
from __future__ import annotations

from datetime import datetime
import gc
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

UI=Path(__file__).resolve().parents[1]
ROOT=UI.parent
sys.path.insert(0,str(UI/"src"))
os.environ["QT_QPA_PLATFORM"]="offscreen"
import psutil
from PIL import Image, ImageDraw
from PySide6.QtCore import QCoreApplication, QTimer
from kfps_ui.background_remove_document import MaskDocument
from kfps_ui.background_remove_service import BackgroundRemoveService
from kfps_ui.upscale_engine import atomic_json, sha256


def main():
    if len(sys.argv)==4 and sys.argv[1]=="--reopen":
        document=MaskDocument.open(Path(sys.argv[2]))
        assert sha256(document.current_path)==sys.argv[3]
        assert document.can_undo
        document.step(-1)
        document.step(1)
        assert sha256(document.current_path)==sys.argv[3]
        exported=document.export(document.run/"restart-export")
        assert Image.open(exported).tobytes()==document.current().tobytes()
        print(json.dumps(dict(reopened=True,exported=str(exported))))
        return 0
    out=ROOT/"runtime/background-remover/validation"/datetime.now().strftime("edit-stress-%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    run=out/"app/runtime/background-remover/runs/stress"
    run.mkdir(parents=True)
    image=Image.new("RGBA",(4000,4000),(220,0,0,255))
    draw=ImageDraw.Draw(image)
    draw.ellipse((500,500,3500,3500),fill="white")
    image.save(run/"source.png")
    image.putalpha(255)
    output=out/"initial.png"
    image.save(output)
    del image,draw
    atomic_json(run/"report.json",dict(settings={}))
    original_hash=sha256(run/"source.png")
    document=MaskDocument.create(run,output,"stress.png")
    app=QCoreApplication.instance() or QCoreApplication([])
    paths=SimpleNamespace(app_root=out/"app",runtime_root=out/"app/runtime",ui_root=UI,python_executable=sys.executable)
    service=BackgroundRemoveService(paths,Mock(),Mock(),Mock())
    service._document=document
    summary=dict(size=[4000,4000],edits=[],errors=[])
    ticks=[]
    timer=QTimer()
    timer.setInterval(20)
    timer.timeout.connect(lambda:ticks.append(time.monotonic()))
    timer.start()
    try:
        # A small cap makes pruning observable without retaining dozens of 16MP PNGs.
        with patch("kfps_ui.background_remove_document.MAX_ENTRIES",5):
            for index in range(8):
                start=time.monotonic()
                ticks.clear()
                service.correct("erase" if index%2==0 else "restore",[[.5,.5],[.6,.6]],200,20)
                deadline=start+30
                peak=0
                while service.running and time.monotonic()<deadline:
                    app.processEvents()
                    peak=max(peak,psutil.Process().memory_info().rss)
                    time.sleep(.005)
                assert not service.running and not service.lastError,service.view
                assert len(ticks)>2,"The event loop stopped during the edit"
                gaps=[b-a for a,b in zip([start]+ticks,ticks+[time.monotonic()])]
                assert max(gaps)<1,"UI event loop stalled for over one second"
                gc.collect()
                summary["edits"].append(dict(seconds=round(time.monotonic()-start,3),peak_mb=round(peak/1048576,1),
                                             retained_mb=round(psutil.Process().memory_info().rss/1048576,1),
                                             max_event_gap_ms=round(max(gaps)*1000,1)))
                assert len(document.state["entries"])<=5
        retained=[row["retained_mb"] for row in summary["edits"]]
        assert max(retained[-3:])-min(retained[1:4])<160,"Repeated edits show continuing memory growth"
        assert sha256(run/"source.png")==original_hash
        expected=sha256(document.current_path)
        service.close()
        completed=subprocess.run([sys.executable,"-B",str(Path(__file__).resolve()),"--reopen",str(run),expected],
                                 capture_output=True,text=True,timeout=30,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        assert completed.returncode==0,completed.stdout+completed.stderr
        summary["restart"]=json.loads(completed.stdout)
        summary["retained_revisions"]=len(document.state["entries"])
        summary["pngs_on_disk"]=len(list(document.folder.glob("revision-*.png")))
    except Exception:
        import traceback
        summary["errors"].append(traceback.format_exc())
    finally:
        timer.stop()
        service.close()
        atomic_json(out/"results.json",summary)
    print(json.dumps(dict(results=str(out/"results.json"),**summary),indent=2))
    return int(bool(summary["errors"]))


if __name__=="__main__":
    raise SystemExit(main())
