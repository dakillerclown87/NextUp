"""Run unreleased source with an installed runtime and isolated test settings.

This is not an installer. Original application files, queue and settings are
never replaced. Playback controls in the test window do control live Spotify.
"""
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys


def installed_runtime(home):
    version = json.loads((home/'current.json').read_text(encoding='utf-8'))['version']
    if not re.fullmatch(r'\d+\.\d+\.\d+(?:-(?:alpha|beta|rc)\.\d+)?', version):
        raise ValueError('Invalid installed version.')
    runtime = home/'versions'/version/'runtime/python.exe'
    if not runtime.is_file():
        raise ValueError('Could not find the existing installed NextUp runtime.')
    return runtime


def prepare_data(home, test_home):
    """Copy settings/login once. Do not clone live queues or modify originals."""
    data = test_home/'userdata'
    data.mkdir(parents=True, exist_ok=True)
    accounts = data/'accounts.json'
    settings_path = data/'studio.json'
    # Stage without keeping any account data inside the downloaded source ZIP.
    if not accounts.exists():
        shutil.copyfile(home/'userdata/accounts.json', accounts)
        accounts.chmod(0o600)
    if not settings_path.exists():
        settings = json.loads((home/'userdata/studio.json').read_text(encoding='utf-8'))
        settings.update(spotify_follow_current_playlist=True, fallback_enabled=False,
                        provider_mode='mixed', widget_audio_mode='animation')
        # Private file writer is not imported until NEXTUP_HOME is set.
        with settings_path.open('x', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)
        settings_path.chmod(0o600)


def check_ports():
    for port in (8888, 8889):
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(('127.0.0.1', port)) == 0:
                raise ValueError('Close the regular NextUp window before starting the live test.')


def child(home, root, test_home):
    os.environ['NEXTUP_HOME'] = str(test_home)
    os.environ['NEXTUP_APP_NAME'] = 'NextUp - Playback Test (unreleased)'
    os.environ['NEXTUP_BUILD_LABEL'] = 'unreleased-recording-identity-test'
    sys.path.insert(0, str(root/'source'))
    os.chdir(root/'source')
    from studio.instance import InstanceLock
    # Prevent a regular NextUp instance from starting during the test.
    with InstanceLock(home):
        check_ports()
        prepare_data(home, test_home)
        from studio.desktop import main as desktop_main
        desktop_main()


def main():
    root = Path(__file__).resolve().parent
    args = sys.argv[1:]
    is_child = bool(args and args[0] == '--child')
    if is_child:
        args.pop(0)
    home = Path(args[0]) if args else Path(os.environ['LOCALAPPDATA'])/'NextUp'
    test_home = Path(os.environ['LOCALAPPDATA'])/'NextUp-Playback-Test'
    try:
        check_ports()
        if is_child:
            child(home, root, test_home)
            return 0
        runtime = installed_runtime(home)
        print('Opening the live playback test. No installed files will be replaced.')
        print('The test has its own settings and queue. Its controls operate live Spotify.')
        return subprocess.call([str(runtime), str(Path(__file__).resolve()), '--child', str(home)], cwd=root)
    except Exception as e:
        # Avoid raw settings/account objects and HTTP exception contents.
        if isinstance(e, ValueError) and str(e) in (
            'Invalid installed version.',
            'Could not find the existing installed NextUp runtime.',
            'Close the regular NextUp window before starting the live test.',
            'NextUp is already running. Use its existing window or stop it first.',
        ):
            print(str(e))
        else:
            print('The test could not start ('+type(e).__name__+'). No installed files were replaced.')
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
