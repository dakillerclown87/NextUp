"""Stable per-user launcher, dependency isolation and rollback. Python 3.13."""

import json, os, shutil, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HOME = Path(
    os.environ.get(
        "NEXTUP_HOME",
        Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share"))
        / "NextUp",
    )
)


def save(path, value):
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(value), encoding="utf-8")
    os.replace(tmp, path)


def version_name(value):
    import re

    if not re.fullmatch(r"\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?", value):
        raise ValueError("Invalid installed version.")
    return value


def runtime(version):
    folder = HOME / "versions" / version_name(version)
    bundled = folder / "runtime/python.exe"
    if bundled.exists():
        if not (folder / ".ready").exists():
            subprocess.run([str(bundled), str(folder / "entry.py"), "--preflight"],
                           cwd=folder, check=True, **output_options())
            (folder / ".ready").touch()
        return folder, bundled
    if os.environ.get("NEXTUP_BUNDLED") == "1":
        raise ValueError("This version has no bundled runtime. Install the Windows EXE release.")
    venv = folder / ".venv"
    exe = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not exe.exists():
        subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    if not (folder / ".ready").exists():
        subprocess.run(
            [
                str(exe),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--only-binary=:all:",
                "-r",
                "requirements.txt",
            ],
            cwd=folder,
            check=True,
        )
        subprocess.run([str(exe), "-m", "pip", "check"], cwd=folder, check=True)
        subprocess.run(
            [
                str(exe),
                "-c",
                "import aiohttp,cryptography; import studio.server",
            ],
            cwd=folder,
            check=True,
        )
        (folder / ".ready").touch()
    return folder, exe


def output_options():
    if os.environ.get("NEXTUP_BUNDLED") == "1":
        return {"stdout": sys.stdout, "stderr": sys.stderr,
                "creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    return {}


def install():
    from studio import __version__

    HOME.mkdir(parents=True, exist_ok=True)
    dest = HOME / "versions" / __version__
    if not dest.exists():
        shutil.copytree(
            ROOT,
            dest,
            ignore=shutil.ignore_patterns(
                ".git",
                ".venv*",
                "__pycache__",
                "*.pyc",
                "config.json",
                "data",
                "userdata",
                "dist",
                "build",
            ),
        )
    data = HOME / "userdata"
    data.mkdir(exist_ok=True)
    runtime(__version__)
    if not (HOME / "current.json").exists():
        save(HOME / "current.json", {"version": __version__})
    shutil.copy2(ROOT / "bootstrap.py", HOME / "bootstrap.py")
    (HOME / "NextUp.bat").write_text(
        '@echo off\ncd /d "%~dp0"\npy -3.13 bootstrap.py\nif errorlevel 1 pause\n',
        encoding="utf-8",
    )
    if os.name == "nt":
        script = '$s=(New-Object -ComObject WScript.Shell).CreateShortcut([IO.Path]::Combine([Environment]::GetFolderPath("Desktop"),"NextUp.lnk"));$s.TargetPath=$env:NEXTUP_SHORTCUT_TARGET;$s.WorkingDirectory=$env:NEXTUP_SHORTCUT_DIR;$s.Save()'
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            env={
                **os.environ,
                "NEXTUP_SHORTCUT_TARGET": str(HOME / "NextUp.bat"),
                "NEXTUP_SHORTCUT_DIR": str(HOME),
            },
            check=False,
        )
    print("Installed. Use the NextUp desktop shortcut or", HOME / "NextUp.bat")


def main():
    import struct, sysconfig

    if struct.calcsize("P") != 8 or sysconfig.get_config_var("Py_GIL_DISABLED"):
        raise ValueError(
            "Use standard 64-bit Python; free-threaded builds are not supported."
        )
    if sys.version_info[:2] != (3, 13):
        raise ValueError(
            "Install standard 64-bit Python 3.13 with the Python launcher first."
        )
    if "--install" in sys.argv:
        install()
        return
    if not (HOME / "current.json").exists():
        install()
    current = json.loads((HOME / "current.json").read_text())["version"]
    if "--rollback" in sys.argv:
        previous = json.loads((HOME / "previous.json").read_text())["version"]
        save(HOME / "current.json", {"version": previous})
        save(HOME / "previous.json", {"version": current})
        current = previous
    pending = HOME / "pending.json"
    if pending.exists():
        candidate = json.loads(pending.read_text())["version"]
        try:
            print("Preparing verified update. Your settings and history will be kept.")
            runtime(candidate)
            save(HOME / "previous.json", {"version": current})
            save(HOME / "current.json", {"version": candidate})
            current = candidate
        except Exception:
            print(
                "Update preparation failed. Starting the previous version. Use Diagnostics to check the failure."
            )
        pending.unlink()
    folder, exe = runtime(current)
    env = {
        **os.environ,
        "NEXTUP_HOME": str(HOME),
        "NEXTUP_USERDATA": str(HOME / "userdata"),
    }
    command = ([str(exe), str(folder / "entry.py")] if (folder / "runtime/python.exe").exists()
               else [str(exe), "-m", "studio.desktop" if os.name == "nt" else "studio.server"])
    code = subprocess.call(command, cwd=folder, env=env, **output_options())
    if code:
        raise ValueError("The application exited with an error. Check startup.log.")
    raise SystemExit(code)


if __name__ == "__main__":
    # pythonw has no stdout/stderr; retain startup diagnostics without a console.
    log = None
    if os.environ.get("NEXTUP_BUNDLED") == "1":
        HOME.mkdir(parents=True, exist_ok=True)
        path = HOME / "startup.log"
        if path.exists() and path.stat().st_size > 2_000_000:
            os.replace(path, HOME / "startup.previous.log")
        log = path.open("a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stderr = log
    try:
        main()
    except Exception as e:
        print(os.environ.get("NEXTUP_APP_NAME", "NextUp") + " could not start:", str(e))
        if os.name == "nt" and log is not None:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,
                "The app could not start. Check startup.log in its installation folder.",
                os.environ.get("NEXTUP_APP_NAME", "NextUp"), 0x10)
        raise SystemExit(1)
