# StreamBuddy

Play a local XSPF playlist in VLC, inserting rotating bumper videos and updating
three text files that OBS can display during the bumpers.

## Installation

Use Python 3.10 or newer, a graphical desktop, and VLC 3.x installed for the same
architecture as Python. Install VLC from [VideoLAN](https://www.videolan.org/vlc/).
The Python package alone does not install the native VLC application/libraries.

Create a virtual environment and install the Python binding:

```sh
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell instead:
# .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Python must include Tkinter for the setup dialogs. Check with `python -m tkinter`.
If unavailable, install Tk support for your Python distribution (for example,
`python3-tk` on Debian/Ubuntu or the matching `python-tk` formula for Homebrew
Python). Windows Python installers normally offer Tcl/Tk support as an option.

## Running

```sh
python StreamBuddy.py
python StreamBuddy.py --test
```

Select, in order:

1. An XSPF playlist containing local episode/movie files, such as a playlist saved
   by VLC. Track order is preserved. Relative locations resolve from the playlist
   directory; `file:///` locations preserve their platform's absolute paths.
2. An existing writable folder for banner text files. The application creates
   `last_episode.txt`, `current_episode.txt`, and `next_episode.txt` automatically.
3. A folder containing bumper videos: MP4, AVI, MKV, FLV, or MOV. Extensions are
   case-insensitive; subfolders are not scanned. Bumpers rotate in filename order.

Canceling any dialog exits normally. Empty/malformed playlists, missing files,
empty bumper folders, or unwritable banner files produce an error before playback.
Use local files or Windows UNC file URIs; HTTP media is not supported. On macOS or
Linux, mount network storage and use the mounted local paths. A playlist exported
on another operating system must reference paths valid on the playback machine.

Each episode is preceded by a bumper showing the previous/current/next titles.
The first item uses “Welcome to the stream!” for the previous title; the final
item in each playlist cycle uses “Thanks for watching!” for the next title.
Titles follow `Show - S01E01 - Episode Title.ext` or `Show - Episode Title.ext`.

The complete playlist repeats, reloading the XSPF file after each full cycle so
saved playlist edits take effect on the next cycle. Bumper rotation continues
across playlist cycles. Normal playback is fullscreen; `--test` plays each item
in a window for up to **five seconds after playback starts**, or until it ends.
Test mode still plays real media and updates the selected banner files.

Press **Ctrl+C** in the terminal to stop. Player resources are released and banner
text is cleared on exit. Playback stops with an error if VLC rejects a file,
reports an error, cannot start within 15 seconds, or makes no playback-position
progress for 30 seconds. That last limit also applies to a manual pause in VLC.
Unknown duration does not block playback; VLC's end state determines completion.
Failures stop the session rather than silently skipping programming. Read the
terminal message, correct the problem, and restart. Operational failures return
exit status 1; cancellation and Ctrl+C return 0 unless banner cleanup fails.

## OBS setup

Add three OBS text sources and enable **Read from file** for each. Point them at
the exact underscore-separated filenames above in your selected banner folder.
Configure the font, layout, and VLC capture/audio sources in OBS yourself.
StreamBuddy updates text files; it does not create OBS scenes or start a broadcast.

Banner text clears about two seconds before a bumper ends when its duration is
known, and always before the episode begins. Test-mode bumper text stays visible
until the shortened bumper finishes. Text files use UTF-8.

`StreamBuddy OBSWebsocket.py` is retained as a compatibility launcher for this
same workflow. Its old hardcoded folders, single `bannertext.txt` output, and
unused WebSocket connection have been retired. Launching that filename now uses
the same dialogs, three text files, and `--test` behavior as `StreamBuddy.py`.
No OBS WebSocket password or `obswebsocket` package is required.

## Regression tests

```sh
python -m unittest discover -v
```

Tests use real temporary playlists/files and simulate the native VLC and GUI
boundaries. They require no VLC, Tk, OBS, or third-party testing packages. They
cover queue cycles, banner contents, input validation, playback timing and
failures, cleanup, and both command-line entry points. Actual video/audio output
and OBS capture still require a smoke test on the playback computer.
