# Build the Windows EXE

End users need neither Python nor developer tools. They run the EXE installer.
Maintainers need build tools to compile it. All NextUp code remains MIT
licensed; bundled third-party code retains its own licenses.

## Build on Windows

Install standard Python 3.13 x64, NSIS 3 and MinGW-w64 GCC. Make `python`,
`gcc` and `makensis` available in your development terminal. Then run:

```powershell
python -m pip install -r requirements.txt
python tools/build_windows.py --product nextup
```

The script fetches the official Python 3.13.15 embeddable x64 package over HTTPS
and verifies the pinned SHA-256. It installs Windows wheels into the payload
using `requirements-windows.lock` with SHA-256 verification, compiles the native
C launcher, and builds a Unicode NSIS installer. It never bundles developer
credentials, user settings or installed user data. Dependencies are included;
the user's first launch does not run pip or download Python. A pinned Microsoft
WebView2 bootstrapper is also included; setup invokes it only when WebView2 is
missing, which requires internet access. Review the official Microsoft download
and update WEBVIEW_SHA256 if Microsoft changes its bootstrapper.

Outputs in `dist/`:

- `NextUp-Setup-2.0.0-beta.39-x64.exe`: installer for users.
- Matching `.exe.sha256`: checksum, not a digital signature.
- `nextup-windows-x64.zip`: full runtime update payload, signed separately
  by `tools/release.py`. Not a standalone portable application.

To build with predownloaded dependencies, pass `--python-zip PATH` and
`--wheelhouse DIRECTORY` and optionally `--webview-setup PATH`. Checksums still apply. Updating the embedded Python
version requires updating both constants in `tools/build_windows.py` and testing
the new runtime. Update the Windows wheel lock deliberately with dependency
changes; the lock contains platform-specific wheel hashes.

On Ubuntu, install `nsis gcc-mingw-w64-x86-64-posix` and use the same build command
with a Python 3.13 environment. This cross-compiles the EXE; it does not constitute
a Windows execution test. The GitHub release workflow builds on Windows and
executes the bundled imports and silent installer before publishing.

## Audio callback checks

Windows builds run `NextUpAudio.exe --self-test` after compilation to verify the
real COM callback exposes IAgileObject, consistent IUnknown identity and IMarshal.
The release workflow repeats this check against the bundled helper. The Python
test suite also compiles `tests_native/audio_completion_test.c`, which exercises
the production callback header with deterministic COM stubs. Neither check
replaces a real Windows application-capture test. Linux cross-builds cannot run
the Windows self-test.

## Layout and behavior

`%LOCALAPPDATA%\NextUp` contains:

- `NextUp.exe`: native x64 GUI launcher; no BAT or shell invocation.
- `runtime/`: private minimal runtime for the stable launcher.
- `bootstrap.py`: stable launcher logic, readable source.
- `versions/<version>/`: source, assets, private runtime and dependencies for
  that release. The new version is preflighted before activating it.
- `userdata/`: settings, connections, queue and recognition history.
- `startup.log`: bounded startup/error log; inspect if the dashboard won't open.

The UI is hosted inside its own pywebview/WebView2 desktop window. Closing the
main window or Tools > Exit stops the service; minimizing keeps it running.
The YouTube player is a separate app window. Provider sign-in uses the system
browser. The desktop shell never falls back to opening a browser dashboard.
The installer creates desktop/Start menu shortcuts and a Windows Apps uninstall
entry, without administrator rights, PATH changes or a system Python install.
Existing NextUp userdata in this installation is preserved. Data from older products is not imported. Uninstall intentionally retains userdata,
including saved account tokens; delete it separately to erase those credentials.
Recognition applications and their dependencies are not included in this package.

Rollback uses Start menu > NextUp > Roll back last update. It can only
return to another bundled release; legacy source installs are not rollback targets.
Signed in-app updates replace whole version payloads, including dependencies.
Stable bootstrap/native launcher changes need a new EXE installation; normal
application bug fixes and per-version runtime/dependency updates do not.

## Before public distribution

Configure your publisher repository/key before building installers for your users;
see PUBLISHING.md. This delivered beta has no configured update publisher.
Test on a clean Windows 10/11 x64 machine without Python: setup, launch, audio
capture, OAuth, update, rollback and uninstall with retained data. The release
workflow includes automated Windows smoke gates, including an own-window launch and shutdown smoke test, but live services need accounts.
The EXE is not Authenticode signed. Windows may identify an unknown publisher.
Ed25519 update signatures are separate from Windows installer signing. A release
publisher can add an Authenticode signing step using their own certificate.

Upstream references:
- https://docs.python.org/3.13/using/windows.html#the-embeddable-package
- https://nsis.sourceforge.io/Docs/Chapter4.html

## Desktop dependencies and source development

The Windows lock also includes pywebview 6.2.1, Python.NET 3.1.0, clr-loader,
Bottle and proxy-tools. Python.NET supports the bundled CPython 3.13 runtime.
The proxy-tools sdist was built as an unchanged pure-Python wheel in vendor/;
its original source notices and distribution metadata are retained, with
upstream license text in vendor/PROXY-TOOLS-LICENSE.txt.
Microsoft WebView2/.NET and their licenses are separate from NextUp’s MIT code.
Use updated Windows 10/11 x64 with .NET Framework 4.6.2 or newer.

On Windows, `python -m studio.desktop` runs the desktop shell from source after
installing requirements. `python -m studio.server --no-browser` is an explicit
headless development mode. EXE entry.py uses desktop mode by default.

Upgrading from beta.2: run the beta.3 EXE once so the installer can check/install
WebView2. Only settings already in the NextUp folder are retained; no legacy data is imported. Later desktop
updates retain the same signed-update mechanism.

## Application icon

NextUp's icon is compiled into the native EXE with windres. Build tools accept
explicit paths through --cc, --windres and --makensis.

## Application audio helper

The NextUp build compiles `packaging/windows/audio_capture.c` into
`studio/native/NextUpAudio.exe` in the version payload. It uses native Windows
COM/WASAPI and needs no additional end-user install. Signed payload updates
include the helper. Source-only Windows developers can build it with MinGW-w64:

```powershell
New-Item -ItemType Directory -Force studio/native
gcc -municode -std=c11 -Os -s -static packaging/windows/audio_capture.c -o studio/native/NextUpAudio.exe -lole32 -luuid -luser32 -liphlpapi -lws2_32
```

Application capture requires build 20348 or later. The rest of NextUp and
animated widgets remain available when that capture API is unsupported.
