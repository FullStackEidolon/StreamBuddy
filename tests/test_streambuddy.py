"""Regression checks; GUI and VLC are external boundaries, never launched here."""

import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from xml.sax.saxutils import escape


# Import the original script even on machines without the optional native bindings.
# Individual tests substitute only the GUI/media boundary they exercise.
gui = ModuleType("tkinter")
gui.Tk = Mock()
gui.TclError = type('TclError', (Exception,), {})
gui.filedialog = ModuleType("tkinter.filedialog")
gui.filedialog.askdirectory = Mock()
gui.filedialog.askopenfilename = Mock()
with patch.dict(sys.modules, {"vlc": ModuleType("vlc"), "tkinter": gui, "tkinter.filedialog": gui.filedialog}):
    import StreamBuddy as app


class WorkspaceTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def media(self, name):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"fixture")
        return path

    def playlist(self, locations):
        path = self.root / "queue.xspf"
        tracks = "".join(f"<track><location>{escape(location)}</location></track>" for location in locations)
        path.write_text(
            '<playlist xmlns="http://xspf.org/ns/0/"><trackList>'
            + tracks + '</trackList></playlist>', encoding="utf-8"
        )
        return path


class SetupTests(WorkspaceTest):
    def test_playlist_preserves_absolute_paths_order_and_escaped_names(self):
        first = self.media("Show #1 – café.mp4")
        second = self.media("100% done.mp4")
        path = self.playlist([first.as_uri(), second.as_uri()])
        self.assertEqual(app.queueBuilder(path), [str(first), str(second)])

    def test_relative_locations_resolve_against_playlist_directory(self):
        video = self.media("media/episode one.mp4")
        path = self.playlist(["media/episode%20one.mp4"])
        self.assertEqual(app.queueBuilder(path), [str(video)])

    def test_localhost_file_uri_is_local(self):
        video = self.media("episode.mp4")
        path = self.playlist([video.as_uri().replace("file:///", "file://localhost/")])
        self.assertEqual(app.queueBuilder(path), [str(video)])

    def test_empty_playlist_has_actionable_error(self):
        path = self.playlist([])
        with self.assertRaisesRegex(ValueError, "(?i)playlist.*(empty|no.*track|no.*video)"):
            app.queueBuilder(path)

    def test_empty_location_identifies_track(self):
        path = self.playlist([""])
        with self.assertRaisesRegex(ValueError, "(?i)track 1.*location"):
            app.queueBuilder(path)

    def test_malformed_playlist_has_actionable_error(self):
        path = self.root / "broken.xspf"
        path.write_text("<broken", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "(?i)(playlist|xml)"):
            app.queueBuilder(path)

    def test_missing_media_is_rejected_before_playback(self):
        path = self.playlist([(self.root / "missing.mp4").as_uri()])
        with self.assertRaisesRegex(ValueError, "(?i)(missing|not.*file|not.*found)"):
            app.queueBuilder(path)

    def test_remote_media_is_rejected_as_not_local(self):
        path = self.playlist(["https://example.com/episode.mp4"])
        with self.assertRaisesRegex(ValueError, "(?i)(local|scheme|unsupported)"):
            app.queueBuilder(path)

    def test_discovery_accepts_uppercase_extensions_but_not_directories(self):
        upper = self.media("a.MP4")
        lower = self.media("b.mkv")
        self.media("notes.txt")
        (self.root / "c.mp4").mkdir()
        self.assertEqual(app.get_video_files(self.root), [str(upper), str(lower)])

    def test_empty_bumper_folder_has_actionable_error(self):
        with self.assertRaisesRegex(ValueError, "(?i)(no.*video|empty|bumper)"):
            app.get_video_files(self.root)

    def test_banner_output_uses_correct_names_and_utf8(self):
        app.set_obs_text_title(None, "Café – Pilot", None, self.root)
        self.assertEqual((self.root / "last_episode.txt").read_text(encoding="utf-8"), "Welcome to the stream!")
        self.assertEqual((self.root / "current_episode.txt").read_text(encoding="utf-8"), "Café – Pilot")
        self.assertEqual((self.root / "next_episode.txt").read_text(encoding="utf-8"), "Thanks for watching!")

    def test_banner_failure_propagates_to_caller(self):
        # A directory with the target filename fails consistently even as root.
        (self.root / "current_episode.txt").mkdir()
        with self.assertRaisesRegex(ValueError, "(?i)(banner|current_episode)"):
            app.set_obs_text_title("last", "current", "next", self.root)

    def test_banner_cleanup_attempts_every_file_even_if_first_write_fails(self):
        app.set_obs_text_title('Last', 'Current', 'Next', self.root)
        (self.root / 'last_episode.txt').unlink()
        (self.root / 'last_episode.txt').mkdir()
        with self.assertRaisesRegex(ValueError, '(?i)last_episode'):
            app.set_obs_text_title('', '', '', self.root)
        self.assertEqual((self.root / 'current_episode.txt').read_text(), '')
        self.assertEqual((self.root / 'next_episode.txt').read_text(), '')

    def test_dialog_windows_are_destroyed_after_cancel(self):
        for selector, dialog_name in [(app.select_file, "askopenfilename"), (app.select_folder, "askdirectory")]:
            with self.subTest(selector=selector.__name__):
                root = Mock()
                with patch.object(app.tk, "Tk", return_value=root), patch.object(app.filedialog, dialog_name, return_value=""):
                    self.assertEqual(selector(), "")
                root.destroy.assert_called_once()

    def test_dialog_windows_are_destroyed_after_error(self):
        root = Mock()
        with patch.object(app.tk, "Tk", return_value=root), patch.object(app.filedialog, "askdirectory", side_effect=RuntimeError("dialog failed")):
            with self.assertRaises(RuntimeError):
                app.select_folder()
        root.destroy.assert_called_once()


class FakeClock:
    def __init__(self):
        self.now = 0.0
        self.interrupt = False

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        if self.interrupt:
            raise KeyboardInterrupt
        self.now += seconds
        if self.now > 120:
            raise AssertionError("Playback exceeded the test's bounded observation window")


class FakeMedia:
    def __init__(self, path):
        self.path = path
        self.released = False

    def release(self):
        self.released = True


class FakePlayer:
    def __init__(self, clock, duration=4, start_delay=0, unknown_duration=False):
        self.clock = clock
        self.duration = duration
        self.start_delay = start_delay
        self.unknown_duration = unknown_duration
        self.error_at = None
        self.stalled = False
        self.started_at = None
        self.stopped = False
        self.released = False
        self.play_result = 0
        self.stop_error = False
        self.fullscreen = None

    def set_mrl(self, path):
        self.path = path

    def set_media(self, media):
        self.path = media.path

    def set_fullscreen(self, enabled):
        self.fullscreen = enabled

    def play(self):
        self.started_at = self.clock.now
        return self.play_result

    def get_state(self):
        elapsed = self.clock.now - self.started_at
        if self.error_at is not None and elapsed >= self.error_at:
            return 'Error'
        if elapsed < self.start_delay:
            return 'Opening'
        if not self.stalled and elapsed >= self.start_delay + self.duration:
            return 'Ended'
        return 'Playing'

    def is_playing(self):
        return self.get_state() == 'Playing'

    def get_time(self):
        if self.stalled:
            return 0
        return int(max(0, self.clock.now - self.started_at - self.start_delay) * 1000)

    def get_length(self):
        return -1 if self.unknown_duration else int(self.duration * 1000)

    def stop(self):
        self.stopped = True
        if self.stop_error:
            raise OSError("stop failed")

    def release(self):
        self.released = True


class FakeInstance:
    def __init__(self, player):
        self.player = player
        self.media = None
        self.released = False

    def media_player_new(self):
        return self.player

    def media_new_path(self, path):
        self.media = FakeMedia(path)
        return self.media

    def release(self):
        self.released = True


class PlaybackTests(WorkspaceTest):
    def setUp(self):
        super().setUp()
        self.video = self.media("episode.mp4")
        self.clock = FakeClock()
        self.player = FakePlayer(self.clock)
        self.instance = FakeInstance(self.player)
        states = SimpleNamespace(**{name: name for name in ['NothingSpecial', 'Opening', 'Buffering', 'Playing', 'Paused', 'Stopped', 'Ended', 'Error']})
        self.vlc = SimpleNamespace(State=states, Instance=lambda *args: self.instance)
        for patcher in [patch.object(app, 'vlc', self.vlc), patch.object(app, 'time', self.clock)]:
            patcher.start()
            self.addCleanup(patcher.stop)

    def assert_released(self):
        self.assertTrue(self.player.stopped, 'Player must stop on every exit')
        self.assertTrue(self.player.released, 'Player must be released')
        self.assertTrue(self.instance.released, 'VLC instance must be released')
        if self.instance.media:
            self.assertTrue(self.instance.media.released, 'Media must be released')

    def test_episode_without_banner_folder_finishes_and_releases(self):
        app.play_video(str(self.video))
        self.assert_released()
        self.assertTrue(self.player.fullscreen)

    def test_test_mode_stops_after_five_seconds_of_playback(self):
        self.player.duration = 60
        self.player.start_delay = 2
        app.play_video(str(self.video), test_mode=True)
        self.assertAlmostEqual(self.clock.now, 7, delta=0.2)
        self.assertFalse(self.player.fullscreen)
        self.assert_released()

    def test_short_clip_finishes_without_waiting_full_test_window(self):
        self.player.duration = 0.2
        app.play_video(str(self.video), test_mode=True)
        self.assertLess(self.clock.now, 1)
        self.assert_released()

    def test_undecodable_media_ending_before_playback_is_an_error(self):
        self.player.duration = 0
        with self.assertRaisesRegex(ValueError, '(?i)(without.*play|no.*play|decode)'):
            app.play_video(str(self.video))
        self.assert_released()

    def test_valid_tiny_clip_can_end_between_polls(self):
        self.player.duration = 0.05
        # A clip can finish before the first state observation; duration is valid.
        with patch.object(self.player, 'get_state', return_value='Ended'):
            app.play_video(str(self.video))
        self.assert_released()

    def test_unknown_duration_does_not_block_completion(self):
        self.player.unknown_duration = True
        app.play_video(str(self.video))
        self.assertLess(self.clock.now, 5)
        self.assert_released()

    def test_startup_timeout_is_bounded_and_releases(self):
        self.player.start_delay = 999
        with self.assertRaisesRegex(ValueError, '(?i)(start|timeout)'):
            app.play_video(str(self.video))
        self.assertLessEqual(self.clock.now, 15.2)
        self.assert_released()

    def test_stalled_playback_is_bounded_and_releases(self):
        self.player.stalled = True
        with self.assertRaisesRegex(ValueError, '(?i)(stall|progress)'):
            app.play_video(str(self.video))
        self.assertLessEqual(self.clock.now, 30.2)
        self.assert_released()

    def test_vlc_error_during_playback_surfaces_immediately(self):
        self.player.duration = 60
        self.player.error_at = 1
        with self.assertRaisesRegex(ValueError, '(?i)(VLC|playback)'):
            app.play_video(str(self.video))
        self.assertLess(self.clock.now, 2)
        self.assert_released()

    def test_rejected_play_command_does_not_wait(self):
        self.player.play_result = -1
        with self.assertRaisesRegex(ValueError, '(?i)(play|start)'):
            app.play_video(str(self.video))
        self.assertEqual(self.clock.now, 0)
        self.assert_released()

    def test_bumper_text_clears_near_end(self):
        app.set_obs_text_title('Last', 'Current', 'Next', self.root)
        cleared_at = []
        original = app.set_obs_text_title
        def write(*args):
            cleared_at.append(self.clock.now)
            return original(*args)
        with patch.object(app, 'set_obs_text_title', side_effect=write):
            app.play_video(str(self.video), banner_folder_path=self.root)
        self.assertAlmostEqual(cleared_at[0], 2, delta=0.2)
        self.assertEqual((self.root / 'current_episode.txt').read_text(), '')
        self.assert_released()

    def test_interrupt_releases_resources(self):
        self.clock.interrupt = True
        with self.assertRaises(KeyboardInterrupt):
            app.play_video(str(self.video))
        self.assert_released()

    def test_cleanup_continues_if_stop_fails(self):
        self.clock.interrupt = True
        self.player.stop_error = True
        with self.assertRaises(KeyboardInterrupt):
            app.play_video(str(self.video))
        self.assert_released()


class SessionTests(WorkspaceTest):
    def setUp(self):
        super().setUp()
        self.banner = self.root / 'banners'
        self.banner.mkdir()
        self.bumpers = self.root / 'bumpers'
        self.bumpers.mkdir()
        self.media('bumpers/A.mp4')
        self.media('bumpers/B.mp4')

    def run_session(self, playlist, playback, folders=None):
        with patch.object(app, 'select_file', return_value=str(playlist)), patch.object(app, 'select_folder', side_effect=folders if folders is not None else [str(self.banner), str(self.bumpers)]), patch.object(app, 'play_video', side_effect=playback):
            return app.main(test_mode=True)

    def test_complete_queue_cycles_match_banner_titles_and_rotate_bumpers(self):
        for count in [1, 2, 3]:
            with self.subTest(count=count):
                episodes = [self.media(f'Episode{i}.mp4') for i in range(1, count + 1)]
                playlist = self.playlist([p.as_uri() for p in episodes])
                played, banners = [], []
                def playback(path, **kwargs):
                    if len(played) == 4 * count:
                        raise KeyboardInterrupt
                    played.append(Path(path).name)
                    if Path(path).parent == self.bumpers:
                        banners.append(tuple((self.banner / name).read_text() for name in ['last_episode.txt', 'current_episode.txt', 'next_episode.txt']))
                    else:
                        self.assertEqual((self.banner / 'current_episode.txt').read_text(), '')
                self.assertEqual(self.run_session(playlist, playback), 0)
                expected_episodes = [f'Episode{i}.mp4' for i in range(1, count + 1)] * 2
                self.assertEqual(played[1::2], expected_episodes)
                self.assertEqual(played[::2], ['A.mp4', 'B.mp4'] * count)
                self.assertEqual([b[1] for b in banners], [name[:-4] for name in expected_episodes])
                self.assertEqual(banners[0][0], 'Welcome to the stream!')
                self.assertEqual(banners[count][0], f'Episode{count}')
                if count == 3:
                    self.assertEqual(banners[1], ('Episode1', 'Episode2', 'Episode3'))
                self.assertEqual((self.banner / 'current_episode.txt').read_text(), '')

    def test_cancel_at_each_setup_step_exits_without_playback(self):
        playlist = self.playlist([self.media('Episode1.mp4').as_uri()])
        for selected, folders in [('', []), (str(playlist), ['']), (str(playlist), [str(self.banner), ''])]:
            with self.subTest(folders=folders), patch.object(app, 'select_file', return_value=selected), patch.object(app, 'select_folder', side_effect=folders), patch.object(app, 'play_video') as player:
                self.assertEqual(app.main(), 0)
                player.assert_not_called()

    def test_empty_playlist_does_not_start_player(self):
        playlist = self.playlist([])
        playback = Mock()
        self.assertEqual(self.run_session(playlist, playback), 1)
        playback.assert_not_called()

    def test_empty_bumper_folder_does_not_start_player(self):
        playlist = self.playlist([self.media('Episode1.mp4').as_uri()])
        empty = self.root / 'empty'
        empty.mkdir()
        playback = Mock()
        self.assertEqual(self.run_session(playlist, playback, [str(self.banner), str(empty)]), 1)
        playback.assert_not_called()

    def test_unwritable_banner_destination_does_not_start_player(self):
        playlist = self.playlist([self.media('Episode1.mp4').as_uri()])
        (self.banner / 'current_episode.txt').mkdir()
        playback = Mock()
        self.assertEqual(self.run_session(playlist, playback), 1)
        playback.assert_not_called()

    def test_playback_error_stops_session_and_clears_banners(self):
        playlist = self.playlist([self.media('Episode1.mp4').as_uri()])
        failure = getattr(app, 'StreamBuddyError', ValueError)('playback failed')
        self.assertEqual(self.run_session(playlist, Mock(side_effect=failure)), 1)
        self.assertEqual((self.banner / 'current_episode.txt').read_text(), '')

    def test_playlist_is_reloaded_only_after_complete_cycle(self):
        first, second, replacement = [self.media(name) for name in ['First.mp4', 'Second.mp4', 'Replacement.mp4']]
        playlist = self.playlist([first.as_uri(), second.as_uri()])
        played = []
        def playback(path, **kwargs):
            if Path(path).parent == self.bumpers:
                return
            played.append(Path(path).name)
            if len(played) == 1:
                self.playlist([replacement.as_uri()])
            if len(played) == 3:
                raise KeyboardInterrupt
        self.assertEqual(self.run_session(playlist, playback), 0)
        self.assertEqual(played, ['First.mp4', 'Second.mp4', 'Replacement.mp4'])

    def test_invalid_reload_stops_cleanly(self):
        playlist = self.playlist([self.media('Episode1.mp4').as_uri()])
        played = []
        def playback(path, **kwargs):
            played.append(Path(path).name)
            if len(played) > 2:
                self.fail('Invalid replacement playlist must stop the session')
            if Path(path).parent != self.bumpers:
                playlist.write_text('<broken')
        self.assertEqual(self.run_session(playlist, playback), 1)
        self.assertEqual(played, ['A.mp4', 'Episode1.mp4'])
        self.assertEqual((self.banner / 'current_episode.txt').read_text(), '')


class CommandLineTests(unittest.TestCase):
    def test_both_launchers_offer_help_without_optional_dependencies(self):
        root = Path(__file__).resolve().parents[1]
        for name in ['StreamBuddy.py', 'StreamBuddy OBSWebsocket.py']:
            with self.subTest(name=name):
                result = subprocess.run([sys.executable, '-S', str(root / name), '--help'], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('--test', result.stdout)

    def test_missing_dependencies_are_reported_without_traceback(self):
        root = Path(__file__).resolve().parents[1]
        # -S excludes site packages, so python-vlc is absent regardless of the host.
        result = subprocess.run([sys.executable, '-S', str(root / 'StreamBuddy.py')], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 1)
        self.assertIn('python-vlc', result.stderr)
        self.assertNotIn('Traceback', result.stderr)

    def test_gui_unavailable_is_an_actionable_error(self):
        with patch.object(app, 'tk', None):
            with self.assertRaisesRegex(ValueError, '(?i)(tk|gui)'):
                app.select_folder()

    def test_display_error_exits_cleanly(self):
        with patch.object(app.tk, 'Tk', side_effect=app.tk.TclError('no display')):
            self.assertEqual(app.main(), 1)


if __name__ == "__main__":
    unittest.main()
