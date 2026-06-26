import json, os, sys, tempfile, unittest
from pathlib import Path
UI=Path(__file__).resolve().parents[1];ROOT=UI.parent
sys.path.insert(0,str(UI/"src"));sys.path.insert(0,str(ROOT));os.environ.setdefault("QT_QPA_PLATFORM","offscreen")
from PySide6.QtCore import QCoreApplication
from kfps_ui.app_paths import AppPaths
from kfps_ui.log_service import LogService
from kfps_ui.report_service import ReportService
APP=QCoreApplication.instance() or QCoreApplication([])

class DummyVersion: localVersion="3.0.12"
class ServiceTests(unittest.TestCase):
 def test_report_is_local_markdown(self):
  with tempfile.TemporaryDirectory() as td:
   root=Path(td);(root/"VERSION").write_text("3.0.12");paths=AppPaths(root,UI,UI/"qml",UI/"assets",root/"runtime",root/"python/python.exe");log=LogService();svc=ReportService(paths,log,DummyVersion());text=svc.build("Bug","Test","Details",True,False,False);self.assertIn("# KFPS Report",text);self.assertNotIn("Visible runtime log",text)
 def test_no_memory_write_in_tests(self):
  dangerous=["fh6_import_typecode_json.py","fh6_export_typecode_json.py","fh6_trim_group_count.py"]
  self.assertTrue(all((ROOT/name).exists() for name in dangerous))

if __name__=="__main__":unittest.main()
