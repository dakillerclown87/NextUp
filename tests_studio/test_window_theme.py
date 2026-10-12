import ctypes
import unittest
from unittest.mock import Mock, patch
from studio.window_theme import caption_attributes, apply_titlebar
from studio.desktop import Desktop
from tests_studio.test_desktop import fake_window


class WindowThemeTests(unittest.TestCase):
    def test_native_colors_follow_light_dark_custom_and_reset(self):
        dark = caption_attributes({})
        self.assertEqual(dark[35], 0x1b140d)  # COLORREF is BGR, not RGB.
        self.assertEqual(dark[20], 1)
        self.assertEqual(caption_attributes({'theme': 'light'})[35], 0xf4f1ed)
        self.assertEqual(caption_attributes({'theme': 'light'})[20], 0)
        custom = caption_attributes({'theme': 'light', 'theme_colors': {'bg':'#112233','text':'#abcdef'}})
        self.assertEqual(custom[35], 0x332211)
        self.assertEqual(custom[36], 0xefcdab)
        self.assertEqual(custom[20], 1)
        self.assertEqual(caption_attributes({'theme_colors':{}}), dark)

    def test_dwm_uses_full_64bit_handle_and_colorrefs(self):
        window = Mock()
        handle = 0x123456789
        window.native.Handle.ToInt64.return_value = handle
        calls = []
        def capture(hwnd, attribute, pointer, size):
            calls.append((hwnd.value, attribute, pointer._obj.value, size))
            return 0
        dll = Mock()
        dll.DwmSetWindowAttribute.side_effect = capture
        with patch('studio.window_theme.os.name', 'nt'), patch.object(ctypes, 'WinDLL', return_value=dll, create=True):
            self.assertTrue(apply_titlebar(window, {}))
        self.assertEqual({a:v for h,a,v,n in calls}, caption_attributes({}))
        self.assertTrue(all(h==handle and n==4 for h,a,v,n in calls))

    def test_unsupported_or_closed_window_retains_system_caption(self):
        window = Mock()
        window.native.Handle.ToInt64.side_effect = RuntimeError('disposed')
        with patch('studio.window_theme.os.name', 'nt'):
            self.assertFalse(apply_titlebar(window, {}))

    def test_all_open_windows_receive_saved_theme(self):
        webview = Mock()
        webview.create_window.side_effect = lambda *a, **k: fake_window()
        desktop = Desktop(webview)
        desktop.studio = Mock(admin='key')
        desktop.studio.settings.value = {'theme':'light','theme_colors':{'bg':'#f0e0d0'}}
        desktop.open_player()
        desktop.open_popout()
        with patch('studio.desktop.apply_titlebar') as paint:
            desktop.window.events.shown.fire()
            self.assertEqual(paint.call_count,3)
            for window in (desktop.window,desktop.player,desktop.popout):
                paint.assert_any_call(window,desktop.studio.settings.value)
