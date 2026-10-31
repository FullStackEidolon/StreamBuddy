"""Play local XSPF playlists with rotating bumpers and OBS text-file banners."""

import argparse
import logging
import os
from pathlib import Path
import time
import urllib.parse
from urllib.request import url2pathname
import xml.etree.ElementTree as ET

try:
    import vlc
except (ImportError, OSError):
    vlc = None

try:
    import tkinter as tk
    from tkinter import filedialog
except ImportError:
    tk = filedialog = None


class StreamBuddyError(ValueError):
    """An operational error that can be shown without a Python traceback."""

logger = logging.getLogger(__name__)

STARTUP_TIMEOUT = 15.0
STALL_TIMEOUT = 30.0
TEST_DURATION = 5.0
POLL_INTERVAL = 0.1

def _select_path(dialog_title, filetypes=None):
    if tk is None:
        raise StreamBuddyError("Tkinter is unavailable. Install Tk support for your Python to use the setup dialogs.")
    root = None
    try:
        root = tk.Tk()
        root.withdraw()
        if filetypes is not None:
            return filedialog.askopenfilename(parent=root, title=dialog_title, filetypes=filetypes)
        return filedialog.askdirectory(parent=root, title=dialog_title)
    except tk.TclError as exc:
        raise StreamBuddyError(f"Cannot open the setup dialogs. Check Tk and your graphical desktop: {exc}") from exc
    finally:
        if root is not None:
            root.destroy()


def select_folder(dialog_title="Select a folder"):
    return _select_path(dialog_title)


def select_file(dialog_title="Select a file", filetypes=None):
    if filetypes is None:
        filetypes = [("All files", "*.*")]
    return _select_path(dialog_title, filetypes)

#Assemble your video list
# Video list from folder
def get_video_files(folder_path):
    if not folder_path:
        raise StreamBuddyError("Select a bumper folder.")
    video_extensions = {'.mp4', '.avi', '.mkv', '.flv', '.mov'}
    try:
        files = sorted(
            str(path) for path in Path(folder_path).iterdir()
            if path.is_file() and path.suffix.lower() in video_extensions
        )
    except OSError as exc:
        raise StreamBuddyError(f"Cannot read bumper folder '{folder_path}': {exc}") from exc
    if not files:
        raise StreamBuddyError(f"No supported bumper videos found in '{folder_path}'.")
    return files

#Video list from .xspf
def queueBuilder(file_path):
    """Read an XSPF playlist of local files, preserving track order."""
    if not file_path:
        raise StreamBuddyError("Select an XSPF playlist.")
    try:
        root = ET.parse(file_path).getroot()
    except (OSError, ET.ParseError) as exc:
        raise StreamBuddyError(f"Cannot read XSPF playlist '{file_path}': {exc}") from exc
    ns = {'xspf': 'http://xspf.org/ns/0/'}
    tracks = root.findall('xspf:trackList/xspf:track', ns)
    if not tracks:
        raise StreamBuddyError(f"Playlist '{file_path}' contains no tracks.")
    queue = []
    for number, track in enumerate(tracks, 1):
        location = (track.findtext('xspf:location', default='', namespaces=ns) or '').strip()
        if not location:
            raise StreamBuddyError(f"Track {number} has no location in '{file_path}'.")
        try:
            uri = urllib.parse.urlsplit(location)
            if uri.scheme not in ('', 'file') or uri.query or uri.fragment:
                raise ValueError("Only local file locations are supported; encode special characters in the URI.")
            uri_path = uri.path
            if uri.netloc and uri.netloc.lower() != 'localhost':
                if os.name != 'nt':
                    raise ValueError("Mount network media locally and use its local file path.")
                uri_path = '//' + uri.netloc + uri_path
            path = Path(url2pathname(uri_path))
            if not path.is_absolute():
                path = Path(file_path).absolute().parent / path
            if not path.is_file():
                raise ValueError(f"Media file not found: {path}")
        except (OSError, ValueError) as exc:
            raise StreamBuddyError(f"Track {number}: {exc}") from exc
        queue.append(str(path))
    return queue

#Handles playing the current video (banner or episode)
def play_video(video_path, test_mode=False, banner_folder_path=None):
    """Play a local file, watching state/position instead of sleeping its duration."""
    if not Path(video_path).is_file():
        raise StreamBuddyError(f"Media file not found: {video_path}")
    if vlc is None:
        raise StreamBuddyError("VLC is unavailable. Install VLC and run: python -m pip install -r requirements.txt")
    instance = player = media = None
    try:
        try:
            instance = vlc.Instance('--quiet', '--no-video-title-show')
        except (OSError, NameError, AttributeError) as exc:
            raise StreamBuddyError("Cannot initialize VLC. Install VLC and python-vlc for this Python architecture.") from exc
        if instance is None:
            raise StreamBuddyError("Cannot initialize VLC. Check the VLC installation.")
        player = instance.media_player_new()
        media = instance.media_new_path(os.path.abspath(video_path))
        if player is None or media is None:
            raise StreamBuddyError(f"VLC could not create a player for '{video_path}'.")
        player.set_media(media)
        player.set_fullscreen(not test_mode)
        logger.info("Playing %s%s", video_path, " (five-second test)" if test_mode else "")
        if player.play() == -1:
            raise StreamBuddyError(f"VLC could not start playback: {video_path}")

        startup_deadline = time.monotonic() + STARTUP_TIMEOUT
        started_at = None
        last_progress_at = None
        last_position = None
        banner_cleared = False
        while True:
            state = player.get_state()
            now = time.monotonic()
            if state == vlc.State.Error:
                raise StreamBuddyError(f"VLC reported a playback error: {video_path}")
            if state == vlc.State.Ended:
                # Some demux failures go straight from Opening to Ended. Keep
                # accepting tiny valid clips that finish between state polls.
                if started_at is None and player.get_time() <= 0 and player.get_length() <= 0:
                    raise StreamBuddyError(f"VLC ended without playing any media: {video_path}")
                return
            if started_at is None:
                if state == vlc.State.Playing:
                    started_at = last_progress_at = now
                elif now >= startup_deadline:
                    raise StreamBuddyError(f"VLC did not start within {STARTUP_TIMEOUT:g} seconds: {video_path}")
            if started_at is not None:
                if state == vlc.State.Stopped:
                    raise StreamBuddyError(f"VLC stopped before the video ended: {video_path}")
                if test_mode and now - started_at >= TEST_DURATION:
                    return
                position = player.get_time()
                if position >= 0 and position != last_position:
                    last_position = position
                    last_progress_at = now
                elif now - last_progress_at >= STALL_TIMEOUT:
                    raise StreamBuddyError(f"Playback made no progress for {STALL_TIMEOUT:g} seconds: {video_path}")
                if banner_folder_path and not banner_cleared and not test_mode:
                    length = player.get_length()
                    if length > 0 and position >= max(0, length - 2000):
                        set_obs_text_title('', '', '', banner_folder_path)
                        banner_cleared = True
            time.sleep(POLL_INTERVAL)
    finally:
        # Attempt every cleanup step, preserving the original failure/interrupt.
        for resource, action in [(player, 'stop'), (player, 'release'), (media, 'release'), (instance, 'release')]:
            if resource is not None:
                try:
                    getattr(resource, action)()
                except Exception as exc:
                    logger.warning("VLC cleanup (%s) failed: %s", action, exc)



# Extract the episode title from the filename
def extract_episode_title(episode_name):
    """Extracts the episode title based on the naming conventions."""
    # If the input string is empty, return an empty string
    if not episode_name:
        return ""
    
    # Remove the file extension
    episode_name = episode_name.rsplit('.', 1)[0]
    
    # Split the string based on ' - ' delimiter
    segments = episode_name.split(' - ')
    
    # Check for the naming convention "Show Name - Episode#Season# - Episode Title"
    if len(segments) == 3:
        return f"{segments[0]} - {segments[2]}"
    
    # Check for the naming convention "Show Name - Episode Title"
    elif len(segments) == 2:
        return f"{segments[0]} - {segments[1]}"
    
    # If none of the conventions match, return the entire input string
    return episode_name

def set_obs_text_title(last_episode_title, current_episode_title, next_episode_title, banner_folder_path):    
    # Default messages for last and next episodes
    if last_episode_title is None:
        last_episode_title = "Welcome to the stream!"
    if next_episode_title is None:
        next_episode_title = "Thanks for watching!"
    
    if not banner_folder_path or not Path(banner_folder_path).is_dir():
        raise StreamBuddyError("Select an existing folder for the OBS banner text files.")
    titles = {
        'last_episode.txt': last_episode_title,
        'current_episode.txt': current_episode_title,
        'next_episode.txt': next_episode_title,
    }
    failures = []
    for filename, content in titles.items():
        path = Path(banner_folder_path) / filename
        try:
            path.write_text(content, encoding='utf-8')
        except OSError as exc:
            failures.append((path, exc))
    if failures:
        details = '; '.join(f"{path}: {exc}" for path, exc in failures)
        raise StreamBuddyError(f"Cannot write banner file(s): {details}") from failures[0][1]

#Main function
def main(test_mode=False):
    """Validate setup, then repeat complete playlists until stopped."""
    banner_folder_path = None
    banners_initialized = False
    status = 0
    try:
        playlist_path = select_file(dialog_title="Select an XSPF playlist", filetypes=[("XSPF files", "*.xspf"), ("All files", "*.*")])
        if not playlist_path:
            logger.info("Setup canceled.")
            return 0
        video_queue = queueBuilder(playlist_path)
        logger.info("OBS text files: last_episode.txt, current_episode.txt, next_episode.txt (created automatically).")
        banner_folder_path = select_folder("Select a folder for OBS banner text files")
        if not banner_folder_path:
            logger.info("Setup canceled.")
            return 0
        bumper_folder_path = select_folder("Select a folder with bumper videos")
        if not bumper_folder_path:
            logger.info("Setup canceled.")
            return 0
        bumper_queue = get_video_files(bumper_folder_path)
        # Fail before playback if the selected output directory cannot be written.
        banners_initialized = True
        set_obs_text_title('', '', '', banner_folder_path)
        bumper_index = 0
        last_title = None
        while True:
            for index, episode in enumerate(video_queue):
                current_title = extract_episode_title(os.path.basename(episode))
                next_title = (
                    extract_episode_title(os.path.basename(video_queue[index + 1]))
                    if index + 1 < len(video_queue) else None
                )
                set_obs_text_title(last_title, current_title, next_title, banner_folder_path)
                play_video(bumper_queue[bumper_index], test_mode=test_mode, banner_folder_path=banner_folder_path)
                set_obs_text_title('', '', '', banner_folder_path)
                bumper_index = (bumper_index + 1) % len(bumper_queue)
                play_video(episode, test_mode=test_mode)
                last_title = current_title
            logger.info("Reloading completed playlist.")
            video_queue = queueBuilder(playlist_path)
    except KeyboardInterrupt:
        logger.info("Stopping StreamBuddy.")
    except (StreamBuddyError, OSError) as exc:
        logger.error("%s", exc)
        status = 1
    finally:
        if banners_initialized:
            try:
                set_obs_text_title('', '', '', banner_folder_path)
            except (StreamBuddyError, OSError) as exc:
                logger.error("Could not clear OBS banners: %s", exc)
                status = 1
    return status


def cli(argv=None):
    """Both launchers share argument parsing and dependency diagnostics."""
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    parser = argparse.ArgumentParser(description='StreamBuddy script to manage video playback in VLC with OBS integration.')
    parser.add_argument('--test', action='store_true', help='Play each video in a window for up to 5 seconds.')
    args = parser.parse_args(argv)
    missing = []
    if vlc is None:
        missing.append('VLC/python-vlc: install VLC, then run python -m pip install -r requirements.txt')
    if tk is None:
        missing.append('Tkinter: install Tk support for your Python distribution')
    if missing:
        logger.error('Missing playback/setup dependencies: %s. See README.md.', '; '.join(missing))
        return 1
    return main(test_mode=args.test)


if __name__ == "__main__":
    raise SystemExit(cli())
