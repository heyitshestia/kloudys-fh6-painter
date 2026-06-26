from __future__ import annotations

import os
import subprocess
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, Slot

from .app_paths import AppPaths
from .log_service import LogService


class UpdateService(QObject):
    def __init__(self,paths:AppPaths,log:LogService,parent=None):super().__init__(parent);self.paths=paths;self.log=log
    @Slot()
    def startUpdate(self):
        batch=self.paths.app_root/"03_update_from_github.bat"
        if not batch.is_file():self.log.append(f"Updater is missing: {batch}","error");return
        handoff=self.paths.runtime_root/"native-update";handoff.mkdir(parents=True,exist_ok=True);script=handoff/"run-qml-update.ps1";log_file=handoff/"qml-update-handoff.log";parent_root=self.paths.app_root.parent
        ps=f"""$ErrorActionPreference = 'Continue'\n$appRoot = '{str(self.paths.app_root).replace("'","''")}'\n$parentRoot = '{str(parent_root).replace("'","''")}'\n$batchPath = '{str(batch).replace("'","''")}'\n$logPath = '{str(log_file).replace("'","''")}'\n$parentPid = {os.getpid()}\nfunction Write-Log([string]$m) {{ "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $m" | Add-Content -LiteralPath $logPath -Encoding UTF8 }}\nWrite-Log 'QML update handoff started.'\ntry {{ Wait-Process -Id $parentPid -Timeout 60 -ErrorAction SilentlyContinue }} catch {{}}\nStart-Sleep -Milliseconds 500\n$env:FORZA_PAINTER_NO_PAUSE = '1'\n$p = Start-Process -FilePath $env:ComSpec -ArgumentList @('/c', "`"$batchPath`"") -WorkingDirectory $appRoot -Wait -PassThru -WindowStyle Normal\nWrite-Log ("Updater exited " + $p.ExitCode)\nif ($p.ExitCode -eq 0) {{ $exe = Join-Path $parentRoot 'KFPS.exe'; if (Test-Path $exe) {{ Start-Process $exe -WorkingDirectory $parentRoot }} }}\n"""
        script.write_text(ps,encoding="utf-8")
        try:
            subprocess.Popen(["powershell.exe","-NoProfile","-ExecutionPolicy","Bypass","-File",str(script)],cwd=self.paths.app_root,creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0));self.log.append("Updater handoff started. Closing KFPS.");QCoreApplication.quit()
        except Exception as exc:self.log.append(f"Could not start updater handoff: {exc}","error")
