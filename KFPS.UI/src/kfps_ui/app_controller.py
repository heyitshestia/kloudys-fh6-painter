from __future__ import annotations

from PySide6.QtCore import QObject, Property, Signal, Slot


class AppController(QObject):
    changed=Signal()
    PAGES={"dashboard":"Dashboard","generate":"Generate","json":"JSON Import / Export","editor":"Editor","images":"Images","tools":"Tools","help":"Help","reports":"Reports","update":"Update","settings":"Settings"}
    LOG_PAGES={"generate","json","editor","images","reports"}
    def __init__(self,parent=None):super().__init__(parent);self._page="dashboard"
    @Property(str,notify=changed)
    def currentPage(self):return self._page
    @Property(str,notify=changed)
    def pageTitle(self):return self.PAGES.get(self._page,"KFPS")
    @Property(str,notify=changed)
    def windowTitle(self):return f"KFPS — {self.pageTitle}"
    @Property(bool,notify=changed)
    def showBottomPanel(self):return self._page=="dashboard" or self._page in self.LOG_PAGES
    @Property(str,notify=changed)
    def bottomMode(self):return "changelog" if self._page=="dashboard" else "log"
    @Slot(str)
    def navigate(self,page):
        if page in self.PAGES and page!=self._page:self._page=page;self.changed.emit()
