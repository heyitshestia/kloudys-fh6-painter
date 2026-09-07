from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

UI = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(UI / "src"))
from kfps_ui.report_service import ReportService
from kfps_ui.support_report import DISCORD_URL
from kfps_ui.settings_service import SettingsService


class DiscordJoinTests(unittest.TestCase):
    def test_join_reuses_the_existing_permanent_invite_without_collecting_reports(self):
        with patch("kfps_ui.report_service.QDesktopServices.openUrl", return_value=True) as opened:
            ReportService.openDiscord(None)
        self.assertEqual(opened.call_count, 1)
        self.assertEqual(opened.call_args.args[0].toString(), "https://discord.gg/XT8dG8bDKy")
        self.assertEqual(DISCORD_URL, "https://discord.gg/XT8dG8bDKy")

    def test_join_is_shell_level_and_shares_ticker_height(self):
        main = (UI / "qml/Main.qml").read_text()
        button = main.split('objectName: "JoinSupportServer"', 1)[1].split("AnnouncementTicker {", 1)[0]
        self.assertIn('text: "Join the server"', button)
        self.assertIn("height: announcementTicker.height", button)
        self.assertIn("reportService.openDiscord()", button)
        self.assertNotIn("openSupportForm", button)
        self.assertNotIn("https://", button)
        self.assertIn("announcementTicker.visible || joinServerButton.visible", main)

    def test_new_notice_is_independent_and_remembers_dismissal_after_reset_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            path.write_text(json.dumps({"supportUpscalerNoticeAcknowledged": True, "backupFolder": "D:/backups"}))
            service = SettingsService(path)
            self.assertFalse(service.communityJoinNoticeAcknowledged)
            service.acknowledgeCommunityJoinNotice()
            restarted = SettingsService(path)
            self.assertTrue(restarted.communityJoinNoticeAcknowledged)
            self.assertTrue(restarted.supportUpscalerNoticeAcknowledged)
            self.assertEqual(restarted.backupFolder, "D:/backups")
            restarted.reset()
            self.assertTrue(SettingsService(path).communityJoinNoticeAcknowledged)

    def test_bad_notice_values_do_not_skip_it_and_read_only_settings_still_allow_dismissal(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "settings.json"
            for value in ("false", "true", 1, None, []):
                path.write_text(json.dumps({"communityJoinNoticeAcknowledged": value}))
                self.assertFalse(SettingsService(path).communityJoinNoticeAcknowledged)
            service = SettingsService(path)
            with patch.object(service, "save", side_effect=PermissionError("read only")), self.assertLogs("kfps_ui.settings_service", level="WARNING"):
                service.acknowledgeCommunityJoinNotice()
            self.assertTrue(service.communityJoinNoticeAcknowledged)

    def test_contest_details_and_popup_have_no_automatic_submission(self):
        text = (UI / "qml/shell/CommunityWelcomeOverlay.qml").read_text()
        for value in ("createinsane", "30 September 2026", "$50 Steam gift card", "one KFPS supporter key each"):
            self.assertIn(value, text)
        self.assertIn("visible: root.contestActive", text)
        self.assertIn("new Date(2026, 9, 1)", text)
        self.assertNotIn("openSupportForm", text)
        self.assertNotIn("openUrl", text)
        self.assertIn("Popup.NoAutoClose", text)
        main = (UI / "qml/Main.qml").read_text()
        self.assertIn("settings.supportUpscalerNoticeAcknowledged && !featureWelcome.visible", main)


if __name__ == "__main__":
    unittest.main()
