"""Windows release gate: own-window launch, service availability, and clean exit."""
import ctypes
import argparse
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import time
import urllib.request


def main():
    if os.name != "nt":
        raise SystemExit("This smoke test needs Windows.")
    parser=argparse.ArgumentParser();parser.add_argument("--product",choices=["nextup"],default="nextup");args=parser.parse_args()
    name="NextUp"
    port=8888
    user = ctypes.windll.user32
    user.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user.FindWindowW.restype = wintypes.HWND
    user.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    root = Path(os.environ["LOCALAPPDATA"]) / "NextUp"
    p = subprocess.Popen([str(root / (name+".exe"))], cwd=root)
    window = None
    try:
        for _ in range(60):
            if p.poll() is not None:
                raise RuntimeError("NextUp exited before creating its window.")
            window = user.FindWindowW(None, name)
            if window:
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1) as r:
                        if name.encode() in r.read():
                            break
                except OSError:
                    pass
            time.sleep(1)
        else:
            raise RuntimeError("Desktop window/service did not become ready.")
        user.PostMessageW(window, 0x0010, 0, 0)  # WM_CLOSE is a normal user close.
        if p.wait(timeout=55) != 0:
            raise RuntimeError("Desktop application did not exit cleanly.")
        print("Desktop window opened, service responded, closing window stopped the app.")
    finally:
        if p.poll() is None:
            # Cleanup only this smoke-test process tree on a failed CI run.
            subprocess.run(["taskkill", "/PID", str(p.pid), "/T", "/F"], check=False)


if __name__ == "__main__":
    main()
