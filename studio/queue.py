"""Persistent queue and request policy; no provider or network dependencies."""

import copy, json, secrets, sqlite3, time, unicodedata
from .music_policy import check_music_track


def norm(s):
    return unicodedata.normalize("NFKC", s).strip().casefold()


class Queue:
    def __init__(self, path, settings):
        self.settings = settings
        self.db = sqlite3.connect(path)
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY, body TEXT)"
        )
        row = self.db.execute("SELECT body FROM state WHERE id=1").fetchone()
        self.state = (
            json.loads(row[0])
            if row
            else {
                "items": [],
                "current": None,
                "history": [],
                "cooldowns": {},
                "counts": {},
                "events": {},
                "votes": [],
                "settlements": [],
            }
        )
        # Never resume playback blindly following a crash/restart.
        if self.state["current"] and (self.state["current"].get("fallback") or self.state["current"].get("native_playlist")):
            self.state["current"] = None
        self.state["items"] = [x for x in self.state["items"] if not x.get("fallback")]
        if self.state["current"]:
            self.state["current"]["status"] = "queued"
            self.state["items"].insert(0, self.state["current"])
            self.state["current"] = None
        for item in self.state["items"]:
            # Old queue files have no verified YouTube category. Keep the rows
            # visible, but never grandfather them into the music-only queue.
            try:
                check_music_track(item["track"])
            except ValueError as e:
                item.update(status="blocked", reason=str(e))
                self.settle(item, "CANCELED")
                continue
            if item.get("owner_added") and item["status"] in ("queued", "review"):
                try:
                    self.check_track(item["track"], reviewed=True)
                except ValueError as e:
                    item.update(status="blocked", reason=str(e))
                else:
                    item.update(reviewed=True, status="queued")
        self._saved_body = None
        self.save()

    def save(self):
        if not self.state["items"]:
            self.state["manual_order"] = False
        body = json.dumps(self.state)
        if body == getattr(self, "_saved_body", None):
            return
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO state VALUES(1,?)", (body,)
            )

        self._saved_body = body

    def request_count(self):
        return sum(not x.get("fallback") and x.get("status") in ("queued", "review") for x in self.state["items"])

    def rule(self, roles):
        rules = self.settings.value["roles"]
        valid = [r for r in roles if r in rules] or ["viewer"]
        precedence = ("viewer", "tier1", "vip", "tier2", "tier3", "mod", "broadcaster")
        return rules[max(valid, key=precedence.index)]

    def check_request_method(self, roles, via_points=False, owner=False):
        if owner:
            return
        method = self.rule(roles).get('request_method', 'both')
        if method == 'disabled':
            raise ValueError('Song requests are not enabled for your role.')
        if method == 'points' and not via_points:
            if not self.settings.value['points_enabled'] or not self.settings.value['reward_id']:
                raise ValueError('Your role requires channel points, but channel-point requests are currently unavailable.')
            raise ValueError('Please use the channel-point song-request reward. Chat song requests are not enabled for your role.')
        if method == 'chat' and via_points:
            raise ValueError('Your role uses chat requests. Use ' + self.settings.value['commands']['request'] + ' with a song link.')

    def check_track(self, t, reviewed=False):
        check_music_track(t)
        c = self.settings.value
        if t["provider"] not in ("spotify", "youtube") or t["duration"] <= 0:
            raise ValueError(
                "Live, unavailable, or unknown-duration tracks are not accepted."
            )
        if t["duration"] > c["max_seconds"]:
            raise ValueError(
                f"Song exceeds the {c['max_seconds'] // 60}m {c['max_seconds'] % 60}s limit."
            )
        names = {norm(x) for x in t.get("artists", []) + t.get("artist_ids", [])}
        if names & {norm(x) for x in c["blocked_artists"]}:
            raise ValueError("This artist/channel is blocked.")
        if {norm(t["id"]), norm(t["url"])} & {norm(x) for x in c["blocked_tracks"]}:
            raise ValueError("This song is blocked.")
        if c["block_explicit"] and t.get("explicit") is True:
            raise ValueError("Explicit songs are blocked.")
        return (
            c["block_explicit"]
            and c["review_unknown"]
            and t.get("explicit") is None
            and not reviewed
        )

    def add(self, track, user, roles, event_id=None, redemption=None, owner=False):
        c = self.settings.value
        self.check_request_method(roles, redemption is not None, owner)
        if event_id and event_id in self.state["events"]:
            return None
        if not c["requests_enabled"] and not owner:
            raise ValueError("Song requests are closed.")
        if c["queue_limit"] and self.request_count() >= c["queue_limit"]:
            raise ValueError("The viewer request queue is full. Playlist songs do not count toward this limit.")
        if c["provider_mode"] not in ("mixed", track["provider"]):
            raise ValueError("This playback source is disabled.")
        review = self.check_track(track, reviewed=owner) or (c["require_approval"] and not owner)
        rule = self.rule(roles)
        uid = user["id"]
        now = time.time()
        active = self.state["items"] + (
            [self.state["current"]] if self.state["current"] else []
        )
        if any(
            not x.get("fallback") and x["track"]["id"] == track["id"]
            and x["track"]["provider"] == track["provider"]
            for x in active
        ):
            raise ValueError("That song is already queued or playing.")
        if not owner:
            if sum(x["user"]["id"] == uid for x in active) >= rule["pending"]:
                raise ValueError("You have reached your active-request limit.")
            if rule["session"] and self.state["counts"].get(uid, 0) >= rule["session"]:
                raise ValueError("You have reached your session request limit.")
            if now - self.state["cooldowns"].get(uid, 0) < rule["cooldown"]:
                raise ValueError("Please wait for your request cooldown.")
        item = {
            "id": secrets.token_hex(8),
            "track": copy.deepcopy(track),
            "user": user,
            "owner_added": owner,
            "reviewed": bool(owner),
            "status": "review" if review else "queued",
            "created": now,
            "redemption": redemption,
        }
        first_fallback = next((i for i, x in enumerate(self.state["items"]) if x.get("fallback")), len(self.state["items"]))
        self.state["items"].insert(first_fallback, item)
        self.state["cooldowns"][uid] = now
        self.state["counts"][uid] = self.state["counts"].get(uid, 0) + 1
        if event_id:
            self.state["events"][event_id] = now
        # Old chat IDs expire, while point-redemption IDs remain in the settlement ledger.
        self.state["events"] = {
            k: v for k, v in self.state["events"].items() if v > now - 7 * 86400
        }
        self.save()
        return item

    def remove(self, ident, uid=None):
        item = next((x for x in self.state["items"] if x["id"] == ident), None)
        if not item:
            raise ValueError("Queue item not found.")
        if item.get("fallback"):
            raise ValueError("Fallback songs follow the saved playlist. Use Skip for the current song or change fallback settings.")
        if item.get("spotify_delivery"):
            raise ValueError("This request was sent to Spotify. Remove it in Spotify, then use Forget in NextUp.")
        if uid and item["user"]["id"] != uid:
            raise ValueError("You can only remove your own requests.")
        self.state["items"].remove(item)
        self.settle(item, "CANCELED")
        self.save()
        return item

    def settle(self, item, status):
        r = item.get("redemption")
        if r and not any(x["id"] == r["id"] for x in self.state["settlements"]):
            manual = r.get('manageable') is False
            already_resolved = r.get('already_resolved', False)
            self.state["settlements"].append({**r, "status": status,
                "done": manual or already_resolved, "manual": manual and not already_resolved})

    def approve(self, ident):
        item = next((x for x in self.state["items"] if x["id"] == ident), None)
        if not item:
            raise ValueError("Queue item not found.")
        self.check_track(item["track"], reviewed=True)
        item["reviewed"] = True
        item["status"] = "queued"
        self.save()

    def reorder(self, ids):
        if any(x.get("spotify_delivery") for x in self.state["items"]):
            raise ValueError("Reorder sent songs in Spotify's queue. Their order cannot be changed here.")
        items = {x["id"]: x for x in self.state["items"]}
        if len(ids) != len(items) or set(ids) != set(items):
            raise ValueError("Queue changed; reload before reordering.")
        requested = [items[i] for i in ids if not items[i].get("fallback")]
        fallback = [x for x in self.state["items"] if x.get("fallback")]
        self.state["items"] = requested + fallback
        self.state["manual_order"] = True
        self.save()

    def next_item(self):
        ordered = sorted(self.state["items"], key=lambda x: bool(x.get("fallback")))
        for item in ordered:
            if item.get("fallback"):
                c = self.settings.value
                playlist = c["fallback_playlist"] if c["fallback_provider"] == "spotify" else c["fallback_youtube_playlist"]
                if not c["fallback_enabled"] or item["track"]["provider"] != c["fallback_provider"] or item.get("fallback_playlist") != playlist:
                    continue
            if self.settings.value["provider_mode"] not in (
                "mixed",
                item["track"]["provider"],
            ):
                continue
            if item["status"] != "queued":
                continue
            try:
                if self.check_track(item["track"], item.get("reviewed", False)):
                    item["status"] = "review"
                    continue
            except ValueError as e:
                item["status"] = "blocked"
                item["reason"] = str(e)
                self.settle(item, "CANCELED")
                continue
            self.save()
            return item
        self.save()
        return None

    def activate(self, item):
        if item in self.state["items"]:
            self.state["items"].remove(item)
        self.state["current"] = item
        item["status"] = "playing"
        self.state["votes"] = []
        self.save()

    def finish(self):
        item = self.state["current"]
        if item:
            self.settle(item, "FULFILLED")
            self.state["history"].insert(0, item)
            self.state["history"] = self.state["history"][:100]
        self.state["current"] = None
        self.state["votes"] = []
        self.save()

    def vote(self, uid):
        if not self.settings.value["vote_skip_enabled"]:
            raise ValueError("Vote-to-skip is disabled.")
        if not self.state["current"]:
            raise ValueError("Nothing is playing.")
        if uid in self.state["votes"]:
            raise ValueError("You already voted for this song.")
        self.state["votes"].append(uid)
        self.save()
        return len(self.state["votes"]) >= self.settings.value["votes_required"]

    def snapshot(self):
        return copy.deepcopy(
            {k: self.state[k] for k in ("items", "current", "history", "votes")}
        )
