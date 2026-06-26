from __future__ import annotations

import base64
import json
from pathlib import Path

from PySide6.QtCore import QObject, Property, QTimer, Signal, Slot, QUrl
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .qt_utils import is_remote_newer


class VersionService(QObject):
    changed = Signal()

    URL = "https://api.github.com/repos/heyitshestia/kloudys-forza-painter-suite/contents/VERSION?ref=main"

    def __init__(self, version_file: Path, demo=False, parent=None):
        super().__init__(parent)
        try:
            self._local = version_file.read_text(encoding="utf-8").strip() or "unknown"
        except Exception:
            self._local = "unknown"
        self._latest = self._local
        self._available = False
        self._checking = False
        self._blink = True
        self._network = QNetworkAccessManager(self)
        self._network.finished.connect(self._finished)
        self._poll = QTimer(self); self._poll.setInterval(60_000); self._poll.timeout.connect(self.checkNow); self._poll.start()
        self._blink_timer = QTimer(self); self._blink_timer.setInterval(650); self._blink_timer.timeout.connect(self._tick); self._blink_timer.start()
        if not demo:
            QTimer.singleShot(500, self.checkNow)

    @Property(str, notify=changed)
    def localVersion(self): return self._local
    @Property(str, notify=changed)
    def latestVersion(self): return self._latest
    @Property(bool, notify=changed)
    def updateAvailable(self): return self._available
    @Property(bool, notify=changed)
    def checking(self): return self._checking
    @Property(bool, notify=changed)
    def blinkOn(self): return self._blink
    @Property(str, notify=changed)
    def displayText(self): return f"v{self._local}"

    @Slot()
    def checkNow(self):
        if self._checking:
            return
        self._checking = True; self.changed.emit()
        request = QNetworkRequest(QUrl(self.URL + "&t=1"))
        request.setRawHeader(b"User-Agent", b"KFPS-QML/1.0")
        self._network.get(request)

    def _finished(self, reply: QNetworkReply):
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                return
            payload = json.loads(bytes(reply.readAll()).decode("utf-8"))
            encoded = str(payload.get("content", "")).replace("\n", "")
            remote = base64.b64decode(encoded).decode("utf-8").strip()
            if remote:
                self._latest = remote
                self._available = is_remote_newer(self._local, remote)
        except Exception:
            pass
        finally:
            self._checking = False
            reply.deleteLater()
            self.changed.emit()

    def _tick(self):
        if self._available:
            self._blink = not self._blink; self.changed.emit()
        elif not self._blink:
            self._blink = True; self.changed.emit()
