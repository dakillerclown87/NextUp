"""Stage only the next Spotify request; NextUp owns cross-platform ordering.

Spotify has no public queue removal/reorder API. An uncertain append is never
retried blindly, and unrelated native entries never take over NextUp playback.
"""
import asyncio
from .providers import Spotify


class NativeQueue:
    def __init__(self, conductor):
        self.c = conductor
        self.queue, self.spotify = conductor.queue, conductor.spotify
        self.error = ""

    @property
    def enabled(self):
        return self.queue.settings.value.get("spotify_native_queue", False) or self.c.continuation.active

    def snapshot(self):
        return {"enabled": self.queue.settings.value.get("spotify_native_queue", False),
                "following_playlist": self.c.continuation.active, "error": self.error,
                "sent": sum(x.get("spotify_delivery") == "sent" for x in self.queue.state["items"]),
                "uncertain": sum(x.get("spotify_delivery") in ("sending", "uncertain") for x in self.queue.state["items"])}

    async def flush(self):
        if not self.enabled or not self.c.enabled or self.c.lock.locked():
            return
        async with self.c.lock:
            await self._flush()

    async def _flush(self):
        # Do not send a Spotify track past an intervening YouTube request.
        item = self.queue.next_item()
        if not item or item.get("fallback") or item["track"]["provider"] != "spotify":
            return
        if item.get("spotify_delivery"):
            return
        try:
            async with asyncio.timeout(20):
                await self.c.continuation.remember_next()
                device = await self.spotify.playback_device()
                data = await self.spotify.api("GET", "me/player/queue")
                entries = data.get("queue") or []
                if entries and Spotify.matches_track(entries[0], item["track"]):
                    item["spotify_delivery"] = "sent"
                    self.queue.save()
                    self.error = ""
                    return
                # Persist before dispatch: a timeout/crash must not duplicate it.
                item["spotify_delivery"] = "sending"
                self.queue.save()
                try:
                    await self.spotify.api("POST", "me/player/queue", params={
                        "device_id": device, "uri": "spotify:track:" + item["track"]["id"]})
                except BaseException:
                    item["spotify_delivery"] = "uncertain"
                    self.queue.save()
                    raise
                item["spotify_delivery"] = "sent"
                self.queue.save()
                self.error = ""
        except Exception as e:
            self.error = "Spotify queue delivery could not be confirmed. NextUp will verify the queue before starting this request; it will not append it twice."
            self.c.diag.add("spotify_queue_delivery", type(e).__name__)

    async def start(self, item, *, recover_mismatch=False):
        """Caller owns conductor.lock. Never replace a failed start with a skip."""
        track = item["track"]
        # Connect may consume a queued song before NextUp's next status poll.
        # Confirm the current track before issuing next/play again.
        state = await self.spotify.api("GET", "me/player")
        if (Spotify.matches_track(state.get("item"), track)
                and (state.get("device") or {}).get("id") == await self.spotify.playback_device()):
            if state.get("is_playing") is not True:
                # A handoff may have paused an already-consumed native entry.
                # Resume that entry instead of skipping to a duplicate/next one.
                state = await self.spotify.resume(track)
            self.error = ""
            return state
        if item.get("spotify_delivery"):
            try:
                async with asyncio.timeout(20):
                    data = await self.spotify.api("GET", "me/player/queue")
            except TimeoutError:
                raise ValueError("Spotify took too long to verify its queue. The request is retained; retry when the connection is ready.") from None
            entries = data.get("queue") or []
            if entries and Spotify.matches_track(entries[0], track):
                await self.spotify.advance_queued(track, **({"preserve_repeat": True} if self.c.continuation.active else {}))
                self.error = ""
                return
        # Empty/native-external queues and fallback tracks use a verified direct
        # start. We cannot remove or reorder someone else's Spotify queue.
        if item.get("spotify_delivery"):
            self.error = "Spotify's queue changed. NextUp is starting the requested track directly to preserve your order."
        await self.spotify.play(track, **({"recover_mismatch": True} if recover_mismatch else {}))
