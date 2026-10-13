"""NextUp entry point for the isolated bundled runtime."""
import os, runpy, sys, time
from pathlib import Path
started = time.perf_counter()
root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))
if "--preflight" in sys.argv:
    import aiohttp, cryptography, sqlite3
    from PIL import Image
    # Exercise the native decoder too; importing the package alone is insufficient.
    Image.new("RGB", (1, 1)).resize((2, 2))
    import studio.server
    import webview, pythonnet
    if os.name == "nt":
        import clr
        from webview.platforms.winforms import _is_chromium
        if not _is_chromium():
            raise RuntimeError("Microsoft WebView2 Runtime is missing. Run the NextUp installer again.")
    print(f"[startup] NextUp component check completed in {time.perf_counter()-started:.2f}s")
else:
    os.chdir(root)
    runpy.run_module("studio.server" if "--no-browser" in sys.argv else "studio.desktop", run_name="__main__")
