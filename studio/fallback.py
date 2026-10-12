"""Resumable Spotify/YouTube playlists, lower priority than viewer requests."""
import asyncio
import copy
import random
import secrets
import time


class FallbackPlaylist:
    def __init__(self, queue, spotify, youtube=None):
        self.queue, self.spotify, self.youtube = queue, spotify, youtube
        self.cached_key = None
        self.tracks = []
        self.loaded_at = 0
        self.note = ""
        self.deferred = set()

    @property
    def enabled(self):
        c = self.queue.settings.value
        return c["fallback_enabled"] and c["provider_mode"] in ("mixed", c["fallback_provider"])

    async def load(self, force=False):
        try:
            return await self._load(force)
        except Exception as e:
            self.note = str(e)
            raise

    async def _load(self, force=False):
        c = self.queue.settings.value
        provider = c["fallback_provider"]
        playlist = c["fallback_playlist"] if provider == "spotify" else c["fallback_youtube_playlist"]
        key = (provider, playlist, c["spotify_client_id"] if provider == "spotify" else c["youtube_api_key"])
        if not playlist:
            raise ValueError("Choose a fallback playlist in Queue first.")
        if provider == "spotify" and not self.spotify.connected:
            raise ValueError("Connect Spotify to play the fallback playlist.")
        if provider == "youtube" and self.youtube is None:
            raise ValueError("YouTube playlist playback is not configured.")
        if force or key != self.cached_key:
            if force:
                self.deferred.clear()
            try:
                async with asyncio.timeout(60):
                    tracks = await (self.spotify if provider == "spotify" else self.youtube).playlist(playlist)
            except TimeoutError:
                raise ValueError("The fallback playlist took too long to load. Check the connection, then press Start / resume to retry.") from None
            self.tracks = list({t["id"]: t for t in tracks}.values())
            self.cached_key, self.loaded_at = key, time.monotonic()
        eligible = []
        for track in self.tracks:
            if (provider, playlist, track["id"]) in self.deferred:
                continue
            try:
                if not self.queue.check_track(track, reviewed=True):
                    eligible.append(track)
            except ValueError:
                continue
        if not eligible:
            raise ValueError("Fallback playlist has no playable songs allowed by the music-only YouTube rule and your artist, explicit and length rules. Check the playlist and request rules.")
        skipped = sum((provider, playlist, t['id']) in self.deferred for t in self.tracks)
        self.note = f"Playlist loaded: {len(eligible)} allowed songs, {len(self.tracks) - len(eligible) - skipped} blocked by request rules."
        if skipped:
            self.note += f" {skipped} skipped after playback failures; refresh the playlist to retry."
        return eligible

    def clear_pending(self):
        self.queue.state["items"] = [x for x in self.queue.state["items"] if not x.get("fallback")]
        self.queue.save()

    async def replenish(self):
        """Materialize the remaining playlist behind viewer requests, without
        committing its position until a track actually starts."""
        if not self.enabled:
            self.clear_pending()
            return []
        eligible = await self.load()
        c = self.queue.settings.value
        provider = c["fallback_provider"]
        playlist = c["fallback_playlist"] if provider == "spotify" else c["fallback_youtube_playlist"]
        key = provider + ":" + playlist
        cursor = self.queue.state.get("fallback_cursors", {}).get(key, {})
        if not cursor and provider == "spotify":
            cursor = self.queue.state.get("fallback_cursor", {})
        if cursor.get("playlist") != playlist or cursor.get("shuffle") != c["fallback_shuffle"]:
            cursor = {}
        played = cursor.get("played", [])
        played_set = set(played)
        remaining = [t for t in eligible if t["id"] not in played_set]
        if not remaining:
            if not c["fallback_repeat"]:
                self.clear_pending()
                self.note = "Fallback playlist finished. Enable Repeat playlist to keep music going."
                return []
            played = []
            remaining = eligible[:]
        old = {x["track"]["id"]: x for x in self.queue.state["items"]
               if x.get("fallback") and x.get("fallback_playlist") == playlist
               and x["track"]["provider"] == provider}
        if c["fallback_shuffle"]:
            # Preserve the already visible order; shuffle only newly staged rows.
            ids = {t["id"] for t in remaining}
            ordered = [i for i in old if i in ids]
            extra = [t["id"] for t in remaining if t["id"] not in ordered]
            random.shuffle(extra)
            ordered += extra
            if len(ordered) > 1 and ordered[0] == cursor.get("last"):
                ordered.append(ordered.pop(0))
            by_id = {t["id"]: t for t in remaining}
            remaining = [by_id[i] for i in ordered]
        pending = []
        for chosen in remaining:
            pending.append({
                "id": old.get(chosen["id"], {}).get("id", "fallback:" + secrets.token_hex(8)),
                "fallback": True, "fallback_playlist": playlist,
                "track": copy.deepcopy(chosen), "reviewed": True,
                "user": {"id": "fallback", "login": "Fallback playlist"},
                "priority": -1, "status": "queued", "created": time.time(), "redemption": None,
                "fallback_cursor_key": key,
                "fallback_shuffle": c["fallback_shuffle"],
                "fallback_cycle_reset": not played,
            })
        self.queue.state["items"] = [x for x in self.queue.state["items"] if not x.get("fallback")] + pending
        self.queue.save()
        return pending

    async def pick(self):
        await self.replenish()
        return self.queue.next_item()

    def can_follow(self, current, nxt):
        if self.queue.settings.value["fallback_shuffle"] or nxt["track"]["provider"] != "spotify":
            return False
        ids = [t["id"] for t in self.tracks]
        try:
            i = ids.index(current["track"]["id"])
            return i + 1 < len(ids) and ids[i + 1] == nxt["track"]["id"]
        except ValueError:
            return False

    def commit(self, item):
        if item.get("fallback") and item in self.queue.state["items"]:
            key = item.get("fallback_cursor_key", item["track"]["provider"] + ":" + item["fallback_playlist"])
            previous = self.queue.state.get("fallback_cursors", {}).get(key, {})
            played = [] if item.get("fallback_cycle_reset") else previous.get("played", [])[:]
            # Native playback may skip unavailable songs or crossfade early.
            # Retire only preceding playlist rows, never viewer requests.
            for row in self.queue.state["items"]:
                if row.get("fallback_cursor_key") == key:
                    if row["track"]["id"] not in played: played.append(row["track"]["id"])
                    if row["id"] == item["id"]: break
            if item["track"]["id"] not in played: played.append(item["track"]["id"])
            cursor = {"playlist": item["fallback_playlist"], "shuffle": item.get("fallback_shuffle", False),
                      "played": played, "last": item["track"]["id"]}
            self.queue.state.setdefault("fallback_cursors", {})[key] = cursor
            if key.startswith("spotify:"):
                self.queue.state["fallback_cursor"] = cursor  # Legacy readers.
            self.queue.save()

    def defer(self, item):
        self.deferred.add((item["track"]["provider"], item["fallback_playlist"], item["track"]["id"]))
        self.queue.state["items"] = [x for x in self.queue.state["items"] if x["id"] != item["id"]]
        self.queue.save()
        self.note = "A playlist song repeatedly failed to start and was skipped for this session. Refresh the playlist to retry it."

    def invalidate(self):
        self.deferred.clear()
        self.cached_key = None
        self.note = ""
        self.clear_pending()
