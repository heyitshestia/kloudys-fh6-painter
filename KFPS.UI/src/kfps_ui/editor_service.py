from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import QObject, Property, Signal, Slot

from .app_paths import AppPaths
from .desktop_service import DesktopService
from .log_service import LogService
from .models import DictListModel
from .preview_service import PreviewService


class EditorService(QObject):
    changed=Signal()
    def __init__(self,paths:AppPaths,preview:PreviewService,desktop:DesktopService,log:LogService,parent=None):
        super().__init__(parent);self.paths=paths;self.preview=preview;self.desktop=desktop;self.log=log;self._project_model=DictListModel(["name","path","modifiedLabel"]);self._selected="";self._preview="";self._shapes="—";self.refresh()

    @Property(QObject, constant=True)
    def projectModel(self):return self._project_model

    @Property(str,notify=changed)
    def selectedPath(self):return self._selected
    @Property(str,notify=changed)
    def selectedName(self):
        if not self._selected:return "—"
        name=Path(self._selected).name;return name.removesuffix(".fabric-project.json")
    @Property(str,notify=changed)
    def selectedShapes(self):return self._shapes
    @Property(str,notify=changed)
    def previewUrl(self):return self._preview
    @Slot()
    def refresh(self):
        import time,json
        root=self.paths.project_root;root.mkdir(parents=True,exist_ok=True);rows=[]
        for path in root.rglob("*.fabric-project.json"):
            age=max(0,int(time.time()-path.stat().st_mtime));label=f"{age//60}m ago" if age<3600 else f"{age//3600}h ago" if age<86400 else f"{age//86400}d ago";rows.append({"name":path.name.removesuffix(".fabric-project.json"),"path":str(path),"modifiedLabel":label,"mtime":path.stat().st_mtime})
        rows.sort(key=lambda r:r["mtime"],reverse=True);self._project_model.replace([{k:r[k] for k in ("name","path","modifiedLabel")} for r in rows]);self.changed.emit()
    @Slot(int)
    def select(self,index):
        import json
        row=self._project_model.row(index)
        if not row:return
        self._selected=str(row["path"]);self._preview=self.preview.preview_for_json(self._selected)
        try:
            data=json.loads(Path(self._selected).read_text(encoding="utf-8"));items=data.get("shapes",data.get("layers",[])) if isinstance(data,dict) else data;self._shapes=str(len(items)) if isinstance(items,list) else "unknown"
        except Exception:self._shapes="unknown"
        self.changed.emit();self.log.append(f"Selected editor project: {self._selected}")
    @Slot()
    def launch(self):self._launch("")
    @Slot()
    def launchSelected(self):self._launch(self._selected)
    def _launch(self,project):
        launcher=self.paths.app_root/"tools"/"fabric-editor"/"start_fabric_editor.py"
        if not launcher.is_file():self.log.append(f"Fabric editor launcher not found: {launcher}","error");return
        args=[self.paths.python_executable,str(launcher)]
        if project:
            try:args += ["--project-id",str(Path(project).resolve().relative_to(self.paths.project_root.resolve())).replace("\\","/")]
            except Exception:pass
        try:
            flags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess,"CREATE_NO_WINDOW") else 0
            subprocess.Popen(args,cwd=self.paths.app_root,creationflags=flags,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);self.log.append("Opened Fabric editor"+(f" with {Path(project).name}" if project else "")+".")
        except Exception as exc:self.log.append(f"Could not open Fabric editor: {exc}","error")
    @Slot()
    def openProjects(self):self.desktop.openFolder(str(self.paths.project_root))
    @Slot()
    def openEditorFolder(self):self.desktop.openFolder(str(self.paths.app_root/"tools"/"fabric-editor"))
