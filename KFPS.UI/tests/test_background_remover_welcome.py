from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UI / "src"))
from kfps_ui.settings_service import SettingsService


class BackgroundRemoverWelcomeTests(unittest.TestCase):
    def test_existing_notices_do_not_suppress_new_notice(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(json.dumps({"supportUpscalerNoticeAcknowledged": True,
                                        "communityJoinNoticeAcknowledged": True,
                                        "reducedMotion": True, "backupFolder": "D:/backups"}))
            service = SettingsService(path)
            self.assertFalse(service.backgroundRemoverNoticeAcknowledged)
            service.acknowledgeBackgroundRemoverNotice()
            restarted = SettingsService(path)
            self.assertTrue(restarted.backgroundRemoverNoticeAcknowledged)
            self.assertTrue(restarted.supportUpscalerNoticeAcknowledged)
            self.assertTrue(restarted.communityJoinNoticeAcknowledged)
            self.assertTrue(restarted.reducedMotion)
            self.assertEqual(restarted.backupFolder, "D:/backups")
            restarted.reset()
            self.assertTrue(SettingsService(path).backgroundRemoverNoticeAcknowledged)

    def test_new_install_starts_unacknowledged_and_notices_remain_independent(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = SettingsService(Path(tmp) / "settings.json")
            self.assertFalse(service.backgroundRemoverNoticeAcknowledged)
            service.acknowledgeBackgroundRemoverNotice()
            self.assertFalse(service.supportUpscalerNoticeAcknowledged)
            self.assertFalse(service.communityJoinNoticeAcknowledged)

    def test_invalid_saved_values_do_not_hide_notice(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            for value in ("false", "true", 1, None, []):
                path.write_text(json.dumps({"backgroundRemoverNoticeAcknowledged": value}))
                self.assertFalse(SettingsService(path).backgroundRemoverNoticeAcknowledged)

    def test_read_only_settings_still_allow_session_dismissal(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = SettingsService(Path(tmp) / "settings.json")
            with patch.object(service, "save", side_effect=PermissionError("read only")), self.assertLogs("kfps_ui.settings_service", level="WARNING"):
                service.acknowledgeBackgroundRemoverNotice()
            self.assertTrue(service.backgroundRemoverNoticeAcknowledged)

    def test_notice_is_queued_and_only_navigates_on_explicit_action(self):
        main = (UI / "qml/Main.qml").read_text()
        self.assertIn('onOpenRequested: appController.navigate("background-remover")', main)
        timer = main.split("id: backgroundRemoverNoticeTimer", 1)[1].split("Timer {", 1)[0]
        for condition in ("window.visible && !screenshotMode",
                          "settings.supportUpscalerNoticeAcknowledged && !featureWelcome.visible",
                          "settings.communityJoinNoticeAcknowledged && !communityWelcome.visible",
                          "!settings.backgroundRemoverNoticeAcknowledged && !backgroundRemoverWelcome.visible"):
            self.assertIn(condition, timer)
        overlay = (UI / "qml/shell/BackgroundRemoverWelcomeOverlay.qml").read_text()
        for forbidden in ("backgroundRemoveService.start", "openUrl", "openSupportForm", "prepare("):
            self.assertNotIn(forbidden, overlay)
        self.assertIn("Popup.NoAutoClose", overlay)
        self.assertIn("Keys.onEscapePressed: root.dismiss(false)", overlay)
        self.assertIn("settings.acknowledgeBackgroundRemoverNotice()", overlay)


if __name__ == "__main__":
    unittest.main()
