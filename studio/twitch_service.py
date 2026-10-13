"""Twitch device login, verified roles, chat and durable point redemptions."""

import asyncio, json, re, time
from urllib.parse import urlsplit
from .providers import request, ServiceError
from .chat_transport import TwitchBot, parse_irc


class Twitch:
    SCOPES = "chat:read chat:edit channel:manage:redemptions channel:read:subscriptions moderation:read channel:read:vips"

    def __init__(self, session, settings, vault, diag):
        self.session, self.settings, self.vault, self.diag = (
            session,
            settings,
            vault,
            diag,
        )
        self.pending = None
        self.identity = {}
        self.validated = 0
        self.lock = asyncio.Lock()
        self.broadcaster = ""
        self.cache = {}
        self.points_status = "Disconnected"
        self.points_error = ""
        self.selected_reward = None

    async def connect(self):
        client = self.settings.value["twitch_client_id"]
        if not re.fullmatch("[A-Za-z0-9]{10,100}", client):
            raise ValueError("Enter a Public Twitch Client ID and save first.")
        d = await request(
            self.session,
            "POST",
            "https://id.twitch.tv/oauth2/device",
            data={"client_id": client, "scopes": self.SCOPES},
        )
        self.pending = {
            **d,
            "client": client,
            "expires_at": time.time() + d["expires_in"],
            "next": time.monotonic() + max(5, d.get("interval", 5)),
        }
        return {"url": d["verification_uri"], "code": d["user_code"]}

    async def poll_login(self):
        p = self.pending
        if not p:
            return {"status": "idle"}
        if time.time() > p["expires_at"]:
            self.pending = None
            raise ValueError("Twitch sign-in expired. Try again.")
        if time.monotonic() < p["next"]:
            return {"status": "pending"}
        p["next"] = time.monotonic() + max(5, p.get("interval", 5))
        try:
            t = await request(
                self.session,
                "POST",
                "https://id.twitch.tv/oauth2/token",
                data={
                    "client_id": p["client"],
                    "device_code": p["device_code"],
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "scopes": self.SCOPES,
                },
            )
        except ServiceError as e:
            if e.code == "authorization_pending":
                return {"status": "pending"}
            if e.code == "slow_down":
                p["interval"] = p.get("interval", 5) + 5
                return {"status": "pending"}
            raise
        t.update(client_id=p["client"], expires_at=time.time() + t["expires_in"])
        self.vault.put("twitch", t)
        self.pending = None
        self.validated = 0
        await self.valid()
        return {"status": "connected", "login": self.identity["login"]}

    async def valid(self):
        async with self.lock:
            t = self.vault.read().get("twitch")
            if not t or t["client_id"] != self.settings.value["twitch_client_id"]:
                raise ValueError("Connect Twitch first.")
            if time.time() > t["expires_at"] - 120:
                n = await request(
                    self.session,
                    "POST",
                    "https://id.twitch.tv/oauth2/token",
                    data={
                        "client_id": t["client_id"],
                        "grant_type": "refresh_token",
                        "refresh_token": t["refresh_token"],
                    },
                )
                t.update(n)
                t["expires_at"] = time.time() + n["expires_in"]
                self.vault.put("twitch", t)
                self.validated = 0
            if time.monotonic() - self.validated > 1800 or not self.identity:
                self.identity = await request(
                    self.session,
                    "GET",
                    "https://id.twitch.tv/oauth2/validate",
                    headers={"Authorization": "OAuth " + t["access_token"]},
                )
                if self.identity.get("client_id") != t["client_id"]:
                    raise ValueError("Twitch app mismatch; reconnect.")
                self.validated = time.monotonic()
            return t["access_token"], self.identity["login"]

    async def api(self, method, path, **kwargs):
        token, _ = await self.valid()
        return await request(
            self.session,
            method,
            "https://api.twitch.tv/helix/" + path,
            headers={
                "Authorization": "Bearer " + token,
                "Client-Id": self.settings.value["twitch_client_id"],
            },
            **kwargs,
        )

    async def prepare(self):
        await self.valid()
        data = await self.api(
            "GET", "users", params={"login": self.settings.value["channel"]}
        )
        if not data.get("data"):
            raise ValueError("Twitch channel not found.")
        self.broadcaster = data["data"][0]["id"]
        self.cache = {}

    async def roles(self, uid, tags=None):
        if uid == self.broadcaster:
            return ["broadcaster"]
        roles = ["viewer"]
        tags = tags or {}
        badges = dict(
            x.split("/", 1) for x in tags.get("badges", "").split(",") if "/" in x
        )
        if "moderator" in badges or tags.get("mod") == "1":
            roles.append("mod")
        if "vip" in badges:
            roles.append("vip")
        if "subscriber" in badges:
            roles.append("tier1")
        if self.identity.get("user_id") != self.broadcaster:
            return roles
        cached = self.cache.get(uid)
        if cached and time.monotonic() - cached[0] < 60:
            return list(set(roles + cached[1]))
        verified = []
        for path, param, role in [
            ("subscriptions", "user_id", "subscriber"),
            ("moderation/moderators", "user_id", "mod"),
            ("channels/vips", "user_id", "vip"),
        ]:
            try:
                d = await self.api(
                    "GET", path, params={"broadcaster_id": self.broadcaster, param: uid}
                )
                if d.get("data"):
                    verified.append(
                        {"1000": "tier1", "2000": "tier2", "3000": "tier3"}.get(
                            d["data"][0].get("tier"), "tier1"
                        )
                        if role == "subscriber"
                        else role
                    )
            except ServiceError as e:
                if e.status not in (401, 403):
                    raise
        if len(self.cache) > 10000:
            self.cache.clear()
        self.cache[uid] = (time.monotonic(), verified)
        return list(set(roles + verified))

    async def list_rewards(self):
        await self.prepare()
        if self.identity['user_id'] != self.broadcaster:
            raise ValueError('Sign in with the channel owner account to select rewards.')
        params = {'broadcaster_id': self.broadcaster}
        all_rewards = await self.api('GET', 'channel_points/custom_rewards', params=params)
        owned = await self.api('GET', 'channel_points/custom_rewards',
                               params={**params, 'only_manageable_rewards': 'true'})
        manageable = {r['id'] for r in owned.get('data', [])}
        rewards = [{k: r.get(k) for k in ('id', 'title', 'cost', 'is_user_input_required',
                     'is_enabled', 'is_paused', 'should_redemptions_skip_request_queue')}
                   | {'manageable': r['id'] in manageable} for r in all_rewards.get('data', [])]
        self.selected_reward = next((r for r in rewards if r['id'] == self.settings.value['reward_id']), None)
        return rewards

    async def validate_reward(self, ident):
        rewards = await self.list_rewards()
        reward = next((r for r in rewards if r['id'] == ident), None)
        if not reward:
            raise ValueError('That reward is no longer on this channel. Refresh Twitch rewards and select it again.')
        if not reward['is_user_input_required']:
            raise ValueError('Enable "Require Viewer to Enter Text" for this reward on Twitch, then refresh rewards.')
        return reward

    async def create_reward(self, title='NextUp SongRequest', cost=None):
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 45:
            raise ValueError('Reward name must contain 1–45 characters.')
        cost = self.settings.value['reward_cost'] if cost is None else cost
        if type(cost) is not int or not 1 <= cost <= 1000000:
            raise ValueError('Reward cost must be 1–1000000 points.')
        await self.prepare()
        if self.identity['user_id'] != self.broadcaster:
            raise ValueError('Connect the channel owner to create a channel-point reward.')
        d = await self.api('POST', 'channel_points/custom_rewards',
            params={'broadcaster_id': self.broadcaster}, json={
                'title': title.strip(), 'cost': cost, 'is_user_input_required': True,
                'prompt': 'Paste a Spotify track or YouTube video link. Rejected requests are refunded.',
                'should_redemptions_skip_request_queue': False,
            })
        reward = d['data'][0]
        self.settings.save({'reward_id': reward['id'], 'reward_cost': cost})
        self.selected_reward = {**reward, 'manageable': True}
        return reward['id']

    async def reconcile_redemptions(self, on_redemption):
        # History access is restricted to rewards created by this Client ID.
        if not self.selected_reward or not self.selected_reward['manageable']:
            return
        cursor = None
        try:
            while True:
                params = {'broadcaster_id': self.broadcaster,
                          'reward_id': self.selected_reward['id'],
                          'status': 'UNFULFILLED', 'first': 50}
                if cursor:
                    params['after'] = cursor
                data = await self.api('GET', 'channel_points/custom_rewards/redemptions', params=params)
                for event in data.get('data', []):
                    await on_redemption(event)
                cursor = data.get('pagination', {}).get('cursor')
                if not cursor:
                    break
        except asyncio.CancelledError:
            raise
        except Exception:
            self.diag.add('points_history', 'History recovery unavailable; live redemptions remain connected.')
            self.points_error = 'Could not recover earlier redemptions. Live requests are still being received.'

    async def settlement_loop(self, queue):
        while True:
            await asyncio.sleep(5)
            for row in queue.state["settlements"]:
                if row["done"] or row.get("manual"):
                    continue
                try:
                    await self.api(
                        "PATCH",
                        "channel_points/custom_rewards/redemptions",
                        params={
                            "broadcaster_id": row["broadcaster"],
                            "reward_id": row["reward"],
                            "id": row["id"],
                        },
                        json={"status": row["status"]},
                    )
                    row["done"] = True
                    queue.save()
                except Exception as e:
                    if getattr(e, 'status', None) == 403:
                        row.update(done=True, manual=True, note='Complete or refund this redemption in Twitch.')
                        queue.save()
                        self.diag.add('points_settlement', 'Twitch denied automatic settlement. Review in Twitch.')
                        continue
                    if getattr(e, "status", None) == 400:
                        try:
                            current = await self.api(
                                "GET",
                                "channel_points/custom_rewards/redemptions",
                                params={
                                    "broadcaster_id": row["broadcaster"],
                                    "reward_id": row["reward"],
                                    "id": row["id"],
                                },
                            )
                            if current.get("data") and current["data"][0]["status"] in (
                                "FULFILLED",
                                "CANCELED",
                            ):
                                row["done"] = True
                                row["resolved_status"] = current["data"][0]["status"]
                                queue.save()
                                continue
                        except Exception:
                            pass
                    self.diag.add("points_settlement", type(e).__name__)
                    break

    async def points(self, on_redemption):
        url = "wss://eventsub.wss.twitch.tv/ws"
        handoff = None
        while True:
            old = None
            reconcile_task = None
            try:
                await self.prepare()
                if self.identity["user_id"] != self.broadcaster:
                    raise ValueError(
                        "Channel points require the channel owner account."
                    )
                self.selected_reward = await self.validate_reward(self.settings.value['reward_id'])
                self.points_error = ''
                ws = await self.session.ws_connect(url, heartbeat=None, timeout=20)
                while True:
                    msg = await asyncio.wait_for(ws.receive(), timeout=45)
                    if msg.type.name != "TEXT":
                        raise ConnectionError("EventSub closed")
                    d = json.loads(msg.data)
                    kind = d["metadata"]["message_type"]
                    payload = d["payload"]
                    if kind == "session_welcome":
                        if old:
                            await old.close()
                            old = None
                        if not handoff:
                            await self.api(
                                "POST",
                                "eventsub/subscriptions",
                                json={
                                    "type": "channel.channel_points_custom_reward_redemption.add",
                                    "version": "1",
                                    "condition": {
                                        "broadcaster_user_id": self.broadcaster,
                                        "reward_id": self.settings.value["reward_id"],
                                    },
                                    "transport": {
                                        "method": "websocket",
                                        "session_id": payload["session"]["id"],
                                    },
                                },
                            )
                        handoff = None
                        self.points_status = "Connected"
                        if reconcile_task is None:
                            reconcile_task = asyncio.create_task(self.reconcile_redemptions(on_redemption))
                    elif kind == "session_reconnect":
                        newurl = payload["session"]["reconnect_url"]
                        parts = urlsplit(newurl)
                        if (
                            parts.scheme != "wss"
                            or parts.hostname != "eventsub.wss.twitch.tv"
                        ):
                            raise ValueError("Invalid Twitch reconnect URL")
                        old = ws
                        handoff = True
                        ws = await self.session.ws_connect(newurl, timeout=20)
                    elif kind == "notification":
                        event = payload['event']
                        if event.get('reward', {}).get('id') == self.settings.value['reward_id']:
                            await on_redemption(event)
                    elif kind == "revocation":
                        raise ValueError("Twitch revoked channel point access.")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.points_status = "Disconnected; retrying"
                self.points_error = str(e)[:240] if isinstance(e, ValueError) else 'Twitch connection failed. Check the broadcaster sign-in and selected reward.' 
                self.diag.add("points_connection", type(e).__name__)
            finally:
                if reconcile_task is not None:
                    reconcile_task.cancel()
                    await asyncio.gather(reconcile_task, return_exceptions=True)
                if old:
                    await old.close()
                if "ws" in locals():
                    await ws.close()
            handoff = None
            await asyncio.sleep(15)


class StudioBot(TwitchBot):
    def __init__(self, *args, studio, **kwargs):
        super().__init__(*args, **kwargs)
        self.studio = studio

    async def receive_loop(self, reader, writer, bot_login):
        while True:
            raw = await asyncio.wait_for(reader.readline(), 360)
            if not raw:
                return
            tags, prefix, command, params, trailing = parse_irc(
                raw.decode("utf-8", "replace").rstrip("\r\n")
            )
            if command == "PING":
                writer.write(f"PONG :{trailing}\r\n".encode())
                await writer.drain()
            elif command == "RECONNECT":
                return
            elif command == "ROOMSTATE":
                self.status = "Connected to Twitch"
            elif command == "NOTICE":
                self.studio.diag.add(
                    "twitch_connection",
                    "Twitch sent a notice; check account/channel permissions.",
                )
            elif (
                command == "PRIVMSG"
                and params
                and params[0].lower() == "#" + self.channel
            ):
                login = prefix.split("!", 1)[0].lower()
                uid = tags.get("user-id", "")
                mid = tags.get("id", "")
                if (
                    not re.fullmatch("[a-z0-9_]{1,25}", login)
                    or not re.fullmatch(r"\d{1,30}", uid)
                    or not mid
                ):
                    continue
                head = trailing.strip().split(" ", 1)[0].lower()
                if head not in self.studio.settings.value[
                    "commands"
                ].values() and head not in [c["name"] for c in self.studio.settings.value["custom_commands"]]:
                    continue
                if len(self.work) >= 64:
                    continue
                task = asyncio.create_task(
                    self.dispatch(uid, login, mid, trailing, tags)
                )
                self.work.add(task)
                task.add_done_callback(self.work.discard)

    async def dispatch(self, uid, login, mid, text, tags):
        try:
            if await self.studio.chat(uid, login, mid, text, tags):
                return
        except Exception as e:
            self.studio.diag.add("request_failed", type(e).__name__)
