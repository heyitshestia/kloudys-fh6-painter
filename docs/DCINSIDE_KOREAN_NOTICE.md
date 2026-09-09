# DCInside Korean-only startup notice

Introduced in KFPS 3.1.67. This notice is intended for the DCInside community
using Korean as their Windows display language.

## Behavior

- Windows users whose display/UI language is Korean receive the supplied Korean
  message, ending in `-Kloudy`, with a single Korean acknowledgement button.
- Uses `GetUserDefaultUILanguage` and `PRIMARYLANGID == LANG_KOREAN`.
  Regional formats, location, keyboard layouts, environment locale strings and
  additional installed languages do not opt users in. Detection failure and
  non-Windows platforms do not show this targeted message.
- Reads display language once at startup. Changing it takes effect on the next
  launch; no language setting is modified by KFPS.
- Queues after the existing feature, community and background-remover notices.
  Screenshot/capture mode suppresses it without marking it acknowledged.
- The button or Escape dismisses it. Clicking outside does not. Text scrolls on
  short windows; the acknowledgement remains visible outside the scroll area.
- Dismissal uses the existing local settings file, with the independent key
  `dcinsideKoreanNotice202609Acknowledged`. Ordinary preference reset preserves
  this key. Other notices remain independent; application versions do not reset it.
- This follows existing installation-local settings, not an account-synced or
  roaming acknowledgement. Deleting those settings or starting a separate
  installation can show it again. If saving fails, it remains dismissed for the
  current session and may appear again after restart.

## Message and reporting boundaries

The user supplied the Korean copy and approved a short, friendly clarification
of reporting visibility. The popup explains review, Discord sign-in and explicit
submission; issue content is public, and optional technical information is
restricted to Kloudy and authorized staff. It does not claim all report content
is private or submit anything automatically. No report collection, external
browser opening, network request or file attachment is added by this notice.

The popup uses installed Malgun Gothic for Korean text and system emoji fallback.
It adds no downloaded or bundled fonts, artwork, links or extra action buttons.

## Implementation and checks

- `KFPS.UI/src/kfps_ui/display_language.py`: bounded Windows UI-language query.
- `KFPS.UI/src/kfps_ui/settings_service.py`: locale exposure and independent
  persisted acknowledgement.
- `KFPS.UI/qml/shell/DcinsideKoreanWelcomeOverlay.qml`: Korean message and popup.
- `KFPS.UI/qml/Main.qml`: startup queue integration.
- `KFPS.UI/tests/test_dcinside_korean_welcome.py`: language, persistence, error,
  compatibility and message-boundary checks.
- `KFPS.UI/tools/test_dcinside_korean_welcome_workflow.py`: isolated real QML
  launches, dismissal/restart/interruption, queueing, language change, capture
  suppression, read-only settings, wheel scrolling and theme/size screenshots.

Generated screenshots, settings and logs belong under ignored
`runtime/welcome-testing/`, never in release payloads.
The offscreen test renderer explicitly loads installed Windows fonts for its own
process because it does not discover the native Windows font database. No font
files are copied or installed. UI-language variants are simulated in the harness;
the native API and glyph availability are checked separately on the host.

Run the focused unit tests and the opt-in Windows UI workflow from the repository
root using the development Python 3.12 environment:

```text
python -m unittest discover -s KFPS.UI/tests -p test_dcinside_korean_welcome.py -v
python KFPS.UI/tools/test_dcinside_korean_welcome_workflow.py
```

The workflow exercises 13 isolated app launches, including six restart sequences,
and 16 screenshots across eight themes at 960x600 and 1440x1080. It checks real
wheel input, glyph support, layout bounds, acknowledgement, queueing and language
eligibility without changing Windows settings or submitting reports.

Relevant behavior is documented by Microsoft:
[GetUserDefaultUILanguage](https://learn.microsoft.com/en-us/windows/win32/api/winnls/nf-winnls-getuserdefaultuilanguage).

Remaining validation limits: no Windows display-language setting was changed, no
fresh Korean-language Windows machine or packaged release was tested, and this
notice does not change or validate server-side Discord access permissions.
