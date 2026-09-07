from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UI / "src"))
from kfps_ui.settings_service import SettingsService


class FeatureWelcomeTests(unittest.TestCase):
    def test_old_settings_show_notice_and_preserve_other_preferences(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(json.dumps({"reducedMotion": True, "backupFolder": "D:/backups"}))
            service = SettingsService(path)
            self.assertFalse(service.supportUpscalerNoticeAcknowledged)
            service.acknowledgeSupportUpscalerNotice()
            restarted = SettingsService(path)
            self.assertTrue(restarted.supportUpscalerNoticeAcknowledged)
            self.assertTrue(restarted.reducedMotion)
            self.assertEqual("D:/backups", restarted.backupFolder)

    def test_new_settings_show_once_and_reset_does_not_repeat_notice(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            service = SettingsService(path)
            self.assertFalse(service.supportUpscalerNoticeAcknowledged)
            service.acknowledgeSupportUpscalerNotice()
            service.reset()
            self.assertTrue(SettingsService(path).supportUpscalerNoticeAcknowledged)

    def test_bad_acknowledgement_types_do_not_silently_hide_notice(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            for value in ("false", "true", 1, None, []):
                path.write_text(json.dumps({"supportUpscalerNoticeAcknowledged": value}))
                self.assertFalse(SettingsService(path).supportUpscalerNoticeAcknowledged)

    def test_read_only_settings_do_not_trap_user_in_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = SettingsService(Path(tmp) / "settings.json")
            with patch.object(service, "save", side_effect=PermissionError("read only")), self.assertLogs("kfps_ui.settings_service", level="WARNING"):
                service.acknowledgeSupportUpscalerNotice()
            self.assertTrue(service.supportUpscalerNoticeAcknowledged)

    def test_overlay_has_no_network_or_report_submission_actions(self):
        text = (UI / "qml/shell/FeatureWelcomeOverlay.qml").read_text()
        self.assertNotIn("openSupportForm", text)
        self.assertNotIn("openUrl", text)
        self.assertIn("Popup.NoAutoClose", text)
        self.assertIn("settings.acknowledgeSupportUpscalerNotice()", text)
        self.assertIn("root.visible", text)


if __name__ == "__main__":
    unittest.main()
