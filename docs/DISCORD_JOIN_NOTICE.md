# Join-server button and one-time startup notice

The global Join the server button sits beside the announcement ticker at the
same height. It remains available when the ticker is disabled and uses the
existing ReportService.openDiscord action and centralized permanent invite.
Opening the invitation uses the system default browser; it does not prepare,
collect or submit a problem report.

## One-time behaviour

CommunityWelcomeOverlay uses the same modal spotlight/arrow style as the prior
Report a problem announcement. It opens automatically once after updating,
points to the Join the server button, and presents a friendly server invitation.

The separate communityJoinNoticeAcknowledged setting is false for existing
installations until dismissed. Got it, Escape and the explicit Join the server
action acknowledge the notice. Dismissal survives application restarts and
Reset settings. If the settings file is read-only, dismissal still holds for
the current process and a warning is logged; a later restart may show it again.

On fresh installations, the earlier support/upscaler notice is shown first.
The community notice waits until that notice is dismissed, so they never stack.
Screenshot/development capture mode suppresses automatic notices unless a test
explicitly enables them. No browser opens on startup or outside/spotlight clicks.

## Contest section

The popup includes a visually separate KFPS Vinyl Contest section with:

- Submission through the Community tab with tag `createinsane`.
- Deadline: 30 September 2026.
- First prize: a $50 Steam gift card.
- Second and third prizes: one KFPS supporter key each.

The section disappears on 1 October 2026 according to the computer's local date.
This is display expiry, not an enforcement of submission eligibility or a new
contest timezone rule. If the popup remains open across midnight, it rechecks
the date every minute. The general server invitation remains useful afterward.

This change does not automatically tag or upload artwork, enter anyone into the
contest, issue prizes, or change community permissions.

## Validation

- `KFPS.UI/tests/test_discord_join.py`: existing invite, independent/persistent
  dismissal, preference preservation, settings reset, invalid saved types,
  read-only settings, and contest copy/expiry contracts.
- `KFPS.UI/tools/test_discord_join_workflow.py`: 320 real offscreen shell cases
  across eight themes, two sizes, ten pages and ticker states; mouse/keyboard
  activation with external browser opening mocked.
- `KFPS.UI/tools/test_discord_notice_workflow.py`: sixteen theme/size screenshots,
  acknowledgement, Escape, explicit join, fresh-install notice sequencing,
  contest deadline/expiry, and five fresh-process restart checks.
- The pre-existing feature-welcome workflow remains a regression check for the
  support/upscaler notice.

Runtime evidence belongs under `runtime/discord-integration-testing/`, not in
commits or release payloads. Existing private Discord publisher deployment and
credential records remain outside this client-feature documentation.
