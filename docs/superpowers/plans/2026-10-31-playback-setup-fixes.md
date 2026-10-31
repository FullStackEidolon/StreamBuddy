# Playback and Setup Repairs Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Repair the playback and setup defects validated in the preceding audit.

**Architecture:** Keep `StreamBuddy.py` as the supported application. Use an immutable episode list with one index, state-based VLC polling with bounded startup/stall waits, and validated local playlist paths. Replace the duplicate OBS script with a compatibility launcher.

**Tech Stack:** Python standard library, python-vlc, Tk file dialogs, unittest.

**Spec:** The user's approved repair scope is the ten-item repair table in this chat, followed by “Fix the outstanding playback and setup issues.” No website or new operator interface is included.

## Global Constraints

- Preserve XSPF order, rotating bumpers, fullscreen playback, and three OBS text files.
- Test mode stops at five seconds of playback or earlier if media ends.
- Canceled setup exits successfully; invalid input or playback failure stops with an actionable error and nonzero status.
- Stop on a failed media item rather than silently skipping requested programming.
- Keep paths, credentials, and machine-specific settings out of source.
- Work on `codex/playback-setup-fixes`; leave changes available for review without publishing.

## Review Focus

- Local URI escaping, Windows drive/UNC paths, and relative playlist locations.
- Playlist edits between complete cycles and one/two/three-item boundaries.
- Very short media, unknown duration, asynchronous VLC errors, and stalled playback.
- Banner-write failures and exceptions during resource cleanup.
- Canceled dialogs and missing Python/native dependencies before opening playback.

## Task 1: Validated setup and banner output

Files: `StreamBuddy.py`, `tests/test_streambuddy.py`, `tests/__init__.py`.

Interfaces: retain `queueBuilder(file_path)`, `get_video_files(folder_path)`, `set_obs_text_title(last, current, next, folder)`, and selection helpers; introduce `StreamBuddyError` for actionable operational errors.

- [x] Write failing tests for decoded absolute/relative file paths, malformed/empty playlists, missing media, case-insensitive file-only discovery, UTF-8 banner contents, write failures, and dialog destruction.
- [x] Run `python3 -m unittest tests.test_streambuddy.SetupTests -v`; verify relevant failures against the current implementation.
- [x] Implement validation, URI conversion, banner error propagation, and guaranteed dialog destruction.
- [x] Run the setup tests and verify all pass.

## Task 2: Playback and queue lifecycle

Files: `StreamBuddy.py`, `tests/test_streambuddy.py`.

Interfaces: retain `play_video(video_path, test_mode=False, banner_folder_path=None)` and `main(test_mode=False)`. Use state polling, a five-second test window, 15-second startup timeout, and 30-second no-progress timeout. `main` returns an exit status.

- [x] Write failing tests with a simulated VLC boundary and clock for episode completion without banners, five-second test playback, unknown duration, errors, startup/stall timeouts, and resource cleanup.
- [x] Write failing orchestration tests with real temporary playlists/banner files for one/two/three-item looping, correct titles, bumper rotation, cancellation, invalid setup, reload failure, and cleanup on interrupt/error.
- [x] Run the tests and verify the failures identify the audited defects.
- [x] Implement state-driven playback, one-index queue traversal, validation before playback, and cleanup on every exit.
- [x] Run `python3 -m unittest discover -v`; verify the entire suite passes.

## Task 3: Supported entry points and final verification

Files: `StreamBuddy OBSWebsocket.py`, `README.md`, `requirements.txt`, `.gitignore`, tests.

Interfaces: `cli(argv=None)` parses the existing `--test` flag and returns an exit status. Both scripts use it.

- [x] Add failing CLI checks for help without GUI/media dependencies, friendly dependency errors, and shared legacy entry behavior.
- [x] Replace duplicate legacy implementation, document install/OBS configuration/error handling/testing, and declare python-vlc.
- [x] Run the complete suite, syntax checks, both CLI help commands, and `git diff --check`.
- [x] Request an independent code review; address substantive findings with regression tests.
- [x] Report evidence and any native VLC/OBS verification limits.

## Execution notes

- Baseline: clean checkout at `21a141b`; no tests existed (`unittest discover` found zero tests).
- Implementing in the current checkout on a dedicated local branch. The explicit repair request authorizes proceeding without another design/plan approval.

- Task 1: complete. Fourteen setup tests reproduced the original defects (12 failures and 2 errors, with one positive-control case) and passed after validation/dialog/banner repairs.
- Task 2: complete. Playback/session regression checks reproduced queue crashes, missing cleanup, unbounded waits, and incorrect test duration; the full suite passed after the repairs.
- Task 3: CLI dependency/help regressions passed after shared entry points and optional dependency diagnostics. Independent read-only review identified one actionable cleanup issue; the new locked-first-banner regression failed before the fix and passed afterward.
- Review scope rulings: HTTP media, XSPF xml:base resolution, automatic retries, and OBS scene automation remain outside this local-file playback repair. Unsupported inputs fail visibly; retries and scene automation are not implied by the existing workflow.
- Native verification found VLC 3.0.24 can transition Opening → Ended for corrupt media with zero position/duration. Added a failing regression and rejected that outcome while retaining valid clips that finish between polls.
- Verification: 40 unittest cases pass; both launchers' help works without optional dependencies; Python compilation and git diff whitespace checks pass.
- Final native verification: all four headless VLC cases passed using generated 0.25s, 2s, and 10s MP4s plus corrupt media. Test mode stopped after 5.05s of observed playback. Player/instance cleanup passed. GUI dialogs, actual audio/video output, Windows execution, and OBS capture were not exercised. Python binding was installed only into a temporary verification environment.
