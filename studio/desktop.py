"""Own-window desktop host. The application service never opens a browser here."""

import asyncio
import base64
import time
import contextlib
import os
import threading
from .settings import HOME, ROOT
from . import __version__
from .window_theme import apply_titlebar

def loading_page():
    icon = base64.b64encode((ROOT / "studio/static/nextup-icon.png").read_bytes()).decode("ascii")
    return f"""<!doctype html><html><body style="margin:0;background:#0d141b;color:#f4f6f8;
font:16px 'Segoe UI',sans-serif;display:grid;place-items:center;height:100vh">
<div style="text-align:center"><img src="data:image/png;base64,{icon}" alt="NextUp" width="108" height="108">
<p>Opening your workspace…</p><small style="color:#aab3bc">Loading your saved settings and queue</small></div>
</body></html>"""



class Desktop:
    def __init__(self, webview):
        self.webview = webview
        self.window = webview.create_window(
            os.environ.get("NEXTUP_APP_NAME", "NextUp"), html=loading_page(), width=820, height=600,
            min_size=(640, 460), background_color="#080f19", text_select=True,
        )
        self.window.events.closed += self.request_stop
        self.popout = None
        self.player = None
        self.loop = None
        self.studio = None
        self.closing = threading.Event()
        self.finished = threading.Event()
        self.thread = None
        self.error = None
        self._player_lock = threading.Lock()
        self.window.events.shown += self.refresh_window_theme

    def ready(self, url, studio):
        self.loop = asyncio.get_running_loop()
        self.studio = studio
        if self.closing.is_set():
            studio.stop_event.set()
        else:
            self.set_compact(studio.settings.value.get("compact_mode", True))
            self.refresh_window_theme()
            self.window.load_url(url)

    def refresh_window_theme(self):
        settings = self.studio.settings.value if self.studio is not None else {}
        for window in (self.window, self.player, self.popout):
            if window is not None:
                apply_titlebar(window, settings)

    def set_compact(self, enabled):
        self.window.restore()
        self.window.resize(*( (820, 600) if enabled else (1100, 760) ))

    def request_stop(self):
        self.closing.set()
        if self.loop is not None and self.studio is not None:
            with contextlib.suppress(RuntimeError):
                self.loop.call_soon_threadsafe(self.studio.stop_event.set)

    def open_player(self):
        if self.closing.is_set() or self.studio is None:
            raise ValueError("NextUp is closing or still starting.")
        with self._player_lock:
            if self.player is not None:
                self.player.restore()
                self.player.show()
                return
            # No arbitrary URL/JS bridge is exposed to the page. The server owns the key.
            player = self.webview.create_window(
                "NextUp · YouTube", url="http://127.0.0.1:8888/player#" + self.studio.admin,
                width=900, height=650, min_size=(500, 400), background_color="#080f19",
            )
            self.player = player
            player.events.shown += self.refresh_window_theme

            def closed():
                with self._player_lock:
                    if self.player is player:
                        self.player = None
            player.events.closed += closed

    def open_popout(self):
        if self.closing.is_set() or self.studio is None:
            raise ValueError("NextUp is still starting or closing.")
        with self._player_lock:
            if self.popout is not None:
                self.popout.restore()
                self.popout.show()
                return
            window = self.webview.create_window("NextUp · Listening room",
                url="http://127.0.0.1:8888/popout#" + self.studio.admin,
                width=960, height=680, min_size=(650, 450), background_color="#080f19")
            self.popout = window
            window.events.shown += self.refresh_window_theme
            def closed():
                with self._player_lock:
                    if self.popout is window:
                        self.popout = None
            window.events.closed += closed

    def serve(self):
        from .server import run
        try:
            asyncio.run(run(open_browser=False, on_ready=self.ready, desktop=self))
        except Exception as e:
            self.error = e
        finally:
            self.closing.set()
            # Cleanup (pause/stop bot/save state) finishes before the player closes.
            for window in (self.player, self.popout, self.window):
                if window is not None:
                    with contextlib.suppress(Exception):
                        window.destroy()
            self.finished.set()

    def start_service(self):
        if self.closing.is_set():
            self.finished.set()
            return
        self.thread = threading.Thread(target=self.serve, name="NextUp-service", daemon=True)
        self.thread.start()

    def run(self):
        try:
            self.webview.start(
                self.start_service, gui="edgechromium", debug=False,
                icon=str(ROOT / "studio/static/nextup.ico"),
                private_mode=True, storage_path=str(HOME / "webview"),
            )
        finally:
            self.request_stop()
            if self.thread is not None:
                self.thread.join(timeout=40)
                if self.thread.is_alive():
                    raise RuntimeError("NextUp shutdown timed out. Restart before using playback.")
        if self.error is not None:
            raise self.error


def main():
    started = time.perf_counter()
    import webview
    if os.name == "nt":
        from webview.platforms.winforms import _is_chromium
        if not _is_chromium():
            raise RuntimeError("Microsoft WebView2 is required. Run the NextUp EXE installer again.")
    # The UI exposes no Python API bridge; privileged requests keep the existing
    # per-process authorization key and localhost origin validation.
    webview.settings["ALLOW_FILE_URLS"] = False
    webview.settings["ALLOW_DOWNLOADS"] = True  # diagnostic export uses a save dialog
    webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = True
    print(f"[startup] Desktop runtime ready in {time.perf_counter()-started:.2f}s")
    Desktop(webview).run()


if __name__ == "__main__":
    main()
