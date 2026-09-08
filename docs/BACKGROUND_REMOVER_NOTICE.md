# Background Remover Introduction (3.1.65)

The local remover now has a separate one-time introduction with an explicit
Open Background Remover action. It explains local processing, available modes,
correction tools and first-use AI downloads. It never starts a job, downloads a
model or opens a browser by itself.

`backgroundRemoverNoticeAcknowledged` is independent of the support/upscaler and
community notices. Missing or invalid values show the new notice. Got it, Escape
and Open Background Remover all acknowledge it. Dismissal survives restarts and
settings resets. If settings cannot be written, dismissal remains effective for
the current process; it may reappear after restarting until writes are possible.

The Main.qml timer waits for both prior notices to be acknowledged and closed.
Capture mode suppresses the popup without acknowledging it. The popup is modal,
keyboard accessible, theme-aware, and keeps actions outside its scrollable body.

Validation uses `test_background_remover_welcome.py` and the opt-in actual-shell
`test_background_remover_welcome_workflow.py` with isolated settings. The latter
covers 16 theme/size captures, four process restarts, fresh-install queueing,
explicit navigation, Escape, read-only settings and screenshot suppression.

The first harness iteration attempted to read an unsupported Qt enum directly;
the test now verifies rendered image dimensions. Fault injection originally
retained an exception traceback through a mock, triggering Qt teardown failure.
A fresh exception from a plain replacement callable exercises the same write
failure without retaining that artificial object graph. No production failure
was suppressed or bypassed.
