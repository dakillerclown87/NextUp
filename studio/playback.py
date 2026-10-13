"""A single playback conductor. Handoffs wait for pause acknowledgements."""

import asyncio, time, secrets
from .providers import Spotify, PlaybackStateError
from .native_queue import NativeQueue
from .fallback import FallbackPlaylist
from .spotify_continuation import SpotifyContinuation
from .playlist_sync import PlaylistSync


class PlayerBridge:
    def __init__(self):
        self.client = None
        self.last = 0
        self.command = None
        self.waiter = None
        self.state = "disconnected"
        self.track = None

    def poll(self, client):
        now = time.monotonic()
        if self.client and self.client != client and now - self.last < 8:
            raise ValueError(
                "Another YouTube player window is active. Close it before using this one."
            )
        self.client = client
        self.last = now
        return self.command or {}

    async def send(self, action, track=None):
        if time.monotonic() - self.last > 8:
            raise ValueError(
                "Open the YouTube player window and click Enable playback first."
            )
        self.command = {"seq": secrets.token_hex(12), "action": action, "track": track}
        self.waiter = asyncio.get_running_loop().create_future()
        try:
            await asyncio.wait_for(self.waiter, 15)
        finally:
            self.command = None
            self.waiter = None

    def ack(self, client, seq, error=""):
        if client != self.client or not self.command or seq != self.command["seq"]:
            return
        if self.waiter and not self.waiter.done():
            if error:
                self.waiter.set_exception(
                    ValueError(
                        "YouTube playback was blocked or unavailable. Click Enable playback and try again."
                    )
                )
            else:
                self.waiter.set_result(True)


class Conductor:
    def __init__(self, queue, spotify, bridge, diagnostics, youtube=None):
        self.queue, self.spotify, self.bridge, self.diag = (
            queue,
            spotify,
            bridge,
            diagnostics,
        )
        self.enabled = False
        self.lock = asyncio.Lock()
        self.status = "Stopped"
        self.error = ""
        self.progress = 0
        self.observed = None
        self.observed_at = 0
        self.dismissed_spotify = None
        self.near_end = False
        self.play_started = 0
        self.spotify_sample = None
        self.spotify_device = None
        self.failed_item = None
        self.starting_item = None
        self.fallback = FallbackPlaylist(queue, spotify, youtube)
        self.continuation = SpotifyContinuation(self)
        self.native = NativeQueue(self)
        self.playlist_sync = PlaylistSync(self)
        self.recovery = None
        self.recovery_skips = []

    @property
    def progress(self):
        extra = min(5, max(0, time.monotonic() - self._progress_at)) if self.status == "Playing" else 0
        current = self.display_current()
        duration = current["track"]["duration"] if current else 0
        return min(duration, self._progress + extra) if duration else 0

    @progress.setter
    def progress(self, seconds):
        self._progress = max(0, float(seconds or 0))
        self._progress_at = time.monotonic()

    def display_current(self):
        current = self.queue.state["current"]
        if getattr(self, "observed", None) and (not current or current["track"]["provider"] == "spotify"):
            return self.observed
        return current

    def snapshot(self):
        return {"status": self.status, "error": self.error, "progress": self.progress,
                "current": self.display_current(), "sampled_at": time.time(),
                "busy": self.lock.locked(), "failed_item": self.failed_item,
                "starting": self.starting_item or (self.recovery or {}).get("item"),
                "fallback_active": bool((self.queue.state["current"] or {}).get("fallback")),
                "fallback_note": self.fallback.note,
                "following_spotify_playlist": self.continuation.active}

    def reject_busy(self):
        if self.lock.locked():
            raise ValueError("A playback operation is already running. Please wait for its result; this click was not queued.")

    async def pause_source(self, item, spotify_state=None):
        if not item:
            return
        if item["track"]["provider"] == "spotify":
            if spotify_state is None:
                await self.spotify.pause()
            else:
                await self.spotify.pause(state=spotify_state)
        else:
            await self.bridge.send("pause")

    def failed(self, error):
        # New chat requests must not keep restarting a stalled Spotify client.
        # Nonrecoverable failures require a manual Resume/Start.
        self.enabled = False
        self.status = "Needs attention"
        self.error = str(error)
        self.diag.add(
            error.code if isinstance(error, PlaybackStateError) else "playback_failed",
            type(error).__name__,
        )

    async def next(self, manual=False, expected=None, spotify_state=None, owner_start=False):
        if expected is None:
            self.reject_busy()
        if manual and not self.queue.settings.value["skip_enabled"]:
            raise ValueError("Skip is disabled.")
        async with self.lock:
            current = self.queue.state["current"]
            outgoing = current or self.observed
            if expected is not None and (
                (current["id"] if current else "") != expected or not self.enabled
            ):
                return
            self.enabled = True
            if manual and not current and self.recovery and self.recovery["item"].get("fallback"):
                # An explicit second Skip abandons the unconfirmed background
                # song. It must not silently start that same retained row again.
                self.fallback.defer(self.recovery["item"])
                self.recovery = None
            # Skip a retained failed request instead of starting it again.
            # Confirm the source stopped in case the failed start arrived late.
            if manual and not current and self.failed_item:
                failed = next((x for x in self.queue.state["items"] if x["id"] == self.failed_item), None)
                if failed:
                    try:
                        await self.pause_source(failed)
                    except Exception as e:
                        self.failed(e)
                        raise
                    self.queue.remove(failed["id"])
                self.failed_item = None
            nxt = self.queue.next_item()
            if manual and not nxt and current and current.get("native_playlist"):
                await self.continuation.remember_next()
            starting = False
            state = None
            try:
                # Stop the previous source before starting the next; errors leave it retained.
                self.status = "Switching songs"
                self.error = ""
                self.starting_item = nxt
                # Hold the outgoing player before network-backed fallback lookup.
                # Natural ends also pause same-provider playback to prevent an
                # album/autoplay track leaking through while the next start loads.
                stopped = not nxt or expected is not None
                if stopped:
                    await self.pause_source(current or self.observed, spotify_state)
                if not nxt:
                    # The outgoing song is already stopped. Retire it before
                    # loading fallback so a failed load cannot resume that old
                    # song instead of retrying the playlist.
                    if current:
                        self.queue.finish()
                        current = None
                    self.observed = None
                    nxt = await self.fallback.pick()
                    if not nxt and not self.fallback.enabled:
                        nxt = self.continuation.return_row()
                # A new track on the same Spotify account replaces the old one.
                # Avoid an unnecessary pause + polling round trip between songs.
                same_spotify = nxt and (current or self.observed) and nxt["track"]["provider"] == (current or self.observed)["track"]["provider"] == "spotify"
                if not stopped and not same_spotify:
                    await self.pause_source(current or self.observed, spotify_state)
                if current:
                    self.queue.finish()
                if not nxt:
                    dismissed = outgoing
                    self.dismissed_spotify = dismissed["track"]["id"] if dismissed and dismissed["track"]["provider"] == "spotify" else None
                    self.observed = None
                    self.status = "Queue empty"
                    self.progress = 0
                    self.near_end = False
                    self.error = ""
                    return
                self.starting_item = nxt
                if not current:
                    if (
                        nxt["track"]["provider"] == "youtube"
                        and getattr(self.spotify, "connected", False) is True
                    ):
                        await self.spotify.pause()
                    if (
                        nxt["track"]["provider"] == "spotify"
                        and isinstance(getattr(self.bridge, "last", None), (int, float))
                        and time.monotonic() - self.bridge.last < 8
                    ):
                        await self.bridge.send("pause")
                if nxt["track"]["provider"] == "spotify":
                    self.status = "Starting Spotify"
                    starting = True
                    if nxt.get("native_playlist"):
                        await self.continuation.start(nxt)
                    elif nxt.get("fallback"):
                        state = None
                        if (manual and current and current.get("fallback")
                                and current["track"]["provider"] == "spotify"
                                and current.get("fallback_playlist") == nxt["fallback_playlist"]):
                            state = await self.spotify.skip_playlist(nxt["track"], nxt["fallback_playlist"], current["track"])
                        if state is None:
                            state = await self.spotify.play_playlist(nxt["track"], nxt["fallback_playlist"])
                        self.spotify_device = (state.get("device") or {}).get("id") if isinstance(state, dict) else None
                        if isinstance(state, dict): self.playlist_sync.usable(state)
                    elif self.native.enabled:
                        await self.native.start(nxt, **({"recover_mismatch": True} if owner_start else {}))
                    else:
                        await self.spotify.play(nxt["track"], **({"recover_mismatch": True} if owner_start else {}))
                else:
                    self.status = "Starting YouTube"
                    starting = True
                    await self.bridge.send("play", nxt["track"])
                self.observed = None
                self.fallback.commit(nxt)
                self.queue.activate(nxt)
                self.failed_item = None
                self.recovery = None
                self.starting_item = None
                self.status = "Playing"
                self.error = ""
                self.progress = (state.get("progress_ms") or 0) / 1000 if isinstance(state, dict) else 0
                self.near_end = False
                self.play_started = time.monotonic()
                self.spotify_sample = None
                try:
                    await self.fallback.replenish()
                except Exception as e:
                    # A prefetch failure must not release control of the track
                    # that has already started. Retry at the next transition.
                    self.fallback.note = str(e)
                    self.diag.add("fallback_prefetch", type(e).__name__)
            except Exception as e:
                if starting and not nxt.get("fallback") and not nxt.get("native_playlist"):
                    self.failed_item = nxt["id"]
                if starting and nxt and nxt["track"]["provider"] == "spotify":
                    self.schedule_recovery(nxt, e)
                else:
                    self.failed(e)
                raise
            finally:
                self.starting_item = None

    def schedule_recovery(self, item, error):
        recoverable = isinstance(error, PlaybackStateError) and error.code in (
            "spotify_wrong_track", "spotify_wrong_context", "spotify_no_state", "spotify_start_timeout", "spotify_start_unconfirmed")
        if not recoverable:
            self.recovery = None
            self.failed(error)
            return
        previous = self.recovery or {}
        attempts = previous.get("attempts", 0) + 1 if previous.get("item", {}).get("id") == item["id"] else 1
        device = (error.state.get("device") or {}).get("id") or self.spotify_device
        self.recovery = {"item": item, "attempts": attempts,
                         "device": device, "passive": attempts > 3,
                         "confirmation_only": getattr(error, "confirmation_only", False),
                         "deadline": time.monotonic() + 60,
                         "at": time.monotonic() + min(30, 5 * attempts)}
        self.enabled = True
        self.status = "Waiting for Spotify" if attempts > 3 else "Recovering Spotify playback"
        self.error = ("Spotify has not confirmed this song. It is retained; monitoring for playback without sending more start commands."
                      if attempts > 3 else "Spotify reported a different or delayed song. Retrying playback; your queue and account remain connected.")
        self.diag.add("spotify_recovery", ("passive:" if attempts > 3 else "retry:") + error.code)
        if self.recovery["confirmation_only"]:
            self.error = "Spotify accepted the command but reported another track. Checking its recording identity without restarting playback."
            self.diag.add("spotify_confirmation_pending", "Accepted command; observation only")

    async def retry_recovery(self):
        r = self.recovery
        if not r or not self.enabled or self.lock.locked():
            return False
        target = r["item"]
        if target.get("fallback") and (not self.fallback.enabled or target.get("fallback_playlist") != self.queue.settings.value["fallback_playlist"]):
            self.recovery = None
            return False
        if not target.get("fallback") and not target.get("native_playlist") and target not in self.queue.state["items"] and self.queue.state["current"] is not target:
            self.recovery = None  # The owner removed/skipped the retained request.
            return False
        # Backoff limits control writes, not observation. A late success must
        # clear recovery on the next normal poll, even before the retry is due.
        data = await self.spotify.api("GET", "me/player")
        if self.recovery is not r or not self.enabled:
            return True  # Pause or another owner operation won the network race.
        device = (data.get("device") or {}).get("id")
        if r.get("device") and device and device != r["device"]:
            r.update(passive=True, at=time.monotonic()+15)
            self.status = "Waiting for Spotify"
            self.error = "Spotify moved to another device. The request is retained; select your intended device and resume."
            return True
        context = (data.get("context") or {}).get("uri")
        wanted_context = ("spotify:playlist:" + target["fallback_playlist"] if target.get("fallback")
                          else self.continuation.context.get("uri") if target.get("native_playlist") else None)
        first = self.queue.next_item()
        if target.get("fallback") and data.get("is_playing") and first and first.get("fallback") and context == wanted_context:
            actual = next((x for x in self.queue.state["items"] if x.get("fallback")
                           and x.get("fallback_playlist") == target["fallback_playlist"]
                           and Spotify.matches_track(data.get("item"), x["track"])), None)
            if actual: target = actual
        matched = Spotify.matches_track(data.get("item"), target["track"])
        if not matched and (not wanted_context or context == wanted_context):
            verifier = getattr(self.spotify, "verify_track", None)
            if verifier:
                matched = await verifier(data.get("item"), target["track"])
            if self.recovery is not r or not self.enabled:
                return True
        if target.get("native_playlist") and context == wanted_context and data.get("is_playing"):
            try:
                target = self.continuation.row(Spotify.track(data.get("item")))
                matched = True
            except (ValueError, KeyError, TypeError):
                pass
        if data.get("is_playing") and matched and (not wanted_context or context == wanted_context):
            async with self.lock:
                if self.recovery is not r or not self.enabled: return True
                if target.get("native_playlist"):
                    self.continuation.adopt(target, data)
                    self.recovery = None
                else:
                    await self.playlist_sync.adopt(target, data)
                self.failed_item = None
                report = getattr(self.spotify, "last_start_report", None)
                if isinstance(report, dict):
                    report.update(result="confirmed_late", playing=True,
                                  expected_track_id=target["track"]["id"],
                                  observed_track_id=(data.get("item") or {}).get("id"),
                                  track_matches=True, device_matches=True,
                                  context_matches=context == wanted_context if wanted_context else None)
                self.diag.add("spotify_recovered", "Playback confirmed without restarting audio")
            return True
        if r.get("confirmation_only"):
            if time.monotonic() >= r["deadline"]:
                # A permanent mismatch is not a delayed acknowledgement. Keep
                # the request unplayed, stop retries and show the real player.
                # Never blindly restart/skip or count an unrelated song served.
                async with self.lock:
                    if self.recovery is not r or not self.enabled: return True
                    self.recovery = None
                    self.enabled = False
                    self.failed_item = target["id"]
                    self.status = "Needs attention"
                    self.error = "Spotify is playing an unverified track. Automatic queue playback is paused; your request is retained. Resume or Skip when ready."
                    try:
                        track = Spotify.track(data.get("item"))
                        self.observed = {"id": "external:" + track["id"], "track": track,
                                         "user": {"id": "external", "login": "Spotify app"},
                                         "status": "playing" if data.get("is_playing") else "paused", "external": True}
                        self.progress = (data.get("progress_ms") or 0) / 1000
                    except (ValueError, KeyError, TypeError):
                        self.observed = None
                    self.diag.add("spotify_identity_unresolved", "No verified recording match within 60 seconds; request retained")
                return True
            return True  # Repeating an acknowledged start/skip can restart audio.
        if time.monotonic() < r["at"]:
            return True
        if r.get("passive"):
            # A bad background song must not stall the whole playlist. Never
            # silently skip a viewer request. Bound skips across distinct songs.
            now = time.monotonic()
            self.recovery_skips = [t for t in self.recovery_skips if now - t < 300]
            if target.get("fallback") and not r.get("deferred") and len(self.recovery_skips) < 3:
                async with self.lock:
                    if self.recovery is not r or not self.enabled: return True
                    self.fallback.defer(target)
                    r["deferred"] = True
                    if self.queue.state["current"] is target: self.queue.finish()
                    self.recovery_skips.append(now)
                    self.diag.add("playlist_song_deferred", "Repeated start confirmation failure")
                    try:
                        await self.fallback.replenish()
                    except ValueError:
                        # Keep the session/account alive if every track fails.
                        r["at"] = now + 15
                        return True
                    self.recovery = None
                try:
                    await self.next(expected="")
                except Exception:
                    pass
                return True
            r["at"] = now + 15
            return True  # Read-only observation; no endless control-command loop.
        current = self.queue.state["current"]
        if current:
            try:
                await self.resume()
                self.recovery = None
            except Exception:
                pass  # resume schedules the failure exactly once.
        else:
            try:
                await self.next(expected="", spotify_state=data, owner_start=True)
            except Exception:
                pass
        return True

    async def pause(self):
        self.reject_busy()
        async with self.lock:
            seconds = self.progress
            await self.pause_source(self.queue.state["current"] or self.observed or (self.recovery or {}).get("item"))
            self.status = "Paused"
            self.progress = seconds
            self.enabled = False
            self.recovery = None
            self.spotify_sample = None

    async def resume(self):
        self.reject_busy()
        current = self.queue.state["current"]
        if (self.continuation.follow_current and not self.failed_item
                and (not current or current.get("native_playlist"))):
            # Resume/Start may be clicked before the next monitor poll. Prefer
            # what Spotify is playing now over a return point from last session.
            async with self.lock:
                async with asyncio.timeout(12):
                    data = await self.spotify.api("GET", "me/player")
                    if data.get("is_playing") and await self.continuation.capture_context(data):
                        return
                if not current:
                    self.continuation.active = False
                    if not self.queue.next_item():
                        self.enabled = False
                        self.status = "Waiting for Spotify playlist"
                        self.error = ""
                        return
        self.enabled = True
        if self.continuation.context and not self.fallback.enabled and not self.continuation.follow_current:
            self.continuation.active = True
        if not self.queue.state["current"]:
            if self.observed and not self.queue.next_item() and not self.queue.settings.value["fallback_enabled"]:
                async with self.lock:
                    await self.spotify.resume(self.observed["track"])
                    self.status = "Playing"
                    self.progress = self._progress
                return
            return await self.next(owner_start=True)
        async with self.lock:
            try:
                if self.queue.state["current"]["track"]["provider"] == "spotify":
                    current = self.queue.state["current"]
                    if current.get("native_playlist"):
                        state = await self.continuation.start(current, position_ms=self._progress * 1000)
                    elif current.get("fallback"):
                        state = await self.spotify.play_playlist(current["track"], current["fallback_playlist"], position_ms=self._progress * 1000)
                        self.spotify_device = (state.get("device") or {}).get("id") if isinstance(state, dict) else None
                        if isinstance(state, dict): self.playlist_sync.usable(state)
                    else:
                        state = await self.spotify.resume(current["track"])
                    if isinstance(state, dict):
                        self.progress = state.get("progress_ms", 0) / 1000
                    self.play_started = time.monotonic()
                    self.near_end = False
                    self.spotify_sample = None
                else:
                    await self.bridge.send("resume")
                self.observed = None
                self.status = "Playing"
                self.error = ""
                self.recovery = None
            except Exception as e:
                current = self.queue.state["current"]
                if current and current["track"]["provider"] == "spotify":
                    self.schedule_recovery(current, e)
                else:
                    self.failed(e)
                raise

    async def ended(self, track_id):
        c = self.queue.state["current"]
        if (
            c
            and c["track"]["provider"] == "youtube"
            and c["track"]["id"] == track_id
            and self.enabled
        ):
            await self.next(expected=c["id"])

    def spotify_finished_between_polls(self, current, data):
        """Recover a missed end only after Spotify confirms a new playing item.

        A UI timer alone never advances a song. Require a recent, playing API
        sample of this exact managed item, enough elapsed time to reach its end,
        and a changed track on the same device. Long outages and manual changes
        before that boundary retain the usual owner-control behavior.
        """
        sample = self.spotify_sample
        if (not sample or sample["current"] != current["id"] or not sample["playing"]
                or self.status != "Playing" or data.get("is_playing") is not True
                or not (data.get("item") or {}).get("id")
                or not sample["device"]
                or (data.get("device") or {}).get("id") != sample["device"]):
            return False
        elapsed = time.monotonic() - sample["at"]
        return 0 <= elapsed <= 30 and sample["duration"] > 0 and (
            sample["progress"] + elapsed >= sample["duration"] - 0.4)

    async def poll_spotify(self):
        if not self.spotify.connected or self.lock.locked():
            return
        c = self.queue.state["current"]
        if c and c["track"]["provider"] != "spotify":
            return
        data = await self.spotify.api("GET", "me/player")
        if self.lock.locked() or self.queue.state["current"] is not c:
            return
        if c and not self.playlist_sync.usable(data):
            return
        self.spotify.remember_device(data)
        if await self.continuation.poll(c, data):
            return
        c = self.queue.state["current"]
        item = data.get("item") or {}
        progress = max(0, (data.get("progress_ms") or 0) / 1000)
        playing = data.get("is_playing") is True
        # Do not hide the startup failure with a subsequent empty/paused poll.
        if self.error and not self.enabled and not playing:
            return
        if not c and self.dismissed_spotify and Spotify.matches_track(item, self.dismissed_spotify) and not playing:
            self.observed = None
            self.status = "Queue empty"
            self.progress = 0
            return
        if playing:
            self.dismissed_spotify = None
        device = (data.get("device") or {}).get("id")
        if await self.playlist_sync.poll(c, data):
            return
        if c and Spotify.matches_track(item, c["track"]):
            self.observed = None
            duration = (item.get("duration_ms") or c["track"]["duration"] * 1000) / 1000
            self.spotify_device = device or self.spotify_device
            self.spotify_sample = {
                "current": c["id"], "at": time.monotonic(), "playing": playing,
                "progress": progress, "duration": duration,
                "device": (data.get("device") or {}).get("id"),
            }
            remaining = duration - progress
            was_near_end = self.near_end
            self.near_end = duration > 0 and remaining <= 3
            # Spotify has no Web API end callback. A short, verified boundary
            # guard stops Connect before album/autoplay advances. Never advance
            # from an interpolated timer alone, or from a user pause mid-song.
            boundary = playing and duration > 0 and remaining <= 0.4
            completed = not playing and duration > 0 and remaining <= 0.4
            repeated = was_near_end and playing and progress < self._progress - 5
            nxt = self.queue.next_item()
            native_transition = (playing and self.native.enabled and nxt
                                 and nxt["track"]["provider"] == "spotify" and nxt.get("spotify_delivery"))
            playlist_transition = (playing and c.get("fallback") and nxt and nxt.get("fallback")
                and self.fallback.can_follow(c, nxt)
                and (data.get("context") or {}).get("uri") == "spotify:playlist:" + c["fallback_playlist"]
                and not data.get("shuffle_state", False) and data.get("repeat_state") != "track")
            if self.enabled and (boundary or completed or repeated) and not native_transition and not playlist_transition:
                await self.next(expected=c["id"], spotify_state=data)
                return
            self.status = "Playing" if playing else "Paused"
            self.progress = progress
            self.error = ""
            return
        if c and self.enabled and (self.near_end or self.spotify_finished_between_polls(c, data)):
            nxt = self.queue.next_item()
            if (self.native.enabled and nxt and nxt["track"]["provider"] == "spotify"
                    and nxt.get("spotify_delivery") and playing
                    and Spotify.matches_track(item, nxt["track"])):
                async with self.lock:
                    if self.queue.state["current"] is not c or not self.enabled:
                        return
                    self.queue.finish()
                    self.queue.activate(nxt)
                    self.observed = None
                    self.near_end = False
                    self.progress = progress
                    self.status = "Playing"
                    self.play_started = time.monotonic()
                    self.spotify_sample = None
                return
            await self.next(expected=c["id"], spotify_state=data)
            return
        if c and time.monotonic() - self.play_started < 8:
            return
        if c:
            # A manual Spotify song replaces the display, but keep the original
            # request until the owner resumes/skips it. No surprise auto-starts.
            self.enabled = False
            self.error = "Spotify changed songs. The managed request is retained; skip it or resume the queue when ready."
        try:
            track = Spotify.track(item)
        except (ValueError, KeyError, TypeError):
            self.observed = None
            if not c:
                self.status = "Stopped"
                self.progress = 0
            else:
                self.status = "Needs attention"
            return
        self.observed = {"id": "external:" + track["id"], "track": track,
                         "user": {"id": "external", "login": "Spotify app"},
                         "status": "playing" if playing else "paused", "external": True}
        self.observed_at = time.monotonic()
        self.status = "Playing" if playing else "Paused"
        self.progress = progress
        if not c and not self.failed_item:
            self.error = ""

    def poll_delay(self):
        if self.recovery:
            return 1
        current = self.queue.state["current"]
        if (self.enabled and self.status == "Playing"
                and current and current["track"]["provider"] == "spotify"):
            # Only tighten polling around a managed song boundary. External
            # Spotify playback retains the normal API request rate.
            remaining = current["track"]["duration"] - self.progress
            return max(0.1, min(2, remaining - 0.3))
        return 2

    async def monitor(self):
        failures = 0
        while True:
            await asyncio.sleep(self.poll_delay())
            try:
                if await self.retry_recovery():
                    continue
                if not self.lock.locked():
                    async with self.lock:
                        await self.continuation.attach()
                await self.poll_spotify()
                await self.native.flush()
                failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                failures += 1
                if failures in (1, 5):
                    self.diag.add("spotify_poll", type(e).__name__)
                if failures >= 5:
                    self.progress = self.progress
                    self.status = "Needs attention"
                    self.error = "Spotify status is unavailable. NextUp will keep checking; your queue is retained. Check Diagnostics if this continues."
