"""Build a self-contained Windows installer on Windows or Linux. MIT License."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studio import __version__
from tools.release import files

PYTHON_VERSION = "3.13.15"
PYTHON_SHA256 = "d1f04d990aee1253d8569e8e5104e30fa9f5fa830899f14843448872d936a2cf"
URL = f"https://www.python.org/ftp/python/{PYTHON_VERSION}/python-{PYTHON_VERSION}-embed-amd64.zip"
# Resolved from Microsoft\'s Evergreen link; pin this exact artifact for repeatable builds.
WEBVIEW_URL = "https://msedge.sf.dl.delivery.mp.microsoft.com/filestreamingservice/files/a3af1bf0-d324-4cfe-b9bf-0b020a73ddfb/MicrosoftEdgeWebview2Setup.exe"
WEBVIEW_SHA256 = "9b5ca0a259e6fc9b57230089258bb2ee1de74a9ed52f88d06b4ac354a8a68c70"


def check_runtime(data):
    if hashlib.sha256(data).hexdigest() != PYTHON_SHA256:
        raise ValueError("Python runtime checksum mismatch")


def run(args, **kwargs):
    subprocess.run([str(x) for x in args], cwd=ROOT, check=True, **kwargs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", choices=["nextup"], default="nextup")
    ap.add_argument("--windres", default="windres" if os.name == "nt" else "x86_64-w64-mingw32-windres")
    ap.add_argument("--python-zip", type=Path)
    ap.add_argument("--wheelhouse", type=Path)
    ap.add_argument("--webview-setup", type=Path)
    ap.add_argument("--cc", default="gcc" if os.name == "nt" else "x86_64-w64-mingw32-gcc")
    ap.add_argument("--makensis", default="makensis")
    a = ap.parse_args()
    from tools.audit_distribution import audit
    audit(list(files()))
    appname = "NextUp"
    build, dist = ROOT / ("build/windows-" + a.product), ROOT / "dist"
    if build.exists():
        shutil.rmtree(build)
    build.mkdir(parents=True)
    dist.mkdir(exist_ok=True)
    webview = a.webview_setup.read_bytes() if a.webview_setup else urllib.request.urlopen(WEBVIEW_URL, timeout=120).read()
    if hashlib.sha256(webview).hexdigest() != WEBVIEW_SHA256:
        raise ValueError("WebView2 bootstrapper checksum changed. Review the official Microsoft download and update the pin.")
    webview_path = build / "MicrosoftEdgeWebview2Setup.exe"
    webview_path.write_bytes(webview)
    if os.name == "nt":
        # In addition to the byte pin, Windows must trust Microsoft's signature.
        script = """
$ErrorActionPreference = 'Stop'
$sig = Get-AuthenticodeSignature -LiteralPath $env:NEXTUP_WEBVIEW_SETUP
if ($sig.Status -ne 'Valid' -or $sig.SignerCertificate.Subject -notmatch '(^|, )CN=Microsoft Corporation(,|$)') {
    throw "WebView2 must have a valid Microsoft Corporation signature: $($sig.Status)"
}
Write-Output "Verified Microsoft WebView2 signature: $($sig.SignerCertificate.Subject)"
"""
        env = dict(os.environ, NEXTUP_WEBVIEW_SETUP=str(webview_path.resolve()))
        run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script], env=env)
    data = a.python_zip.read_bytes() if a.python_zip else urllib.request.urlopen(URL, timeout=120).read()
    check_runtime(data)
    archive = build / "python.zip"
    archive.write_bytes(data)
    base = build / "runtime"
    with zipfile.ZipFile(archive) as z:
        z.extractall(base)
    # Isolated interpreter: local dependencies and stdlib only. No PATH/user site.
    (base / "python313._pth").write_text("python313.zip\n.\nLib/site-packages\n", encoding="utf-8")
    app = build / "app"
    app.mkdir()
    for source, rel in files():
        target = app / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    shutil.copy2(ROOT / "packaging/windows/entry.py", app / "entry.py")
    shutil.copytree(base, app / "runtime")
    site = app / "runtime/Lib/site-packages"
    command = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check",
               "--only-binary=:all:", "--platform", "win_amd64", "--python-version", "3.13",
               "--implementation", "cp", "--abi", "cp313", "--no-compile",
               "--target", site, "--require-hashes", "-r",
               "requirements-windows.lock"]
    if a.wheelhouse:
        command += ["--no-index", "--find-links", a.wheelhouse.resolve()]
    run(command)
    # Wheels contain their upstream licenses. Include an inventory beside them.
    dependencies = []
    for info in sorted(site.glob("*.dist-info")):
        dependencies.append(info.name)
        (info / "direct_url.json").unlink(missing_ok=True)
    (app / "BUNDLED-DEPENDENCIES.txt").write_text(
        "Python " + PYTHON_VERSION + " (runtime/LICENSE.txt)\n"
        + "Dependency licenses and notices: runtime/Lib/site-packages/*.dist-info\n\n"
        + "\n".join(dependencies) + "\n", encoding="utf-8")
    (app / "bundle.json").write_text(json.dumps({"format": 1, "platform": "windows-x64",
        "python": PYTHON_VERSION, "version": __version__, "desktop": "webview2", "product": a.product}), encoding="utf-8")
    if a.product == "nextup":
        native = app / "studio/native"
        native.mkdir(parents=True, exist_ok=True)
        run([a.cc, "-municode", "-std=c11", "-Os", "-s", "-static",
             ROOT / "packaging/windows/audio_capture.c", "-o", native / "NextUpAudio.exe",
             "-lole32", "-luuid", "-luser32", "-liphlpapi", "-lws2_32"])
        if os.name == "nt":
            run([native / "NextUpAudio.exe", "--self-test"])
    resources = []
    if a.product == "nextup":
        rc = build / "icon.rc"
        rc.write_text('1 ICON "' + (ROOT / 'studio/static/nextup.ico').as_posix() + '"\n')
        obj = build / "icon.o"
        run([a.windres, "--preprocessor", a.cc, "--preprocessor-arg=-E", "--preprocessor-arg=-xc", "--preprocessor-arg=-DRC_INVOKED", "-i", rc, "-o", obj])
        resources = [obj]
    mutex = "NextUpApp"
    run([a.cc, "-municode", "-mwindows", "-Os", "-s", "-static",
         '-DAPP_NAME=L"'+appname+'"', '-DAPP_MUTEX=L"Local\\\\'+mutex+'"',
         ROOT / "packaging/windows/launcher.c", *resources, "-o", build / (appname+".exe"), "-luser32"])
    run([sys.executable, ROOT / "tools/audit_distribution.py", "--payload", app])
    update = dist / "nextup-windows-x64.zip"
    with update.open("w+b") as stream:
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
            for p in sorted(app.rglob("*")):
                if p.is_file():
                    z.write(p, p.relative_to(app).as_posix())
        stream.flush()
        os.fsync(stream.fileno())
    with zipfile.ZipFile(update) as z:
        if z.testzip() is not None:
            raise ValueError("Runtime update archive failed verification")
    prefix = "/" if os.name == "nt" else "-"
    exe = dist / f"{appname}-Setup-{__version__}-x64.exe"
    run([a.makensis, f"{prefix}DAPPNAME={appname}", f"{prefix}DMUTEX={mutex}",
         f"{prefix}DINSTALLFOLDER={'NextUp'}",
         f"{prefix}DREGKEY={'NextUp'}",
         f"{prefix}DVERSION={__version__}", f"{prefix}DSOURCE={ROOT}",
         f"{prefix}DPAYLOAD={build}", f"{prefix}DOUTPUT={exe}", ROOT / "packaging/windows/installer.nsi"])
    (dist / (exe.name + ".sha256")).write_text(hashlib.sha256(exe.read_bytes()).hexdigest() + "  " + exe.name + "\n")
    print("Built", exe)


if __name__ == "__main__":
    main()
