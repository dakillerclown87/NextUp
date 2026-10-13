import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from studio.desktop import Desktop


class Event:
    def __init__(self):
        self.callbacks = []

    def __iadd__(self, callback):
        self.callbacks.append(callback)
        return self

    def fire(self):
        for callback in self.callbacks:
            callback()


def fake_window():
    window = Mock()
    window.events.closed = Event()
    window.events.shown = Event()
    return window


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.webview = Mock()
        self.webview.create_window.side_effect = lambda *a, **k: fake_window()
        self.app = Desktop(self.webview)

    def test_main_window_uses_edge_without_browser_fallback(self):
        with patch('webbrowser.open') as browser:
            self.app.run()
        self.assertEqual(self.webview.start.call_args.kwargs['gui'], 'edgechromium')
        browser.assert_not_called()
        self.assertTrue(self.app.closing.is_set())

    def test_compact_control_restores_and_resizes_native_window(self):
        from studio import __version__
        initial = self.webview.create_window.call_args
        self.assertEqual(initial.args[0], "NextUp")
        self.assertEqual((initial.kwargs['width'], initial.kwargs['height']), (820, 600))
        self.app.set_compact(True)
        self.app.window.restore.assert_called_once()
        self.app.window.resize.assert_called_once_with(820, 600)
        self.app.set_compact(False)
        self.app.window.resize.assert_called_with(1100, 760)

    def test_native_window_failure_does_not_open_browser(self):
        self.webview.start.side_effect = RuntimeError('missing WebView2')
        with patch('webbrowser.open') as browser:
            with self.assertRaisesRegex(RuntimeError, 'WebView2'):
                self.app.run()
        browser.assert_not_called()

    def test_closing_main_window_signals_backend(self):
        self.app.loop = Mock()
        self.app.studio = Mock()
        self.app.window.events.closed.fire()
        self.assertTrue(self.app.closing.is_set())
        self.app.loop.call_soon_threadsafe.assert_called_once_with(self.app.studio.stop_event.set)

    def test_player_reused_and_recreated_after_close(self):
        self.app.studio = Mock(admin='private-key')
        self.app.open_player()
        player = self.app.player
        self.assertEqual(self.webview.create_window.call_args.kwargs['url'],
                         'http://127.0.0.1:8888/player#private-key')
        self.app.open_player()
        player.restore.assert_called_once()
        self.assertEqual(self.webview.create_window.call_count, 2)
        player.events.closed.fire()
        self.assertIsNone(self.app.player)
        self.app.open_player()
        self.assertEqual(self.webview.create_window.call_count, 3)

    def test_player_refuses_after_shutdown(self):
        self.app.request_stop()
        with self.assertRaises(ValueError):
            self.app.open_player()


class ReadyTests(unittest.IsolatedAsyncioTestCase):
    async def test_close_before_server_ready_never_loads_window(self):
        wv = Mock()
        wv.create_window.return_value = fake_window()
        app = Desktop(wv)
        app.request_stop()
        studio = Mock(stop_event=asyncio.Event())
        app.ready('http://127.0.0.1:8888/#key', studio)
        self.assertTrue(studio.stop_event.is_set())
        app.window.load_url.assert_not_called()

    async def test_real_server_ready_callback_skips_browser_and_cleans_up(self):
        import studio.server as server
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            original = server.Studio
            holder = []

            def ready(url, service):
                holder.append(service)
                self.assertTrue(url.startswith('http://127.0.0.1:8888/#'))
                self.assertTrue(service.state()['desktop'])
                service.stop_event.set()

            with patch.object(server, 'HOME', home), patch.object(server, 'Studio', side_effect=lambda s: original(s, home)), patch.object(server.webbrowser, 'open') as browser:
                await asyncio.wait_for(server.run(open_browser=False, on_ready=ready, desktop=Mock()), 10)
            browser.assert_not_called()
            self.assertEqual(len(holder), 1)
            with self.assertRaises(Exception):
                holder[0].queue.db.execute('SELECT 1')
