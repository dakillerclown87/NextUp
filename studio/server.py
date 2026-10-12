"""Local Studio application. Admin and read-only overlay servers are separated."""

import asyncio, contextlib, os, re, secrets, sys, threading, time, webbrowser
from pathlib import Path
from aiohttp import web, ClientSession, ClientTimeout
from . import __version__
from .settings import Settings, ROOT, HOME
from .providers import Spotify, YouTube, Vault, parse_link
from .queue import Queue
from .playback import PlayerBridge, Conductor
from .chrome import ChromePlayer, PlayerChoice, extension_origin
from .twitch_service import Twitch, StudioBot
from .diagnostics import Diagnostics
from .updater import Updater
from .instance import InstanceLock


class Studio:
    def __init__(self, session, home=HOME):
        self.home = Path(home)
        self.data = self.home / "userdata"
        self.data.mkdir(parents=True, exist_ok=True)
        self.settings = Settings(self.data / "studio.json")
        self.vault = Vault(self.data / "accounts.json")
        self.diag = Diagnostics(self.data / "logs/events.jsonl")
        self.queue = Queue(self.data / "queue.sqlite3", self.settings)
        from .moderation import Moderation
        self.moderation = Moderation(self)
        from .artwork_palette import ArtworkPalette
        self.artwork_palette = ArtworkPalette(session)
        self.spotify = Spotify(session, self.settings, self.vault)
        self.youtube = YouTube(session, self.settings)
        self.bridge = PlayerBridge()
        self.chrome = ChromePlayer(self)
        self.player = PlayerChoice(self.settings, self.bridge, self.chrome)
        self.conductor = Conductor(self.queue, self.spotify, self.player, self.diag, self.youtube)
        self.twitch = Twitch(session, self.settings, self.vault, self.diag)
        self.updater = Updater(session, home=self.home)
        self.admin = secrets.token_urlsafe(32)
        self.service_lock = asyncio.Lock()
        keypath = self.data / "overlay-key.txt"
        if not keypath.exists():
            keypath.write_text(secrets.token_urlsafe(32))
            keypath.chmod(0o600)
        self.overlay_key = keypath.read_text()
        from .widget_design import WidgetAssets
        self.widget_assets = WidgetAssets(self.data)
        from .equalizer import ApplicationEqualizer
        self.equalizer = ApplicationEqualizer(self.settings, playback=self.conductor.snapshot, browser_peer=self.chrome.audio_peer)
        self.audio_clients = set()
        self.tasks = set()
        self.bot_tasks = []
        self.bot = None
        self.overlay_tunnel = None
        self.overlay_public = ""
        self.stop_event = asyncio.Event()
        self.desktop = None
        self.chat_seen = {}
        self.chat_rate = {}
        self.login_task = None

    def background(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task

    async def request_song(
        self, text, user, roles, event_id=None, redemption=None, owner=False
    ):
        self.queue.check_request_method(roles, redemption is not None, owner)
        link = parse_link(text)
        if not link:
            raise ValueError(
                "Paste a Spotify track link or a YouTube video link. Use the dashboard to search by name."
            )
        track = await (self.spotify if link[0] == "spotify" else self.youtube).resolve(
            link[1]
        )
        async with self.conductor.lock:
            item = self.queue.add(track, user, roles, event_id, redemption, owner)
            if item and item["status"] == "queued":
                try:
                    await self.conductor.continuation.attach()
                except Exception as e:
                    self.diag.add("spotify_playlist_attach", type(e).__name__)
        if self.conductor.native.enabled:
            await self.conductor.native.flush()
        if (
            self.conductor.enabled
            and not self.queue.state["current"]
            and item
            and item["status"] == "queued"
        ):

            async def advance():
                try:
                    await self.conductor.next(expected="")
                except Exception:
                    pass

            self.background(advance())
        return item

    async def chat(self, uid, login, mid, text, tags):
        parts = text.strip().split(None, 1)
        mapping = {v: k for k, v in self.settings.value["commands"].items()}
        if not parts:
            return False
        action = mapping.get(parts[0].lower())
        custom = next((c for c in self.settings.value["custom_commands"] if c["enabled"] and c["name"] == parts[0].lower()), None)
        if custom:
            action = "custom"
        if not action:
            return False
        now = time.monotonic()
        if mid in self.chat_seen:
            return True
        self.chat_seen[mid] = now
        if len(self.chat_seen) > 10000:
            self.chat_seen = {k: v for k, v in self.chat_seen.items() if now - v < 120}
        if now - self.chat_rate.get(uid, 0) < 3:
            return True
        self.chat_rate[uid] = now
        if len(self.chat_rate) > 10000:
            self.chat_rate = {k: v for k, v in self.chat_rate.items() if now - v < 120}
        arg = parts[1].strip() if len(parts) > 1 else ""
        prefix = "@" + login + " "
        try:
            if action == "custom":
                roles = await self.twitch.roles(uid, tags)
                allowed = {"everyone": set(roles), "vip": {"vip", "mod", "broadcaster"}, "mod": {"mod", "broadcaster"}}[custom["permission"]]
                if custom["permission"] != "everyone" and not allowed.intersection(roles):
                    raise ValueError("You do not have permission to use this command.")
                rate_key = (uid, custom["name"])
                if now - self.chat_rate.get(rate_key, float("-inf")) < custom["cooldown"]:
                    return True
                self.chat_rate[rate_key] = now
                current = self.conductor.display_current()
                t = current["track"] if current else {}
                from .reply_pool import choose_reply
                response = choose_reply(self.queue, custom).format(user=login, channel=self.settings.value["channel"], args=arg[:200],
                    song=t.get("title", "Nothing playing"), artist=", ".join(t.get("artists", [])),
                    platform=t.get("provider", ""), queue_count=self.queue.request_count())
            elif action == "request":
                item = await self.request_song(
                    arg,
                    {"id": uid, "login": login},
                    await self.twitch.roles(uid, tags),
                    event_id="chat:" + mid,
                )
                response = (
                    "Already received."
                    if not item
                    else f"{'Awaiting review' if item['status'] == 'review' else 'Queued'}: "
                    f"{item['track']['title']} — {', '.join(item['track']['artists']) or 'Unknown artist'} "
                    f"({'Spotify' if item['track']['provider'] == 'spotify' else 'YouTube'})."
                )
            elif action == "queue":
                response = "Queue: " + (
                    "; ".join(
                        f"{i + 1}. {x['track']['title']} [{x['id']}]"
                        for i, x in enumerate(self.queue.state["items"][:3])
                    )
                    or "empty"
                )
            elif action == "remove":
                async with self.conductor.lock:
                    mine = [
                        x for x in self.queue.state["items"] if x["user"]["id"] == uid
                    ]
                    ident = arg or (mine[-1]["id"] if mine else "")
                    self.queue.remove(ident, uid)
                response = "Your request was removed."
            elif action == "skip":
                roles = await self.twitch.roles(uid, tags)
                if not self.queue.rule(roles)["skip"]:
                    raise ValueError(
                        "You do not have skip permission. Try vote-to-skip."
                    )
                await self.conductor.next(manual=True)
                response = "Skipped."
            elif action == "vote":
                async with self.conductor.lock:
                    passed = self.queue.vote(uid)
                    votes = len(self.queue.state["votes"])
                    current_id = self.queue.state["current"]["id"]
                if passed:
                    await self.conductor.next(expected=current_id)
                response = (
                    "Vote passed; skipped."
                    if passed
                    else f"Skip votes: {votes}/{self.settings.value['votes_required']}."
                )
            else:
                c = self.conductor.display_current()
                response = (
                    f"Playing: {c['track']['title']} — {', '.join(c['track']['artists'])} ({c['track']['provider']})"
                    if c
                    else "Nothing is playing from the request queue."
                )
        except ValueError as e:
            response = str(e)
        self.bot.reply(mid, prefix + response)
        return True

    async def redemption(self, e):
        rid = e["id"]
        if str(e.get('status', '')).lower() == 'canceled':
            return
        reward = e.get("reward", {}).get("id", self.settings.value["reward_id"])
        if reward != self.settings.value["reward_id"]:
            return
        if "points:" + rid in self.queue.state["events"] or any(
            x["id"] == rid for x in self.queue.state["settlements"]
        ):
            return
        selected = self.twitch.selected_reward or {}
        if selected.get('id') == reward and e.get('reward', {}).get('title'):
            selected['title'] = e['reward']['title']
        r = {"id": rid, "reward": reward, "broadcaster": self.twitch.broadcaster,
             "manageable": selected.get('id') == reward and selected.get('manageable', False),
             "already_resolved": str(e.get('status', 'unfulfilled')).lower() != 'unfulfilled'}
        try:
            await self.request_song(
                e.get("user_input", ""),
                {"id": e["user_id"], "login": e["user_login"]},
                await self.twitch.roles(e["user_id"]),
                event_id="points:" + rid,
                redemption=r,
            )
        except Exception as err:
            async with self.conductor.lock:
                self.queue.settle({"redemption": r}, "CANCELED")
                self.queue.save()
            self.diag.add("request_failed", type(err).__name__)

    async def start_bot(self):
        if self.bot:
            raise ValueError("The bot is already running.")
        if not self.settings.value["channel"]:
            raise ValueError("Enter the Twitch channel and save first.")
        await self.twitch.prepare()
        c = {"channel": self.settings.value["channel"]}
        try:
            self.bot = StudioBot(c, self.twitch, studio=self)
            self.bot_tasks = [
                asyncio.create_task(self.bot.run()),
                asyncio.create_task(self.twitch.settlement_loop(self.queue)),
            ]
            if self.settings.value["points_enabled"]:
                if not self.settings.value["reward_id"]:
                    raise ValueError(
                        "Select a channel-point reward in Rewards first."
                    )
                self.twitch.selected_reward = await self.twitch.validate_reward(self.settings.value["reward_id"])
                self.bot_tasks.append(
                    asyncio.create_task(self.twitch.points(self.redemption))
                )
        except Exception:
            await self.stop_bot()
            raise

    async def stop_bot(self):
        for t in self.bot_tasks:
            t.cancel()
        await asyncio.gather(*self.bot_tasks, return_exceptions=True)
        self.bot_tasks = []
        self.bot = None
        self.twitch.points_status = "Disconnected"

    async def start_overlay_tunnel(self):
        if self.overlay_tunnel and self.overlay_tunnel.returncode is None:
            return self.overlay_public
        self.overlay_tunnel = await asyncio.create_subprocess_exec(
            "cloudflared",
            "tunnel",
            "--url",
            "http://127.0.0.1:8889",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

        async def consume():
            while line := await self.overlay_tunnel.stdout.readline():
                m = re.search(rb"https://[a-z0-9-]+\.trycloudflare\.com", line)
                if m:
                    self.overlay_public = m[0].decode()
            self.overlay_public = ""

        self.background(consume())
        for _ in range(100):
            if self.overlay_public:
                return self.overlay_public
            await asyncio.sleep(0.2)
        raise ValueError(
            "No tunnel URL yet. Check that cloudflared is installed and try again."
        )

    def state(self):
        return {
            "equalizer": self.equalizer.snapshot(),
            "version": __version__,
            "desktop": self.desktop is not None,
            "points": {"status": self.twitch.points_status, "error": self.twitch.points_error,
                       "reward": self.twitch.selected_reward},
            "settings": self.settings.public(),
            "moderation": self.moderation.snapshot(),
            "queue": self.queue.snapshot(),
            "playback": self.conductor.snapshot(),
            "spotify_queue": self.conductor.native.snapshot(),
            "connections": {
                "spotify": bool(self.vault.read().get("spotify")),
                "twitch": bool(self.vault.read().get("twitch")),
                "bot": self.bot.status if self.bot else "Stopped",
                "points": self.twitch.points_status,
                "youtube_player": self.player.last > 0 and time.monotonic() - self.player.last < 8 and (self.settings.value["youtube_player_mode"] != "chrome" or self.chrome.connected),
                "chrome_paired": bool(self.vault.read().get("chrome")),
                "chrome_connected": self.chrome.connected,
            },
            "widgets": {
                kind: "http://127.0.0.1:8889"
                + "/overlay/"
                + kind
                + "?key="
                + self.overlay_key
                for kind in ("now", "gradient", "queue")
            },
            "widgets_public": {kind: self.overlay_public + "/overlay/" + kind + "?key=" + self.overlay_key
                               for kind in ("now", "gradient", "queue")} if self.overlay_public else {},
            "diagnostics": self.diag.report(),
            "logs": self.diag.rows[-30:],
            "update_configured": not bool(self.updater.configuration_error),
            "update_configuration_error": self.updater.configuration_error,
        }

    async def cleanup(self):
        await self.moderation.close()
        for ws in list(self.audio_clients):
            await ws.close()
        await self.equalizer.close()
        with contextlib.suppress(Exception):
            await self.conductor.pause()
        await self.chrome.close()
        await self.stop_bot()
        if self.overlay_tunnel and self.overlay_tunnel.returncode is None:
            self.overlay_tunnel.terminate()
            await self.overlay_tunnel.wait()
        for t in list(self.tasks):
            t.cancel()
        await asyncio.gather(*list(self.tasks), return_exceptions=True)
        self.queue.db.close()


STUDIO_KEY = web.AppKey("studio", Studio)


@web.middleware
async def security(req, handler):
    app = req.app[STUDIO_KEY]
    host = req.host
    if host not in ("127.0.0.1:8888", "localhost:8888"):
        raise web.HTTPForbidden(text="Invalid host")
    origin = req.headers.get("Origin")
    if req.path == "/chrome/ws":
        if not extension_origin(origin):
            raise web.HTTPForbidden(text="Invalid extension origin")
        return await handler(req)
    if origin and origin not in ("http://127.0.0.1:8888", "http://localhost:8888"):
        raise web.HTTPForbidden(text="Invalid origin")
    if req.path.startswith("/api/") and not secrets.compare_digest(
        req.headers.get("X-NextUp-Key", ""), app.admin
    ):
        raise web.HTTPUnauthorized()
    try:
        result = await handler(req)
    except (ValueError, KeyError, TypeError) as e:
        result = web.json_response(
            {"error": str(e) if isinstance(e, ValueError) else "Invalid request."},
            status=400,
        )
    except web.HTTPException:
        raise
    except Exception as e:
        app.diag.add("request_failed", type(e).__name__)
        result = web.json_response(
            {"error": "Operation failed. Check Diagnostics."}, status=500
        )
    result.headers.update(
        {
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Content-Security-Policy": "default-src 'self'; script-src 'self' https://www.youtube.com; style-src 'self' 'unsafe-inline'; img-src 'self' https: data: blob: http://127.0.0.1:8889; frame-src 'self' http://127.0.0.1:8889 https:; font-src 'self' data: http://127.0.0.1:8889 https:; connect-src 'self' http://127.0.0.1:8889 ws://127.0.0.1:8889 wss://*.trycloudflare.com; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
        }
    )
    return result


async def api(req):
    s = req.app[STUDIO_KEY]
    op = req.match_info["op"]
    b = await req.json() if req.method == "POST" else dict(req.query)
    result = {}
    if op == "state":
        result = s.state()
    elif op == "moderator-create":
        result = s.moderation.create(b)
    elif op == "moderator-revoke":
        s.moderation.revoke(b.get("id"))
    elif op == "moderator-link":
        result = {"url": await s.moderation.start_tunnel()}
    elif op == "audio-apps":
        result = await s.equalizer.applications()
    elif op == "audio-source":
        if type(b.get("pid")) is not int or not isinstance(b.get("started"),str):raise ValueError("Select an application from the list.")
        await s.equalizer.choose(b["pid"],b["started"])
        result = s.equalizer.snapshot()
    elif op == "audio-retry":
        await s.equalizer.configure(force=True)
        result = s.equalizer.snapshot()
    elif op == "widget-remove":
        ident=b.get("id")
        rows=s.settings.value["widget_presets"]
        if not any(p["id"]==ident for p in rows):raise ValueError("This saved widget is already removed.")
        s.settings.save({"widget_presets":[p for p in rows if p["id"]!=ident]})
    elif op == "chrome-open":
        if not s.chrome.connected:
            raise ValueError("Pair and connect the NextUp extension in your browser first.")
        await s.chrome.ws.send_json({"type":"open"})
    elif op == "chrome-pair":
        result = {"code": s.chrome.pairing_code(), "expires_seconds": 180}
    elif op == "chrome-revoke":
        await s.chrome.revoke()
    elif op == "settings":
        if "spotify_follow_current_playlist" in b:
            s.conductor.reject_busy()
            if b["spotify_follow_current_playlist"] is True:
                b["fallback_enabled"] = False
                if s.settings.value["provider_mode"] == "youtube":
                    b.setdefault("provider_mode", "mixed")
        elif b.get("fallback_enabled") is True:
            b["spotify_follow_current_playlist"] = False
        if "spotify_native_queue" in b or "provider_mode" in b:
            if s.conductor.lock.locked():
                raise ValueError("Wait for playback to finish changing before switching queue modes.")
            if b.get("spotify_native_queue") is True:
                b.setdefault("provider_mode", "mixed")
        if "youtube_player_mode" in b and b["youtube_player_mode"] != s.settings.value["youtube_player_mode"]:
            c = s.queue.state["current"]
            if s.conductor.lock.locked() or (c and c["track"]["provider"] == "youtube"):
                raise ValueError("Finish or skip the current YouTube song before switching players.")
            if time.monotonic() - s.player.last < 8:
                await s.player.send("pause")
        if s.bot and any(
            k in b and b[k] != s.settings.value[k]
            for k in (
                "channel",
                "twitch_client_id",
                "points_enabled",
                "reward_id",
                "recognition_enabled",
            )
        ):
            raise ValueError(
                "Stop the bot before changing Twitch, points or recognition connections."
            )
        if not b.get("youtube_api_key"):
            b.pop("youtube_api_key", None)
        selected_reward = None
        if b.get('reward_id') and b['reward_id'] != s.settings.value['reward_id']:
            selected_reward = await s.twitch.validate_reward(b['reward_id'])
        s.settings.save(b)
        if "spotify_follow_current_playlist" in b:
            async with s.conductor.lock:
                current = s.queue.state["current"]
                if b["spotify_follow_current_playlist"] and current and current.get("fallback"):
                    # Release the managed fallback row, leave Spotify audio
                    # untouched and attach to the live playlist on the next poll.
                    s.queue.finish()
                    s.conductor.recovery = None
                    s.conductor.failed_item = None
                if not b["spotify_follow_current_playlist"] and current and current.get("native_playlist"):
                    s.queue.finish()
                    s.conductor.continuation.active = False
                    s.conductor.enabled = False
                pending = s.conductor.recovery
                if b["spotify_follow_current_playlist"] and pending and pending["item"].get("fallback"):
                    s.conductor.recovery = None
                    s.conductor.failed_item = None
                if b["spotify_follow_current_playlist"] and not s.queue.state["current"]:
                    if s.conductor.status != "Paused":
                        s.conductor.status = "Waiting for Spotify playlist"
                    s.conductor.error = ""
        if selected_reward is not None:
            s.twitch.selected_reward = selected_reward
        if b.get("require_approval") is True:
            async with s.conductor.lock:
                for item in s.queue.state["items"]:
                    if item["status"] == "queued" and not any(item.get(k) for k in ("owner_added", "reviewed", "spotify_delivery")):
                        item["status"] = "review"
                s.queue.save()
        if "compact_mode" in b and s.desktop is not None:
            await asyncio.to_thread(s.desktop.set_compact, s.settings.value["compact_mode"])
        if s.desktop is not None and any(k in b for k in ("theme", "theme_colors")):
            await asyncio.to_thread(s.desktop.refresh_window_theme)
        if any(k.startswith("fallback_") for k in b):
            s.conductor.fallback.invalidate()
            async def refresh_fallback_queue():
                async with s.conductor.lock:
                    try:
                        await s.conductor.fallback.replenish()
                    except Exception as e:
                        s.conductor.fallback.note = str(e)
            s.background(refresh_fallback_queue())
            if (s.conductor.fallback.enabled and not s.queue.state["current"]
                    and not s.queue.next_item() and (s.conductor.status in ("Stopped", "Queue empty", "Needs attention")
                         or (s.conductor.status == "Playing" and s.conductor.observed))):
                async def start_idle_fallback():
                    try:
                        await s.conductor.resume()
                    except Exception as e:
                        s.conductor.failed(e)
                s.background(start_idle_fallback())
        if any(k.startswith("widget_audio_") or k=="youtube_player_mode" for k in b):await s.equalizer.configure()
    elif op == "fallback-check":
        s.conductor.reject_busy()
        async with s.conductor.lock:
            tracks = await s.conductor.fallback.load(force=True)
            await s.conductor.fallback.replenish()
            result = {"message": s.conductor.fallback.note, "allowed": len(tracks),
                      "loaded": len(s.conductor.fallback.tracks)}
    elif op == "spotify-connect":
        result = {"url": s.spotify.connect()}
        if s.desktop is not None:
            await asyncio.to_thread(webbrowser.open, result["url"])
    elif op == "twitch-connect":
        result = await s.twitch.connect()
        if s.desktop is not None:
            await asyncio.to_thread(webbrowser.open, result["url"])
    elif op == "twitch-poll":
        result = await s.twitch.poll_login()
    elif op == "disconnect":
        provider = b["provider"]
        if provider not in ("spotify", "twitch"):
            raise ValueError("Invalid provider")
        if provider == "twitch":
            await s.stop_bot()
            s.twitch.identity = {}
            s.twitch.cache = {}
            s.twitch.pending = None
        else:
            c = s.queue.state["current"]
            if c and c["track"]["provider"] == "spotify":
                await s.conductor.pause()
                s.queue.finish()
            async with s.conductor.lock:
                for item in list(s.queue.state["items"]):
                    if item["track"]["provider"] == "spotify":
                        s.queue.remove(item["id"])
                s.queue.state["history"] = [
                    x
                    for x in s.queue.state["history"]
                    if x["track"]["provider"] != "spotify"
                ]
                s.queue.save()
        if provider == "spotify":
            s.conductor.fallback.invalidate()
            s.queue.state.pop("fallback_cursor", None)
            s.queue.state["fallback_cursors"] = {k:v for k,v in s.queue.state.get("fallback_cursors", {}).items() if not k.startswith("spotify:")}
            s.queue.save()
        s.vault.put(provider, None)
    elif op == "devices":
        result = await s.spotify.api("GET", "me/player/devices")
    elif op in ("search", "song-input"):
        text = b.get("text")
        if b.get("provider") not in ("spotify", "youtube") or not isinstance(text, str):
            raise ValueError("Choose a search provider and enter a song name or link.")
        text = text.strip()
        if not 1 <= len(text) <= 2048:
            raise ValueError("Enter a song name or a Spotify / YouTube link.")
        link = parse_link(text)
        if link and op == "song-input":
            # A complete link identifies a track; the picker is for name searches.
            result = {"item": await s.request_song(
                text, {"id": "owner", "login": "You"}, ["broadcaster"], owner=True
            )}
        elif link:
            result = {"tracks": [await (s.spotify if link[0] == "spotify" else s.youtube).resolve(link[1])]}
        else:
            if "://" in text or text.lower().startswith("spotify:"):
                raise ValueError("Use a Spotify track link or YouTube video link, not a playlist or channel link.")
            if len(text) > 200:
                raise ValueError("Enter a search, up to 200 characters.")
            result = {"tracks": await (s.spotify if b["provider"] == "spotify" else s.youtube).search(text)}
    elif op == "request":
        result = {
            "item": await s.request_song(
                b["url"], {"id": "owner", "login": "You"}, ["broadcaster"], owner=True
            )
        }
    elif op == "queue":
        async with s.conductor.lock:
            if b["action"] == "forget-spotify":
                item = next((x for x in s.queue.state["items"] if x["id"] == b["id"]), None)
                if not item:
                    raise ValueError("Queue item not found.")
                item.pop("spotify_delivery", None)
                s.queue.remove(item["id"])
                return web.json_response({"ok": True})
            if b["action"] == "clear" and any(x.get("spotify_delivery") for x in s.queue.state["items"]):
                raise ValueError("Remove sent songs in Spotify, then use Forget in NextUp. Spotify's queue cannot be cleared here.")
            if b["action"] == "remove":
                s.queue.remove(b["id"])
            elif b["action"] == "approve":
                s.queue.approve(b["id"])
            elif b["action"] == "reorder":
                s.queue.reorder(b["ids"])
            elif b["action"] == "clear":
                for x in list(s.queue.state["items"]):
                    if not x.get("fallback"):
                        s.queue.remove(x["id"])
            elif b["action"] == "new-session":
                s.queue.state["counts"] = {}
                s.queue.state["cooldowns"] = {}
                s.queue.save()
            else:
                raise ValueError("Unknown queue action")
    elif op == "playback":
        action = b["action"]
        if action == "next":
            await s.conductor.next(manual=bool(s.conductor.display_current() or s.conductor.failed_item or s.conductor.recovery))
        elif action == "pause":
            await s.conductor.pause()
        elif action == "resume":
            await s.conductor.resume()
        else:
            raise ValueError("Unknown playback action")
    elif op == "bot":
        async with s.service_lock:
            if b["action"] == "start":
                await s.start_bot()
            elif b["action"] == "stop":
                await s.stop_bot()
            else:
                raise ValueError("Unknown bot action")
    elif op == "rewards":
        result = {"rewards": await s.twitch.list_rewards()}
    elif op == "reward":
        if s.bot:
            raise ValueError('Stop the bot before creating a different song-request reward.')
        result = {"id": await s.twitch.create_reward(b.get('title', 'NextUp SongRequest'), b.get('cost'))}
    elif op == "playlists":
        result = await s.spotify.api("GET", "me/playlists", params={"limit": 50})
    elif op == "playlist":
        ident = b["id"]
        if not re.fullmatch("[A-Za-z0-9]{22}", ident):
            raise ValueError("Enter a Spotify playlist ID (22 characters).")
        result = {"tracks": await s.spotify.playlist(ident)}
    elif op in ("player-poll", "player-event") and s.settings.value["youtube_player_mode"] != "embedded":
        raise ValueError("Browser playback is selected. Close the embedded player.")
    elif op == "player-poll":
        result = s.bridge.poll(b["client"])
    elif op == "player-event":
        if b.get("client") != s.bridge.client:
            raise ValueError("Player session changed.")
        if b.get("event") == "ack":
            s.bridge.ack(b["client"], b.get("seq"), b.get("error", ""))
        elif b.get("event") == "ended":

            async def end():
                try:
                    await s.conductor.ended(b.get("track"))
                except Exception:
                    pass

            s.background(end())
        elif b.get("event") == "progress":
            c = s.queue.state["current"]
            value = b.get("seconds", 0)
            if (
                c
                and c["track"]["provider"] == "youtube"
                and c["track"]["id"] == b.get("track")
                and isinstance(value, (int, float))
                and 0 <= value <= 7200
            ):
                if (type(b.get("playing")) is bool and not b.get("ended")
                        and not s.bridge.command and not s.conductor.lock.locked()
                        and not s.conductor.error):
                    s.conductor.status = "Playing" if b["playing"] else "Paused"
                s.conductor.progress = value
        elif b.get("event") == "error":
            s.conductor.enabled = False
            s.conductor.status = "Needs attention"
            s.conductor.error = "YouTube playback failed. Review the player window."
            s.diag.add("player_lost", "YouTube error")
    elif op == "widget-save":
        result = s.widget_assets.save(s.settings, b.get("preset"), b.get("as_new", True) is True)
    elif op == "widget-export":
        preset = next((p for p in s.settings.value["widget_presets"] if p["id"] == b.get("id")), None)
        if preset is None: raise ValueError("Widget not found.")
        result = s.widget_assets.export(preset)
    elif op == "overlay-tunnel":
        result = {"url": await s.start_overlay_tunnel()}
    elif op == "analyze":
        result = {"findings": s.diag.analyze(b["text"])}
    elif op == "diagnostics":
        result = {
            "version": __version__,
            "findings": s.diag.report(),
            "events": s.diag.rows,
            "spotify_start": s.spotify.last_start_report,
            "build_label": os.environ.get("NEXTUP_BUILD_LABEL", "installed"),
            "playback_status": s.conductor.status,
        }
    elif op == "update-check":
        result = await s.updater.check()
    elif op == "update-stage":
        if s.bot or s.queue.state["current"]:
            raise ValueError(
                "Stop the bot and finish playback before staging an update."
            )
        try:
            result = await s.updater.stage()
        except Exception as e:
            s.diag.add("update_failed", type(e).__name__)
            raise
    elif op == "desktop-popout":
        if s.desktop is None:
            raise ValueError("Open the popout in the desktop app.")
        await asyncio.to_thread(s.desktop.open_popout)
    elif op == "desktop-minimize":
        if s.desktop is not None:
            await asyncio.to_thread(s.desktop.window.minimize)
    elif op == "desktop-player":
        if s.desktop is None:
            raise ValueError("The desktop player is available in the Windows app.")
        await asyncio.to_thread(s.desktop.open_player)
    elif op == "exit":
        s.stop_event.set()
    else:
        raise web.HTTPNotFound()
    return web.json_response(result)


async def callback(req):
    s = req.app[STUDIO_KEY]
    await s.spotify.callback(req.query.get("code", ""), req.query.get("state", ""))
    return web.Response(
        text="<h2>Spotify connected</h2><p>Return to your NextUp window. You can close this tab.</p>",
        content_type="text/html",
    )


async def page(req):
    name = {"/": "index.html", "/player": "player.html", "/popout": "index.html"}.get(req.path)
    if not name:
        raise web.HTTPNotFound()
    return web.FileResponse(ROOT / "studio/static" / name)


@web.middleware
async def readonly(req, handler):
    s = req.app[STUDIO_KEY]
    if not secrets.compare_digest(req.query.get("key", ""), s.overlay_key):
        raise web.HTTPUnauthorized()
    r = await handler(req)
    r.headers.update(
        {
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        }
    )
    return r


async def overlay_state(req):
    s = req.app[STUDIO_KEY]
    q = s.queue.state

    def clean(item):
        return (
            {"track": item["track"], "requester": item["user"]["login"]}
            if item
            else None
        )

    return web.json_response(
        {
            "current": clean(s.conductor.display_current()),
            "playback": {k:v for k,v in s.conductor.snapshot().items() if k != "current"},
            "colors": s.settings.value["theme_colors"],
            "equalizer": s.settings.value["widget_equalizer"],
            "equalizer_style": s.settings.value["widget_equalizer_style"],
            "branding": s.settings.value["widget_branding"],
            "presets": s.settings.value["widget_presets"],
            "items": [clean(x) for x in q["items"] if x["status"] == "queued"],
        }
    )


async def artwork_palette(req):
    s=req.app[STUDIO_KEY];current=s.conductor.display_current()
    art=current['track'].get('art','') if current else ''
    if not art or req.query.get('art')!=art:return web.json_response({'colors':[]})
    return web.json_response({'colors':await s.artwork_palette.get(art)})

async def audio_stream(req):
    s=req.app[STUDIO_KEY]
    if len(s.audio_clients)>=64:raise web.HTTPServiceUnavailable(text="Too many widget audio connections.")
    ws=web.WebSocketResponse(heartbeat=20,max_msg_size=1024)
    await ws.prepare(req);s.audio_clients.add(ws)
    try:
        while not ws.closed:
            sample=s.equalizer.snapshot(public=True)
            await asyncio.wait_for(ws.send_json(sample),2)
            try:
                message=await asyncio.wait_for(ws.receive(),.05 if sample["mode"]=="application" else .5)
                if message.type in (web.WSMsgType.CLOSE,web.WSMsgType.CLOSED,web.WSMsgType.ERROR):break
            except asyncio.TimeoutError:pass
    except (ConnectionError,RuntimeError,asyncio.TimeoutError):pass
    finally:
        s.audio_clients.discard(ws);await ws.close()
    return ws

async def overlay_page(req):
    if req.match_info["kind"] not in ("now", "gradient", "queue"):
        raise web.HTTPNotFound()
    page = (ROOT / "studio/static/overlay.html").read_text(encoding="utf-8")
    return web.Response(text=page.replace("__OVERLAY_KEY__", req.app[STUDIO_KEY].overlay_key), content_type="text/html")

async def widget_asset(req):
    s=req.app[STUDIO_KEY]
    try:path=s.widget_assets.path(req.match_info['ident'])
    except ValueError:raise web.HTTPNotFound()
    if not path.is_file():raise web.HTTPNotFound()
    return web.FileResponse(path)

async def widget_font(req):
    s=req.app[STUDIO_KEY]
    try:path=s.widget_assets.font_path(req.match_info['ident'],req.match_info['fmt'])
    except ValueError:raise web.HTTPNotFound()
    if not path.is_file():raise web.HTTPNotFound()
    return web.FileResponse(path,headers={'Content-Type':'font/'+req.match_info['fmt']})

async def widget_audio(req):
    return web.FileResponse(ROOT / "studio/static/widget-audio.js")

async def widget_v3_renderer(req):
    return web.FileResponse(ROOT / "studio/static/widget-v3.js")

async def widget_renderer(req):
    return web.FileResponse(ROOT / "studio/static/widget-renderer.js")


async def widget_singularity(req):
    return web.FileResponse(ROOT / "studio/static/widget-singularity.js")

async def widget_horizon_texture(req):
    return web.FileResponse(ROOT / "studio/static/event-horizon.png")


def admin_app(studio):
    app = web.Application(middlewares=[security], client_max_size=42 * 1024 * 1024)
    app[STUDIO_KEY] = studio
    app.router.add_get("/", page)
    app.router.add_get("/player", page)
    app.router.add_get("/popout", page)
    app.router.add_get("/chrome/ws", studio.chrome.handle)
    app.router.add_get("/callback/spotify", callback)
    # GET is reserved for read-only operations. Mutations require authenticated POST.
    for op in ("state", "diagnostics", "audio-apps"):

        async def read(req, op=op):
            req.match_info["op"] = op
            return await api(req)

        app.router.add_get("/api/" + op, read)
    app.router.add_post("/api/{op}", api)
    app.router.add_static("/static/", ROOT / "studio/static", show_index=False)
    return app


def overlay_app(studio):
    app = web.Application(middlewares=[readonly])
    app[STUDIO_KEY] = studio
    app.router.add_get("/overlay/{kind}", overlay_page)
    app.router.add_get("/state", overlay_state)
    app.router.add_get("/widget-assets/{ident}.png", widget_asset)
    app.router.add_get("/widget-renderer.js", widget_renderer)
    app.router.add_get("/widget-v3.js", widget_v3_renderer)
    app.router.add_get("/art-palette", artwork_palette)
    app.router.add_get("/widget-singularity.js", widget_singularity)
    app.router.add_get("/event-horizon.png", widget_horizon_texture)
    app.router.add_get("/widget-audio.js", widget_audio)
    app.router.add_get("/audio", audio_stream)
    app.router.add_get("/widget-fonts/{ident}.{fmt}", widget_font)
    return app


async def run(open_browser=True, on_ready=None, desktop=None):
    started = time.perf_counter()
    with InstanceLock(HOME):
        async with ClientSession(timeout=ClientTimeout(total=30)) as session:
            s = Studio(session)
            s.desktop = desktop
            admin = web.AppRunner(admin_app(s), access_log=None)
            over = web.AppRunner(overlay_app(s), access_log=None)
            try:
                await admin.setup()
                await over.setup()
                await web.TCPSite(admin, "127.0.0.1", 8888).start()
                await web.TCPSite(over, "127.0.0.1", 8889).start()
                await s.moderation.start_server()
                s.background(s.conductor.monitor())
                url = "http://127.0.0.1:8888/#" + s.admin
                print(
                    "NextUp is running. Use Tools > Exit in the dashboard to stop."
                )
                if on_ready is not None:
                    on_ready(url, s)
                elif open_browser:
                    webbrowser.open(url)
                else:
                    print("Dashboard URL:", url)
                print(f"[startup] NextUp local services ready in {time.perf_counter()-started:.2f}s")
                s.background(s.equalizer.configure())
                await s.stop_event.wait()
            finally:
                await s.cleanup()
                await admin.cleanup()
                await over.cleanup()


def main():
    try:
        asyncio.run(run("--no-browser" not in sys.argv))
    except KeyboardInterrupt:
        pass
    except ValueError as e:
        print(str(e))
        raise SystemExit(1)
    except OSError:
        print(
            "Could not start. Close another NextUp instance or free ports 8888 and 8889."
        )
        raise SystemExit(1)


if __name__ == "__main__":
    main()
