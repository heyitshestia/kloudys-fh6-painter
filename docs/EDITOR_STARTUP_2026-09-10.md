# Editor Startup Hardening

Target: KFPS 3.1.74. The supplied DCInside report names .73 for an editor that
stopped responding until New Canvas was used, and .72/.73 for black windows.
No original failing project, desktop log or hardware details were available.
These fixes cover reproduced failure paths, not a claim that every black-screen
cause has been identified.

## Changes

- Reopen used a URL differing only by its session fragment, which Chromium could
  treat as same-document navigation. A unique restart query forces a new page,
  without automatically reopening a selected project or deleting stored data.
- Native startup reports starting/ready/failed using the existing installation-
  scoped marker. A 60-second deadline displays the existing retry panel. Canceled
  navigation is distinguished from a genuine load failure.
- The client distinguishes no instance from a connected instance that rejected
  or did not acknowledge a request. It never replays a potentially accepted New
  Canvas/project command; cold-start polling only sends idempotent activation.
- Early Python/Qt bootstrap errors are recorded in a UTF-8 log and PID-matched
  diagnostic. Standalone launches show a dialog; KFPS displays its worker result.
- Generator/Open Editor activates existing work, with progress/error feedback.
- Project/resource/reference reads are bounded. Work yields even when animation
  frames are suspended. Reference callback exceptions now reject their promise.
- Unavailable browser storage no longer aborts the early theme/resource setup.
  Korean console diagnostics no longer depend on the Windows console encoding.
- Small unauthorized POST bodies are discarded without parsing/storing, within
  64 KiB and 200 ms bounds, so Windows receives the intended 403 rather than a
  connection reset. Authorization, allowed origins and write rules are unchanged.

## Evidence

- Baseline suspended-frame probe: no completion within 1.2 s. Patched: 0.1 s.
- 801 Python tests passed, plus four Node suites and 10 localization tests.
- Real 3,000-layer native save/export, main-app output notification, duplicate
  standalone launch, Cancel/Discard/Save close paths, exact restart recovery,
  and exact recovery after owned-renderer termination passed.
- Both actual QML buttons launched/activated the same independent host. It stayed
  alive after the main app exited. Cold EXE and KFPS-service launches preserved
  favorites across forced host exit and restart.
- Native missing-JavaScript timeout/retry and renderer retry passed, including
  the offscreen CI configuration, with stored sentinel data unchanged.
- Korean cold project loading, malformed-project response preservation/retry,
  injected reference callback failure, and browser-storage denial passed.
- Missing-PySide bootstrap test exited with code 1 and a matching diagnostic.

The first two full-suite runs exposed an intermittent rejected-request TCP reset
on Windows. The bounded discard fix passed the original assertions and 30 repeated
unauthorized writes without creating a project. No security assertion was relaxed.
The existing PySide shutdown garbage-collection warning remains.

## Storage Compatibility

The separately validated pending capacity patch is included: 50 MiB embedded
reference and 100 MiB serialized project/recovery. Asset and flat-export budgets
are unchanged. Prior paired tests found similar costs for unchanged inputs;
near-limit files use substantially more memory and can cause multi-second stalls
on throttled CPUs. This raises capacity, not a promise of stutter-free editing.

No Fabric replacement, shape-ID conversion, game save changes, launcher binary
rebuild, personal installation changes or manual release bundle are included.
