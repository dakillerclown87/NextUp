"""Read-only Spotify evidence collector for an existing NextUp installation.

Uses only Python's standard library and the existing, unexpired login. No
token refresh, playback command, installation, or settings write occurs.
"""
import base64
import ctypes
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request

IDS = ('21JvBMXPGJ6rpvHacAFWUO', '6kabsWWWUCKCXbBSPt4Cae')


class ProbeError(Exception):
    pass


def saved_token(home):
    payload = json.loads((home / 'userdata/accounts.json').read_text(encoding='utf-8'))
    if 'dpapi' in payload:
        from ctypes import wintypes
        class Blob(ctypes.Structure):
            _fields_ = [('length', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]
        data = base64.b64decode(payload['dpapi'])
        buffer = ctypes.create_string_buffer(data)
        source = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
        destination = Blob()
        decrypt = ctypes.windll.crypt32.CryptUnprotectData
        decrypt.argtypes = [ctypes.POINTER(Blob), ctypes.c_void_p, ctypes.c_void_p,
                           ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
        decrypt.restype = wintypes.BOOL
        free = ctypes.windll.kernel32.LocalFree
        free.argtypes = [ctypes.c_void_p]
        free.restype = ctypes.c_void_p
        if not decrypt(ctypes.byref(source), None, None, None, None, 1, ctypes.byref(destination)):
            raise ProbeError('Windows could not read the existing login. Run under the same Windows account as NextUp.')
        try:
            payload = json.loads(ctypes.string_at(destination.data, destination.length))
        finally:
            free(destination.data)
    spotify = payload.get('spotify') or {}
    if not spotify.get('access_token') or spotify.get('expires_at', 0) <= time.time()+30:
        raise ProbeError('The saved Spotify login is expired or missing. Open NextUp with Spotify connected, then run this check again.')
    return spotify['access_token']


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def spotify_get(token, path):
    # Explicit allowlist. This tool cannot call any playback-control endpoint.
    if path != 'me/player' and not re.fullmatch(r'tracks/[A-Za-z0-9]{22}\?market=from_token', path):
        raise ProbeError('Unsupported diagnostic endpoint.')
    req = urllib.request.Request('https://api.spotify.com/v1/'+path,
                                 headers={'Authorization': 'Bearer '+token}, method='GET')
    try:
        with urllib.request.build_opener(NoRedirect()).open(req, timeout=15) as response:
            return json.loads(response.read()) if response.status != 204 else {}
    except urllib.error.HTTPError as e:
        raise ProbeError('Spotify returned HTTP '+str(e.code)+'. No playback commands were sent.') from None
    except (urllib.error.URLError, TimeoutError):
        raise ProbeError('Spotify could not be reached. No playback commands were sent.') from None


def track_summary(item):
    item = item or {}
    return {'id': item.get('id'), 'linked_from': (item.get('linked_from') or {}).get('id'),
            'name': item.get('name'), 'isrc': (item.get('external_ids') or {}).get('isrc'),
            'duration_ms': item.get('duration_ms'), 'explicit': item.get('explicit'),
            'artist_ids': [a.get('id') for a in item.get('artists', [])],
            'artist_names': [a.get('name') for a in item.get('artists', [])],
            'is_playable': item.get('is_playable')}


def collect(get, settings):
    state = get('me/player')
    ids = list(IDS)
    observed = (state.get('item') or {}).get('id')
    if observed and observed not in ids and re.fullmatch(r'[A-Za-z0-9]{22}', observed):
        ids.append(observed)
    metadata = {}
    for ident in ids:
        try:
            metadata[ident] = track_summary(get('tracks/'+ident+'?market=from_token'))
        except ProbeError as e:
            metadata[ident] = {'error': str(e)}
    configured = settings.get('spotify_device')
    playlist = settings.get('fallback_playlist')
    return {'probe': 'NextUp recording identity (read-only)',
            'captured_at_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'playing': state.get('is_playing'), 'progress_ms': state.get('progress_ms'),
            'device_matches_saved': (state.get('device') or {}).get('id') == configured if configured else None,
            'context_matches_saved_playlist': (state.get('context') or {}).get('uri') == 'spotify:playlist:'+playlist if playlist else None,
            'current_track': track_summary(state.get('item')), 'recordings': metadata}


def main():
    home = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(os.environ['LOCALAPPDATA']) / 'NextUp'
    try:
        token = saved_token(home)
        settings = json.loads((home / 'userdata/studio.json').read_text(encoding='utf-8'))
        report = collect(lambda path: spotify_get(token, path), settings)
        output = Path(__file__).resolve().with_name('nextup-recording-check.json')
        output.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('Saved nextup-recording-check.json beside this script. Attach that JSON in the chat.')
        return 0
    except ProbeError as e:
        print(str(e))
    except Exception:
        # Never print raw exceptions, paths, settings or account contents.
        print('Could not complete the check. Extract the ZIP first and run it under the same Windows account as NextUp.')
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
