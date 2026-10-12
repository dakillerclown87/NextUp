"""Installer activation: preflight before changing current version; retain data."""
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

root = Path(__file__).resolve().parent
sys.path.insert(0, str(root))
import bootstrap


def activate(version):
    bootstrap.HOME = root
    bootstrap.version_name(version)
    # Legacy source launches also hold this lock; native launches hold a mutex.
    folder = root / "versions" / version
    sys.path.insert(0, str(folder))
    from studio.instance import InstanceLock

    with InstanceLock(root):
        result = subprocess.run(
            [str(folder / "runtime/python.exe"), str(folder / "entry.py"), "--preflight"],
            cwd=folder, capture_output=True, text=True, errors="replace",
        )
        details = (result.stdout or "") + (result.stderr or "")
        (root / "install-diagnostics.txt").write_text(details, encoding="utf-8")
        if details:
            print(details, flush=True)
        if result.returncode:
            raise RuntimeError(f"Component check failed (exit {result.returncode}). See install-diagnostics.txt for the exact error.")
        data = root / "userdata"
        data.mkdir(exist_ok=True)
        current = root / "current.json"
        if current.exists():
            previous = json.loads(current.read_text())
            if previous["version"] != version and (root / "versions" / bootstrap.version_name(previous["version"]) / "runtime/python.exe").exists():
                bootstrap.save(root / "previous.json", previous)
            elif previous["version"] != version:
                (root / "previous.json").unlink(missing_ok=True)
        bootstrap.save(current, {"version": version})
        (root / "pending.json").unlink(missing_ok=True)
        (folder / ".ready").touch()
        removed = bootstrap.cleanup_versions()
        if removed:
            print("Removed older app versions: " + ", ".join(removed), flush=True)


class BotRunningError(RuntimeError):
    pass


def check_instance():
    import errno
    import msvcrt
    with (root / "instance.lock").open("a+b") as f:
        if f.tell() == 0:
            f.write(b"0")
            f.flush()
        f.seek(0)
        try:
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as e:
            if e.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                raise BotRunningError("Another NextUp process holds the application lock.") from e
            raise
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    print("NextUp instance check passed.", flush=True)


if __name__ == "__main__":
    os.environ["NEXTUP_BUNDLED"] = "1"
    try:
        if sys.argv[1] == "--check":
            check_instance()
        else:
            activate(sys.argv[1])
    except Exception as e:
        try:
            with (root / "install-diagnostics.txt").open("a", encoding="utf-8") as log:
                log.write("\n" + traceback.format_exc())
        except OSError:
            pass
        print("Installation check failed:", e, flush=True)
        sys.exit(10 if isinstance(e, BotRunningError) else 1)
