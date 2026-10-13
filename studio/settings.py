"""Versioned configuration lives outside installed application versions."""

import copy, json, os, re, math
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from .storage import write_private
from . import customization

ROOT = Path(__file__).resolve().parents[1]
HOME = Path(
    os.environ.get(
        "NEXTUP_HOME",
        Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share"))
        / "NextUp",
    )
)
DATA = HOME / "userdata"
ROLES = ("viewer", "tier1", "tier2", "tier3", "vip", "mod", "broadcaster")
DEFAULTS = {
    "theme": "dark",
    "compact_mode": True,
    "sidebar_collapsed": False,
    "provider_mode": "mixed",
    "youtube_player_mode": "embedded",
    "requests_enabled": True,
    "max_seconds": 360,
    "block_explicit": True,
    "review_unknown": True,
    "require_approval": False,
    "moderators_enabled": False,
    "blocked_artists": [],
    "blocked_tracks": [],
    "skip_enabled": True,
    "vote_skip_enabled": True,
    "votes_required": 3,
    "queue_limit": 100,
    "hide_playlist": True,
    "spotify_client_id": "",
    "spotify_device": "",
    "spotify_device_name": "",
    "spotify_native_queue": False,
    "spotify_follow_current_playlist": False,
    "fallback_enabled": False,
    "fallback_playlist": "",
    "fallback_provider": "spotify",
    "fallback_youtube_playlist": "",
    "fallback_shuffle": False,
    "fallback_repeat": True,
    "youtube_api_key": "",
    "channel": "",
    "twitch_client_id": "",
    "points_enabled": False,
    "reward_id": "",
    "reward_cost": 500,
    "recognition_enabled": False,
    "theme_colors": {},
    "custom_commands": [],
    "widget_equalizer": True,
    "widget_equalizer_style": "bars",
    "widget_branding": True,
    "widget_presets": [],
    "widget_audio_mode": "animation",
    "widget_audio_pid": 0,
    "widget_audio_started": "",
    "widget_audio_name": "",
    "widget_audio_gain": 1.0,
    "roles": {
        r: {
            "pending": n,
            "session": 0,
            "cooldown": c,
            "skip": r in ("mod", "broadcaster"),
            "request_method": "both",
        }
        for r, n, c, p in [
            ("viewer", 2, 60, 0),
            ("tier1", 3, 45, 0),
            ("tier2", 5, 30, 10),
            ("tier3", 8, 15, 20),
            ("vip", 5, 30, 10),
            ("mod", 10, 5, 30),
            ("broadcaster", 100, 0, 40),
        ]
    },
    "commands": {
        "request": "!sr",
        "queue": "!queue",
        "remove": "!remove",
        "skip": "!skip",
        "vote": "!voteskip",
        "playing": "!np",
    },
}
SECRET_KEYS = {"youtube_api_key"}


def validate(raw):
    c = copy.deepcopy(DEFAULTS)
    c.update(raw)
    for k, v in DEFAULTS.items():
        if isinstance(v, bool) and type(c[k]) is not bool:
            raise ValueError(k + " must be true or false.")
    for k, lo, hi in [
        ("max_seconds", 10, 7200),
        ("votes_required", 1, 1000),
        ("queue_limit", 0, 10000),
        ("reward_cost", 1, 1000000),
    ]:
        if type(c[k]) is not int or not lo <= c[k] <= hi:
            raise ValueError(f"{k} must be {lo}–{hi}.")
    if c["theme"] not in ("light", "dark") or c["provider_mode"] not in (
        "spotify",
        "youtube",
        "mixed",
    ):
        raise ValueError("Invalid appearance or provider mode.")
    if c["youtube_player_mode"] not in ("embedded", "chrome"):
        raise ValueError("Invalid YouTube player mode.")
    for k in (
        "channel",
        "twitch_client_id",
        "spotify_client_id",
        "spotify_device",
        "spotify_device_name",
        "youtube_api_key",
        "reward_id",
    ):
        if not isinstance(c[k], str) or len(c[k]) > 200:
            raise ValueError("Invalid " + k)
    value = c["fallback_playlist"]
    if not isinstance(value, str) or len(value) > 500:
        raise ValueError("Enter a Spotify playlist link, URI or ID.")
    value = value.strip()
    if value.startswith("spotify:playlist:"):
        value = value.removeprefix("spotify:playlist:")
    elif value.startswith("https://"):
        u = urlparse(value)
        match = re.fullmatch(r"/(?:intl-[a-zA-Z-]+/)?playlist/([A-Za-z0-9]{22})/?", u.path)
        if u.netloc != "open.spotify.com" or not match:
            raise ValueError("Use a full open.spotify.com/playlist link.")
        value = match[1]
    if value and not re.fullmatch(r"[A-Za-z0-9]{22}", value):
        raise ValueError("Enter a Spotify playlist link, URI or 22-character ID.")
    c["fallback_playlist"] = value
    if c["fallback_provider"] not in ("spotify", "youtube"):
        raise ValueError("Choose Spotify or YouTube as the fallback platform.")
    yt = c["fallback_youtube_playlist"]
    if not isinstance(yt, str) or len(yt) > 500:
        raise ValueError("Enter a YouTube playlist link or ID.")
    yt = yt.strip()
    if yt.startswith("https://"):
        u = urlparse(yt)
        if u.netloc not in ("www.youtube.com", "youtube.com", "music.youtube.com", "m.youtube.com", "youtu.be"):
            raise ValueError("Use a YouTube playlist link.")
        yt = parse_qs(u.query).get("list", [""])[0]
        if not yt:
            raise ValueError("The YouTube link needs a playlist (list=) ID.")
    if yt and not re.fullmatch(r"[A-Za-z0-9_-]{10,100}", yt):
        raise ValueError("Enter a valid YouTube playlist link or ID.")
    c["fallback_youtube_playlist"] = yt
    if c["fallback_enabled"] and not (value if c["fallback_provider"] == "spotify" else yt):
        raise ValueError("Choose a playlist for the selected fallback platform before enabling fallback.")
    c["channel"] = c["channel"].strip().lower().lstrip("#")
    if c["channel"] and not re.fullmatch(r"[a-z0-9_]{1,25}", c["channel"]):
        raise ValueError("Use the Twitch channel login, without a URL.")
    for k in ("blocked_artists", "blocked_tracks"):
        if (
            not isinstance(c[k], list)
            or len(c[k]) > 1000
            or any(not isinstance(x, str) or len(x) > 200 for x in c[k])
        ):
            raise ValueError("Invalid block list.")
        c[k] = [x.strip() for x in c[k] if x.strip()]
    if not isinstance(c["roles"], dict) or set(c["roles"]) != set(ROLES):
        raise ValueError("All role rules are required.")
    for rule in c["roles"].values():
        rule.pop("priority", None)
        rule.setdefault('request_method', 'both')
        if rule['request_method'] not in ('both', 'points', 'chat', 'disabled'):
            raise ValueError('Invalid request method for role.')
        for k, lo, hi in [
            ("pending", 1, 500),
            ("session", 0, 10000),
            ("cooldown", 0, 3600),
        ]:
            if type(rule.get(k)) is not int or not lo <= rule[k] <= hi:
                raise ValueError("Invalid role rule: " + k)
        if type(rule.get("skip")) is not bool:
            raise ValueError("Skip privilege must be true/false.")
    if not isinstance(c["commands"], dict) or set(c["commands"]) != set(
        DEFAULTS["commands"]
    ):
        raise ValueError("All command mappings are required.")
    commands = list(c["commands"].values())
    if any(
        not isinstance(x, str)
        or not re.fullmatch(r"![a-z][a-z0-9_]{0,24}", x)
        for x in commands
    ) or len(set(commands)) != len(commands):
        raise ValueError(
            "Commands must be unique and lowercase."
        )
    if c["widget_audio_mode"] not in ("animation","application","follow"):
        raise ValueError("Choose animation or application audio for the equalizer.")
    if type(c["widget_audio_pid"]) is not int or not 0 <= c["widget_audio_pid"] <= 0xffffffff:
        raise ValueError("Invalid audio application.")
    token=c["widget_audio_started"]
    if not isinstance(token,str) or (token and (not token.isascii() or not token.isdigit() or len(token)>20 or int(token)>2**64-1)):
        raise ValueError("Invalid audio application identity.")
    if not isinstance(c["widget_audio_name"],str) or len(c["widget_audio_name"])>100:
        raise ValueError("Invalid audio application name.")
    gain=c["widget_audio_gain"]
    if type(gain) not in (int,float) or not math.isfinite(gain) or not .25 <= gain <= 4:
        raise ValueError("Equalizer sensitivity must be 0.25 to 4.")
    customization.equalizer_style(c["widget_equalizer_style"])
    c["recognition_enabled"] = False
    c["theme_colors"] = customization.colors(c["theme_colors"]) if c["theme_colors"] else {}
    c["custom_commands"] = customization.commands(c["custom_commands"], commands)
    if not isinstance(c["widget_presets"], list):
        raise ValueError("Widget presets must be a list.")
    c["widget_presets"] = [customization.preset(v) for v in c["widget_presets"]]
    return c


class Settings:
    def __init__(self, path=None):
        self.path = path or DATA / "studio.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.value = validate(
            json.loads(self.path.read_text()) if self.path.exists() else {}
        )

    def save(self, patch):
        value = validate({**self.value, **patch})
        write_private(self.path, value)
        self.value = value

    def public(self):
        return {k: v for k, v in self.value.items() if k not in SECRET_KEYS} | {
            "youtube_key_set": bool(self.value["youtube_api_key"])
        }
