"""Official provider APIs. Spotify plays through the user's Spotify device."""

import asyncio, base64, ctypes, hashlib, json, os, re, secrets, time
from urllib.parse import urlencode, urlsplit, parse_qs
import aiohttp
from .settings import DATA
from .storage import write_private
from .music_policy import YOUTUBE_MUSIC_CATEGORY, require_youtube_music


class ServiceError(ValueError):
    pass


class PlaybackStateError(ValueError):
    """A failed confirmation with a fixed, credential-free diagnostic code."""

    def __init__(self, message, code, state):
        super().__init__(message)
        self.code = code
        self.state = state


class Vault:
    def __init__(self, path=None):
        self.path = path or DATA / "accounts.json"

    def _protect(self, data, decode=False):
        if os.name != "nt":
            return data
        from ctypes import wintypes

        class Blob(ctypes.Structure):
            _fields_ = [
                ("length", wintypes.DWORD),
                ("data", ctypes.POINTER(ctypes.c_ubyte)),
            ]

        buf = ctypes.create_string_buffer(data)
        src = Blob(len(data), ctypes.cast(buf, ctypes.POINTER(ctypes.c_ubyte)))
        dst = Blob()
        fn = (
            ctypes.windll.crypt32.CryptUnprotectData
            if decode
            else ctypes.windll.crypt32.CryptProtectData
        )
        if not fn(ctypes.byref(src), None, None, None, None, 1, ctypes.byref(dst)):
            raise OSError("Windows could not unlock account data.")
        try:
            return ctypes.string_at(dst.data, dst.length)
        finally:
            ctypes.windll.kernel32.LocalFree(dst.data)

    def read(self):
        if not self.path.exists():
            return {}
        raw = json.loads(self.path.read_text())
        if "dpapi" in raw:
            return json.loads(self._protect(base64.b64decode(raw["dpapi"]), True))
        return raw

    def put(self, provider, value):
        data = self.read()
        if value is None:
            data.pop(provider, None)
        else:
            data[provider] = value
        write_private(
            self.path,
            {
                "dpapi": base64.b64encode(
                    self._protect(json.dumps(data).encode())
                ).decode()
            }
            if os.name == "nt"
            else data,
        )


async def request(session, method, url, **kwargs):
    try:
        async with session.request(
            method, url, timeout=aiohttp.ClientTimeout(total=25), **kwargs
        ) as r:
            if r.status == 204:
                return {}
            try:
                data = await r.json(content_type=None)
            except (ValueError, UnicodeError):
                data = {}
            if r.status >= 400:
                e = ServiceError(
                    f"{urlsplit(url).hostname}: HTTP {r.status}. "
                    + {
                        401: "Reconnect this account.",
                        403: "Check account permissions, Premium, and app access.",
                        404: "Open Spotify and select an active device, or check the item.",
                        429: "Rate limit reached; try later.",
                    }.get(r.status, "Check Diagnostics.")
                )
                e.status = r.status
                e.code = (
                    data.get("message", data.get("error", ""))
                    if isinstance(data, dict)
                    else ""
                )
                raise e
            return data
    except (aiohttp.ClientError, asyncio.TimeoutError):
        raise ServiceError(
            "Provider connection timed out or failed. Check your network."
        ) from None


class Spotify:
    SCOPES = "user-read-playback-state user-modify-playback-state playlist-read-private playlist-read-collaborative"
    START_TIMEOUT = 45

    def __init__(self, session, settings, vault):
        self.session, self.settings, self.vault = session, settings, vault
        self.pending = None
        self.lock = asyncio.Lock()
        self.last_device = None
        self.last_start_report = {}
        self.album_devices = set()
        self.identity_metadata = {}

    def connect(self):
        client = self.settings.value["spotify_client_id"]
        if not re.fullmatch("[A-Za-z0-9]{10,100}", client):
            raise ValueError("Enter your Spotify Client ID and save first.")
        verifier = secrets.token_urlsafe(64)
        state = secrets.token_urlsafe(32)
        self.pending = {
            "verifier": verifier,
            "state": state,
            "time": time.monotonic(),
            "client": client,
        }
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        return "https://accounts.spotify.com/authorize?" + urlencode(
            {
                "client_id": client,
                "response_type": "code",
                "redirect_uri": "http://127.0.0.1:8888/callback/spotify",
                "scope": self.SCOPES,
                "state": state,
                "code_challenge_method": "S256",
                "code_challenge": challenge,
            }
        )

    async def callback(self, code, state):
        p = self.pending
        if (
            not p
            or not secrets.compare_digest(state, p["state"])
            or time.monotonic() - p["time"] > 600
        ):
            raise ValueError(
                "Spotify sign-in expired or state did not match. Start again."
            )
        self.pending = None
        t = await request(
            self.session,
            "POST",
            "https://accounts.spotify.com/api/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "http://127.0.0.1:8888/callback/spotify",
                "client_id": p["client"],
                "code_verifier": p["verifier"],
            },
        )
        t.update(client_id=p["client"], expires_at=time.time() + t["expires_in"])
        self.vault.put("spotify", t)

    async def token(self):
        async with self.lock:
            t = self.vault.read().get("spotify")
            if not t or t["client_id"] != self.settings.value["spotify_client_id"]:
                raise ValueError("Connect Spotify first.")
            if t["expires_at"] < time.time() + 60:
                new = await request(
                    self.session,
                    "POST",
                    "https://accounts.spotify.com/api/token",
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": t["refresh_token"],
                        "client_id": t["client_id"],
                    },
                )
                t.update(new)
                t["expires_at"] = time.time() + new["expires_in"]
                self.vault.put("spotify", t)
            return t["access_token"]

    async def api(self, method, path, **kwargs):
        for attempt in range(2):
            token = await self.token()
            try:
                return await request(
                    self.session,
                    method,
                    "https://api.spotify.com/v1/" + path,
                    headers={"Authorization": "Bearer " + token},
                    **kwargs,
                )
            except ServiceError as e:
                if getattr(e, "status", None) != 401 or attempt:
                    raise
                t = self.vault.read()["spotify"]
                t["expires_at"] = 0
                self.vault.put("spotify", t)

    @staticmethod
    def track(t):
        if (
            not t
            or t.get("type", "track") != "track"
            or t.get("is_local")
            or t.get("is_playable") is False
        ):
            raise ValueError("This Spotify track cannot be played.")
        return {
            "provider": "spotify",
            "id": t["id"],
            "source_id": (t.get("linked_from") or {}).get("id", t["id"]),
            "isrc": (t.get("external_ids") or {}).get("isrc", ""),
            "title": t["name"],
            "artists": [a["name"] for a in t["artists"]],
            "artist_ids": [a["id"] for a in t["artists"]],
            "duration": t["duration_ms"] / 1000,
            "explicit": t.get("explicit"),
            "url": "https://open.spotify.com/track/" + t["id"],
            "art": next(iter(t.get("album", {}).get("images", [])), {}).get("url", ""),
        }

    async def resolve(self, ident):
        return self.track(await self.api("GET", "tracks/" + ident))

    async def search(self, text):
        d = await self.api(
            "GET", "search", params={"q": text, "type": "track", "limit": 5}
        )
        return [self.track(t) for t in d["tracks"]["items"]]

    @property
    def connected(self):
        return bool(self.vault.read().get("spotify"))

    @staticmethod
    def matches_track(item, track_id):
        """Accept proven catalog equivalents, never names or artwork alone.

        Keep the requested playlist ID for offsets/cursors. The player can
        report another release of that recording, without linked_from.
        """
        item = item or {}
        target = track_id if isinstance(track_id, dict) else {"id": track_id}
        def ids(t):
            return {x for x in (t.get("id"), t.get("source_id"), t.get("playback_id"),
                               (t.get("linked_from") or {}).get("id")) if x}
        if ids(item) & ids(target):
            return True
        def recording(t):
            return str(t.get("isrc") or (t.get("external_ids") or {}).get("isrc") or "").upper()
        def artists(t):
            return set(t.get("artist_ids") or [a.get("id") for a in t.get("artists", []) if isinstance(a, dict)]) - {None, ""}
        def duration(t):
            return t.get("duration_ms", (t.get("duration") or 0) * 1000)
        # ISRC alone is insufficient: protect against reused/bad metadata,
        # covers, edits and clean/explicit substitutions.
        return bool(recording(item) and recording(item) == recording(target)
                    and artists(item) and artists(item) == artists(target)
                    and isinstance(item.get("explicit"), bool)
                    and item.get("explicit") == target.get("explicit")
                    and duration(item) > 0 and duration(target) > 0
                    and abs(duration(item) - duration(target)) <= 1000)

    async def verify_track(self, item, target):
        """Read-only enrichment for saved rows and sparse player responses."""
        if self.matches_track(item, target):
            return True
        if not isinstance(target, dict) or not (item or {}).get("id"):
            return False
        async def metadata(ident):
            if not ident:
                return {}
            cached = self.identity_metadata.get(ident)
            if cached and cached[0] > time.monotonic():
                return cached[1]
            try:
                async with asyncio.timeout(5):
                    data = await self.api("GET", "tracks/" + ident, params={"market": "from_token"})
                # Require an exact ID or Spotify's documented relink relation.
                if not self.matches_track(data, ident):
                    data = {}
            except (ServiceError, TimeoutError):
                data = {}
            if len(self.identity_metadata) >= 256:
                self.identity_metadata.pop(next(iter(self.identity_metadata)))
            self.identity_metadata[ident] = (time.monotonic() + (300 if data else 15), data)
            return data
        expected = await metadata(target.get("source_id") or target.get("id"))
        self.last_start_report.update(
            expected_resolved_id=expected.get("id"),
            expected_isrc=(expected.get("external_ids") or {}).get("isrc"),
            observed_isrc=(item.get("external_ids") or {}).get("isrc"),
        )
        if not expected:
            return False
        actual = item
        if not self.matches_track(actual, expected):
            actual = await metadata(item["id"])
            self.last_start_report["observed_resolved_id"] = actual.get("id")
            self.last_start_report["observed_isrc"] = (actual.get("external_ids") or {}).get("isrc")
        if not actual or not self.matches_track(actual, expected):
            return False
        # Store only an ID verified against fresh Spotify metadata. Preserve
        # the original queue/playlist identity and carry the proof into polling.
        target["playback_id"] = item["id"]
        target["isrc"] = (expected.get("external_ids") or {}).get("isrc", "")
        self.last_start_report["identity_resolution"] = "spotify_catalog_equivalent"
        return True

    def remember_device(self, state):
        device = state.get("device") or {}
        if device.get("id") and not device.get("is_restricted"):
            self.last_device = (self.settings.value["spotify_client_id"], device["id"])

    async def wait_state(self, playing, track_id=None, device_id=None, repeat_off=False, attempts=21, context_uri=None):
        # Spotify commands acknowledge receipt before Connect state catches up.
        # None means activation-only; an empty state never confirms playback/pause.
        state = {}
        for attempt in range(attempts):
            state = await self.api("GET", "me/player")
            matches = not track_id or self.matches_track(state.get("item"), track_id)
            if (not matches and (not device_id or (state.get("device") or {}).get("id") == device_id)
                    and (not context_uri or (state.get("context") or {}).get("uri") == context_uri)):
                matches = await self.verify_track(state.get("item"), track_id)
            if track_id:
                self.last_start_report.update(
                    expected_track_id=track_id.get("id") if isinstance(track_id, dict) else track_id,
                    observed_track_id=(state.get("item") or {}).get("id"),
                    observed_linked_from=((state.get("item") or {}).get("linked_from") or {}).get("id"),
                    observed_isrc=((state.get("item") or {}).get("external_ids") or {}).get("isrc"),
                    context_matches=(state.get("context") or {}).get("uri") == context_uri if context_uri else None,
                    state_present=bool(state), playing=state.get("is_playing") is True,
                    track_loaded=bool((state.get("item") or {}).get("id")),
                    track_matches=matches,
                    device_matches=(state.get("device") or {}).get("id") == device_id,
                )
            if state and (playing is None or state.get("is_playing") is playing) and (
                matches
            ) and (
                not device_id or (state.get("device") or {}).get("id") == device_id
            ) and (
                not repeat_off or state.get("repeat_state") == "off"
            ) and (not context_uri or (state.get("context") or {}).get("uri") == context_uri):
                self.remember_device(state)
                return state
            if attempt < attempts - 1:
                await asyncio.sleep(0.75)
        if not state:
            code = "spotify_no_state"
            detail = "Spotify returned no playback state. Open Spotify on your selected device and play a song once."
        elif device_id and (state.get("device") or {}).get("id") != device_id:
            code = "spotify_wrong_device"
            detail = "Spotify is reporting a different device. Find playback devices and select your device again."
        elif track_id and not (state.get("item") or {}).get("id"):
            code = "spotify_empty_player"
            detail = "Spotify has no track loaded. Fully quit and reopen Spotify, select this computer in Spotify, and play a song manually before retrying NextUp."
        elif track_id and not matches:
            code = "spotify_wrong_track"
            detail = "Spotify is reporting a different track. Check the Spotify app for an unavailable song or playback interruption."
        elif context_uri and (state.get("context") or {}).get("uri") != context_uri:
            code = "spotify_wrong_context"
            detail = "Spotify did not confirm the saved fallback playlist as its playback source. Check playlist access, then retry."
        elif repeat_off and state.get("repeat_state") != "off":
            code = "spotify_repeat_unconfirmed"
            detail = "Spotify did not confirm Repeat off. Turn Repeat off in Spotify before retrying the queue."
        else:
            code = "spotify_pause_unconfirmed" if playing is False else "spotify_start_unconfirmed"
            detail = "Spotify has not acknowledged " + ("pause" if playing is False else "playback") + ". Open Spotify on your selected device, then retry."
        raise PlaybackStateError(
            "Spotify did not confirm playback state. " + detail, code, state
        )

    async def playback_device(self):
        saved = self.settings.value["spotify_device"]
        devices = (await self.api("GET", "me/player/devices")).get("devices", [])
        device = next((d for d in devices if d.get("id") and
                       (d["id"] == saved if saved else d.get("is_active"))), None)
        # Connect can mark our paused device inactive during a long YouTube
        # video. Reuse only a previously observed device that is still present.
        # An explicit saved choice or another active device always takes priority.
        if not device and not saved and self.last_device:
            client, previous = self.last_device
            if client == self.settings.value["spotify_client_id"]:
                device = next((d for d in devices if d.get("id") == previous), None)
        if not device:
            raise ValueError("The saved Spotify device is unavailable. Open Spotify there, then use Find playback devices to select it again."
                             if saved else "No active Spotify device. Open Spotify and play a song once, or select a device in Connections.")
        if device.get("is_restricted"):
            raise ValueError("Spotify does not allow playback controls on this device. Select another device in Connections.")
        # Device discovery must not mutate Connect state. Start playback directly
        # on the chosen device; only transfer if Spotify explicitly returns 404.
        return device["id"]

    @staticmethod
    def stalled_on_device(state, device_id):
        reported_device = (state.get("device") or {}).get("id")
        return state.get("is_playing") is not True and reported_device in (None, device_id)

    async def play(self, track, *, recover_mismatch=False):
        started_at = time.monotonic()
        self.last_start_report = {"method": "track_list", "starts": 0, "result": "starting"}
        try:
            async with asyncio.timeout(self.START_TIMEOUT):
                state = await self._play(track, recover_mismatch=recover_mismatch)
            self.last_start_report["result"] = "confirmed"
            return state
        except TimeoutError:
            self.last_start_report["result"] = "spotify_start_timeout"
            raise PlaybackStateError(
                "Spotify took too long to start. Open Spotify on your selected device, "
                "then press Resume / Start to retry the retained request.",
                "spotify_start_timeout", {},
            ) from None
        except Exception as e:
            self.last_start_report["result"] = e.code if isinstance(e, PlaybackStateError) else type(e).__name__
            raise
        finally:
            self.last_start_report["elapsed_ms"] = round((time.monotonic() - started_at) * 1000)

    async def _play(self, track, *, recover_mismatch=False):
        device_id = await self.playback_device()
        device_key = (self.settings.value["spotify_client_id"], device_id)
        params = {"device_id": device_id}
        body = {"uris": ["spotify:track:" + track["id"]], "position_ms": 0}
        if device_key in self.album_devices:
            alternate = await self.album_start_body(track)
            if alternate:
                body = alternate
                self.last_start_report["method"] = "album_offset"
        def recoverable(state):
            # Only an explicit owner Play/Resume may replace another playing
            # song during recovery. Automatic handoffs must not fight Spotify.
            return self.stalled_on_device(state, device_id) or (
                recover_mismatch and (state.get("device") or {}).get("id") == device_id
                and not self.matches_track(state.get("item"), track))

        # Spotify does not guarantee Player command execution order. Do not send
        # shuffle/repeat/transfer before a direct start has been acknowledged.
        for attempt in range(2):
            try:
                self.last_start_report["starts"] += 1
                await self.api("PUT", "me/player/play", params=params, json=body)
            except ServiceError as e:
                if getattr(e, "status", None) != 404 or attempt:
                    raise
                # Some Connect clients require activation first. Use this only
                # after an explicit no-device response, never as routine setup.
                if await self.playback_device() != device_id:
                    raise ValueError("Spotify device selection changed. Retry playback.")
                await self.api("PUT", "me/player", json={"device_ids": [device_id], "play": False})
                await self.wait_state(None, device_id=device_id)
                continue
            try:
                state = await self.wait_state(True, track, device_id,
                                              attempts=7 if recover_mismatch and not attempt else 21)
                break
            except PlaybackStateError as e:
                if attempt or "context_uri" in body or not recoverable(e.state):
                    raise
                # Recheck for late success before retrying. Never restart an
                # already-playing track or take playback from another device.
                state = await self.api("GET", "me/player")
                if (state.get("is_playing") is True
                        and (state.get("device") or {}).get("id") == device_id
                        and self.matches_track(state.get("item"), track)):
                    break
                if not recoverable(state):
                    raise
                if await self.playback_device() != device_id:
                    raise ValueError("Spotify device selection changed. Retry playback.")
                # Try an album and exact track offset once instead of repeating
                # the same URI-list command that left the client blank.
                alternate = await self.album_start_body(track)
                if not alternate:
                    raise e
                latest = await self.api("GET", "me/player")
                if (latest.get("is_playing") is True
                        and (latest.get("device") or {}).get("id") == device_id
                        and self.matches_track(latest.get("item"), track)):
                    state = latest
                    break
                if not recoverable(latest):
                    raise e
                body = alternate
                self.last_start_report["method"] = "album_offset"
        # A one-track URI list needs no shuffle change. Repeat is changed only
        # after confirmed playback, and its state must settle before proceeding.
        if state.get("repeat_state") != "off":
            await self.api("PUT", "me/player/repeat", params={**params, "state": "off"})
            await self.wait_state(True, track, device_id, repeat_off=True)
        self.remember_device(state)
        if "context_uri" in body:
            self.album_devices.add(device_key)
        self.last_start_report.update(
            state_present=bool(state), playing=state.get("is_playing") is True,
            track_loaded=bool((state.get("item") or {}).get("id")),
            track_matches=self.matches_track(state.get("item"), track),
            device_matches=(state.get("device") or {}).get("id") == device_id,
        )

        return state

    async def skip_playlist(self, track, playlist, previous_id):
        """Advance only a verified native next entry, without reloading context."""
        context = "spotify:playlist:" + playlist
        device = await self.playback_device()
        state = await self.api("GET", "me/player")
        if ((state.get("device") or {}).get("id") != device
                or (state.get("context") or {}).get("uri") != context):
            return None
        previous_ident = previous_id.get("id") if isinstance(previous_id, dict) else previous_id
        if (previous_ident != track["id"] and state.get("is_playing") is True
                and self.matches_track(state.get("item"), track)):
            return state
        if not self.matches_track(state.get("item"), previous_id):
            return None
        queued = await self.api("GET", "me/player/queue")
        entries = queued.get("queue") or []
        if not entries or not self.matches_track(entries[0], track):
            return None
        return await self.advance_queued(track, preserve_repeat=True, context_uri=context)

    async def play_playlist(self, track, playlist, position_ms=0, controls=None):
        """Keep playlist context and never restart an already-playing target."""
        if not re.fullmatch(r"[A-Za-z0-9]{22}", playlist):
            raise ValueError("Choose a valid Spotify fallback playlist.")
        context = "spotify:playlist:" + playlist
        accepted = False
        self.last_start_report = {"method": "playlist_offset", "starts": 0, "result": "starting"}
        try:
            async with asyncio.timeout(self.START_TIMEOUT):
                device = await self.playback_device()
                params = {"device_id": device}
                before = await self.api("GET", "me/player")
                same = (before.get("is_playing") is True
                        and (before.get("device") or {}).get("id") == device
                        and await self.verify_track(before.get("item"), track))
                if same and (before.get("context") or {}).get("uri") == context:
                    state = before
                    self.last_start_report["method"] = "playlist_already_playing"
                else:
                    # Restoring context must retain the live position if this
                    # exact song is already playing on the selected device.
                    position = before.get("progress_ms", 0) if same else position_ms
                    body = {"context_uri": context, "offset": {"uri": "spotify:track:" + track.get("source_id", track["id"])},
                            "position_ms": max(0, int(position or 0))}
                    for attempt in range(2):
                        try:
                            self.last_start_report["starts"] += 1
                            await self.api("PUT", "me/player/play", params=params, json=body)
                            accepted = True
                        except ServiceError as e:
                            if getattr(e, "status", None) != 404 or attempt:
                                raise
                            await self.api("PUT", "me/player", json={"device_ids": [device], "play": False})
                            await self.wait_state(None, device_id=device)
                            continue
                        state = await self.wait_state(True, track, device, context_uri=context)
                        break
                desired_shuffle = bool((controls or {}).get("shuffle", False))
                desired_repeat = (controls or {}).get("repeat", "off")
                if state.get("shuffle_state", False) != desired_shuffle:
                    await self.api("PUT", "me/player/shuffle", params={**params, "state": str(desired_shuffle).lower()})
                    state = await self.wait_state(True, track, device, context_uri=context)
                if state.get("repeat_state") != desired_repeat:
                    await self.api("PUT", "me/player/repeat", params={**params, "state": desired_repeat})
                    state = await self.wait_state(True, track, device, repeat_off=desired_repeat == "off", context_uri=context)
                self.last_start_report["result"] = "confirmed"
                return state
        except TimeoutError:
            self.last_start_report["result"] = "spotify_start_timeout"
            error = PlaybackStateError("Spotify took too long to confirm the saved playlist. Monitoring without restarting the song.", "spotify_start_timeout", {})
            error.confirmation_only = accepted
            raise error from None
        except Exception as e:
            self.last_start_report["result"] = e.code if isinstance(e, PlaybackStateError) else type(e).__name__
            if isinstance(e, PlaybackStateError): e.confirmation_only = accepted
            raise

    async def album_start_body(self, track):
        metadata = await self.api("GET", "tracks/" + track["id"])
        album = (metadata.get("album") or {}).get("uri", "")
        if (not self.matches_track(metadata, track)
                or not isinstance(metadata.get("id"), str)
                or metadata.get("is_playable") is False or metadata.get("is_local")
                or not re.fullmatch(r"spotify:album:[A-Za-z0-9]{22}", album)):
            return None
        return {"context_uri": album,
                "offset": {"uri": "spotify:track:" + metadata["id"]}, "position_ms": 0}

    async def advance_queued(self, track, *, preserve_repeat=False, context_uri=None):
        """An acknowledged skip is never repeated because its report is late."""
        accepted = False
        self.last_start_report = {"method": "native_next", "starts": 0, "result": "starting"}
        try:
            async with asyncio.timeout(self.START_TIMEOUT):
                device = await self.playback_device()
                await self.api("POST", "me/player/next", params={"device_id": device})
                accepted = True
                self.last_start_report["starts"] = 1
                state = await self.wait_state(None, track, device, context_uri=context_uri)
                if not state.get("is_playing"):
                    await self.api("PUT", "me/player/play", params={"device_id": device})
                    state = await self.wait_state(True, track, device, context_uri=context_uri)
                if not preserve_repeat and state.get("repeat_state") != "off":
                    await self.api("PUT", "me/player/repeat", params={"device_id": device, "state": "off"})
                    state = await self.wait_state(True, track, device, repeat_off=True, context_uri=context_uri)
                self.last_start_report["result"] = "confirmed"
                return state
        except TimeoutError:
            error = PlaybackStateError("Spotify took too long to confirm the skip. Monitoring without repeating it.", "spotify_start_timeout", {})
            error.confirmation_only = accepted
            self.last_start_report["result"] = error.code
            raise error from None
        except PlaybackStateError as e:
            e.confirmation_only = accepted
            self.last_start_report["result"] = e.code
            raise

    async def pause(self, state=None):
        try:
            async with asyncio.timeout(self.START_TIMEOUT):
                await self._pause(state)
        except TimeoutError:
            raise PlaybackStateError("Spotify took too long to pause. Playback was not advanced.",
                                     "spotify_pause_unconfirmed", {}) from None

    async def _pause(self, state=None):
        # The conductor can pass the state it just polled at a track boundary,
        # avoiding another network read before the time-sensitive pause.
        if state is None:
            state = await self.api("GET", "me/player")
        self.remember_device(state)
        if not state or state.get("is_playing") is False:
            return
        # Pause the device actually playing, even if the saved next-play target differs.
        device_id = (state.get("device") or {}).get("id")
        await self.api(
            "PUT",
            "me/player/pause",
            params={"device_id": device_id} if device_id else {},
        )
        await self.wait_state(False)

    async def resume(self, track=None):
        try:
            async with asyncio.timeout(self.START_TIMEOUT):
                return await self._resume(track)
        except TimeoutError:
            raise PlaybackStateError("Spotify took too long to resume. Select a song in Spotify, then retry once.",
                                     "spotify_start_timeout", {}) from None

    async def _resume(self, track=None):
        device_id = await self.playback_device()
        state = await self.api("GET", "me/player")
        if track and (not self.matches_track(state.get("item"), track)
                      or (state.get("device") or {}).get("id") != device_id):
            return await self.play(track, recover_mismatch=True)
        await self.api(
            "PUT",
            "me/player/play",
            params={"device_id": device_id},
        )
        return await self.wait_state(True, track if track else None, device_id)

    async def playlist(self, ident):
        items = []
        # Bound scanned entries, not accepted tracks: unavailable entries still
        # occupy positions in Spotify's pagination.
        for offset in range(0, 10000, 50):
            try:
                d = await self.api("GET", f"playlists/{ident}/items",
                                   params={"limit": 50, "offset": offset})
            except ServiceError as e:
                messages = {
                    403: "Spotify denied access to this playlist (HTTP 403). Use a playlist owned by the connected Spotify account or one it collaborates on. A saved/followed playlist is not necessarily owned by you. If you own it, reconnect Spotify to grant playlist access and check the app's allowed users.",
                    404: "Spotify could not find or access this playlist (HTTP 404). Check the playlist link and the connected account's access.",
                    401: "Spotify playlist authorization expired (HTTP 401). Reconnect Spotify.",
                    429: "Spotify rate-limited playlist loading (HTTP 429). Wait before checking again.",
                }
                if e.status in messages:
                    error = ServiceError(messages[e.status])
                    error.status, error.code = e.status, "spotify_playlist_access"
                    raise error from None
                raise
            rows = d.get("items", [])
            for row in rows:
                try:
                    items.append(self.track(row.get("item") or row.get("track")))
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
            if not rows or not d.get("next"):
                break
        if not items:
            raise ValueError("Spotify returned no playable music in this playlist. The playlist may be empty or contain unavailable tracks, local files or episodes.")
        return items



class YouTube:
    def __init__(self, session, settings):
        self.session, self.settings = session, settings

    async def api(self, path, params):
        key = self.settings.value["youtube_api_key"]
        if not key:
            raise ValueError("Enter a YouTube Data API key in Connections and save.")
        return await request(
            self.session,
            "GET",
            "https://www.googleapis.com/youtube/v3/" + path,
            params={**params, "key": key},
        )

    async def resolve(self, ident):
        data = await self.api(
            "videos", {"part": "snippet,contentDetails,status", "id": ident}
        )
        if not data.get("items"):
            raise ValueError("YouTube video not found.")
        return self.video_track({**data["items"][0], "id": ident})

    def video_track(self, v):
        ident = v["id"]
        s = v["snippet"]
        require_youtube_music(s.get("categoryId"))
        d = v["contentDetails"]
        if (self.settings.value["youtube_player_mode"] == "embedded" and not v["status"].get("embeddable")) or s.get("liveBroadcastContent") in (
            "live",
            "upcoming",
        ):
            raise ValueError("Live or non-embeddable videos cannot be queued.")
        m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d["duration"])
        duration = (
            sum(int(n or 0) * factor for n, factor in zip(m.groups(), (3600, 60, 1)))
            if m
            else 0
        )
        return {
            "provider": "youtube",
            "youtube_category_id": s["categoryId"],
            "id": ident,
            "title": s["title"],
            "artists": [s["channelTitle"]],
            "artist_ids": [s["channelId"]],
            "duration": duration,
            "explicit": True
            if d.get("contentRating", {}).get("ytRating") == "ytAgeRestricted"
            else None,
            "url": "https://www.youtube.com/watch?v=" + ident,
            "art": s.get("thumbnails", {}).get("medium", {}).get("url", ""),
        }

    async def playlist(self, ident):
        """Read accessible playlist entries and resolve metadata in batches."""
        ids, token, seen = [], "", set()
        while len(ids) < 500:
            params = {"part": "contentDetails", "playlistId": ident, "maxResults": 50}
            if token:
                params["pageToken"] = token
            data = await self.api("playlistItems", params)
            ids.extend(row.get("contentDetails", {}).get("videoId") for row in data.get("items", []))
            token = data.get("nextPageToken", "")
            if not token or token in seen:
                break
            seen.add(token)
        ids = [i for i in ids[:500] if isinstance(i, str) and re.fullmatch(r"[\w-]{11}", i)]
        found = {}
        for offset in range(0, len(ids), 50):
            data = await self.api("videos", {"part": "snippet,contentDetails,status", "id": ",".join(ids[offset:offset+50])})
            for video in data.get("items", []):
                try:
                    found[video["id"]] = self.video_track(video)
                except (ValueError, KeyError, TypeError):
                    continue
        return [found[i] for i in ids if i in found]

    async def search(self, text):
        d = await self.api(
            "search",
            {
                "part": "snippet",
                "type": "video",
                "videoCategoryId": YOUTUBE_MUSIC_CATEGORY,
                "videoEmbeddable": "any" if self.settings.value["youtube_player_mode"] == "chrome" else "true",
                "maxResults": 5,
                "q": text,
                "safeSearch": "strict"
                if self.settings.value["block_explicit"]
                else "none",
            },
        )
        tracks = []
        for row in d.get("items", []):
            try:
                tracks.append(await self.resolve(row["id"]["videoId"]))
            except ValueError:
                continue
        return tracks


def parse_link(text):
    text = text.strip()
    if re.fullmatch(r"spotify:track:[A-Za-z0-9]{22}", text):
        return "spotify", text.rsplit(":", 1)[1]
    p = urlsplit(text)
    if p.scheme != "https" or p.username or p.password:
        return None
    if p.hostname == "open.spotify.com":
        match = re.fullmatch(r"/(?:intl-[a-z]{2}/)?track/([A-Za-z0-9]{22})/?", p.path)
        if match:
            return "spotify", match[1]
    if p.hostname in ("youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"):
        ident = (
            p.path.strip("/")
            if p.hostname == "youtu.be"
            else parse_qs(p.query).get("v", [""])[0]
        )
        if p.path.startswith(("/shorts/", "/embed/")):
            ident = p.path.split("/")[2]
        if re.fullmatch(r"[A-Za-z0-9_-]{11}", ident):
            return "youtube", ident
    return None
