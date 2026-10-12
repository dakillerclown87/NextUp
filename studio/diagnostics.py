"""Bounded structured diagnostics. Never records chat transcripts or tokens."""

import json, time
from pathlib import Path

FIXES = {
    "spotify_identity_unresolved": "Spotify reported a track that could not be verified as the requested recording within 60 seconds. Automatic playback stopped without restarting audio or discarding the request. Export diagnostics before resuming or skipping.",
    "spotify_recovered": "Playback was confirmed after a delayed report. NextUp resumed tracking without restarting the song.",
    "spotify_confirmation_pending": "Spotify accepted a start/skip but reported another track. NextUp is observing without repeating that command. This is not an account disconnection. If it persists, export Diagnostics; track identifiers are included for comparison.",
    "playlist_song_deferred": "A background song was skipped after playback failures. The playlist remains saved; Check saved playlist makes skipped songs eligible again.",
    "spotify_recovery": "Playback confirmation was delayed. NextUp checks status during retry backoff and clears the live warning when playback is confirmed; this historical event does not mean the account disconnected.",
    "playlist_reconciled": "Spotify advanced within the selected playlist; NextUp synchronized its cursor without restarting audio.",
    "playlist_retry": "Spotify confirmation was delayed. NextUp retains requests and retries at most three times with backoff; no playlist reload is needed for transient drift.",
    "spotify_queue_delivery": "Check the Spotify queue. Uncertain submissions are not retried automatically, to avoid duplicate songs. Remove a song in Spotify before using Forget in NextUp.",
    "spotify_start_timeout": "Spotify did not finish starting within 45 seconds. Open Spotify on the selected device and use Resume / Start to retry the retained request.",
    "spotify_empty_player": "Spotify has no track loaded. Fully quit/reopen Spotify, select this computer in Spotify, play manually, then retry NextUp.",
    "spotify_no_state": "Spotify returned no player state. Open Spotify on the selected device and play a song manually before retrying.",
    "spotify_wrong_device": "Spotify reports another device. Find playback devices and select the intended device again.",
    "spotify_wrong_track": "Spotify reports a different song. Check whether the requested track plays manually; stop competing playback controls.",
    "spotify_start_unconfirmed": "Spotify did not start. Restart its desktop client, confirm manual playback, and retry once.",
    "spotify_pause_unconfirmed": "Spotify did not confirm pause. The handoff was stopped to avoid overlapping audio.",
    "spotify_repeat_unconfirmed": "Spotify did not confirm Repeat off. Turn Repeat off in Spotify, then retry the queue.",
    "playback_failed": "Check Spotify Premium and active device; for YouTube, open the player and enable playback. Reconnect the affected account.",
    "spotify_poll": "Check network, Spotify account access, and the selected playback device.",
    "external_playback": "Playback was changed outside NextUp. Stop the other playback and use Resume or Skip.",
    "twitch_connection": "Reconnect Twitch. Check Client ID and channel login. The broadcaster must authorize channel-point scopes.",
    "points_connection": "Sign in as the channel owner, refresh rewards and select the correct reward ID. Enable viewer text input and start the bot.",
    "points_history": "Recovery of older redemptions failed. Live requests continue; review missed redemptions in Twitch.",
    "points_settlement": "Review Twitch redemptions. Only rewards created by this Client ID support automatic refunds; other rewards need manual action.",
    "update_failed": "Check the configured GitHub repository, release signature and signing key. Existing version remains available.",
    "request_failed": "Review source availability, request limits and block lists.",
    "player_lost": "Keep the YouTube player window open. Click Enable playback if the browser blocks autoplay.",
}


class Diagnostics:
    def __init__(self, path):
        self.path = Path(path)
        self.rows = []

    def add(self, code, detail=""):
        # Detail is only an internal exception class or a fixed diagnostic string.
        row = {
            "time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "code": code,
            "detail": detail[:160],
        }
        self.rows.append(row)
        self.rows = self.rows[-200:]
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and self.path.stat().st_size > 1_000_000:
            self.path.replace(self.path.with_suffix(".previous.jsonl"))
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")

    def report(self):
        return [
            {
                "code": c,
                "count": sum(r["code"] == c for r in self.rows),
                "suggestion": FIXES.get(
                    c, "Review configuration and reconnect the affected service."
                ),
            }
            for c in dict.fromkeys(r["code"] for r in reversed(self.rows))
        ]

    def analyze(self, text):
        if len(text) > 1_000_000:
            raise ValueError("Log file must be smaller than 1 MB.")
        # Return known findings only; uploaded text is not saved or echoed.
        found = []
        for pattern, fix in [
            ("401", "Authorization expired: reconnect the affected account."),
            ("403", "Check permissions, account access and Premium status."),
            ("429", "API rate limit: wait before retrying."),
            (
                "153",
                "YouTube requires a valid embedding origin/referrer. Use the provided player URL.",
            ),
            (
                "100",
                "If this is a YouTube player error, the video may be removed/private.",
            ),
            ("timeout", "Check network and provider status."),
            (
                "signature",
                "Update verification failed. Do not install modified release files.",
            ),
            ("ModuleNotFoundError", "Run SETUP.bat to repair Python components."),
        ]:
            if pattern.lower() in text.lower():
                found.append({"match": pattern, "suggestion": fix})
        return found or [
            {
                "match": "No known pattern",
                "suggestion": "No known error pattern found. Review the affected provider in Connections.",
            }
        ]
