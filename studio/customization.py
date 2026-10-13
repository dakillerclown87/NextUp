"""Validated data-only themes, commands and widget presets; no executable uploads."""
import re, hashlib, json
from string import Formatter
COLORS = {"bg":"#080f19", "panel":"#111c29", "raised":"#1b2938", "sidebar":"#090f19",
          "text":"#f5f7fb", "muted":"#a4b2c5", "line":"#2a3849", "accent":"#19cee4",
          "accent2":"#d23eea", "danger":"#ff7b95", "ink":"#06111b"}
VARIABLES = {"user", "channel", "args", "song", "artist", "platform", "queue_count"}

def colors(value):
    if not isinstance(value, dict) or set(value) - set(COLORS):
        raise ValueError("Unknown theme color.")
    if any(not isinstance(v, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", v) for v in value.values()):
        raise ValueError("Use a six-digit hex color such as #19CEE4.")
    return {**COLORS, **value}

def commands(value, reserved):
    if not isinstance(value, list):
        raise ValueError("Custom commands must be a list.")
    seen = set(reserved)
    for row in value:
        if not isinstance(row, dict): raise ValueError("Invalid custom command.")
        name, reply = row.get("name", ""), row.get("reply", "")
        if not isinstance(name, str) or not re.fullmatch(r"![a-z][a-z0-9_]{0,24}", name) or name in seen:
            raise ValueError("Custom commands need unique names that do not replace built-in commands.")
        seen.add(name)
        if not isinstance(reply, str) or not reply.strip() or "\x00" in reply or any(len(line) > 350 for line in reply.splitlines()):
            raise ValueError("Enter one reply per line, up to 350 characters each.")
        try:
            for _, field, fmt, conversion in Formatter().parse(reply):
                if field is not None and (field not in VARIABLES or fmt or conversion):
                    raise ValueError("Invalid reply variable.")
        except ValueError:
            raise ValueError("Use supported reply variables only: " + ", ".join(sorted(VARIABLES))) from None
        if type(row.get("enabled")) is not bool or type(row.get("cooldown")) is not int or not 0 <= row["cooldown"] <= 3600:
            raise ValueError("Invalid custom command cooldown or toggle.")
        if row.get("permission") not in ("everyone", "vip", "mod"):
            raise ValueError("Invalid command permission.")
    return value

def equalizer_style(value):
    if value not in ("bars", "rounded", "mirror", "led", "circle-bars", "circle-wave", "orb", "circle-dots", "particle-sphere"):
        raise ValueError("Choose a supported equalizer style.")
    return value

def equalizer_response(value):
    import math
    if not isinstance(value, dict):
        raise ValueError("Equalizer response must be an object.")
    result = {}
    for name, default, lo, hi in (("sensitivity",1,.25,4),("attack_ms",45,5,250),("release_ms",220,40,1000),("bass",0,0,200)):
        v = value.get(name, default)
        if type(v) not in (int,float) or not math.isfinite(v) or not lo <= v <= hi:
            raise ValueError(f"Invalid equalizer {name}: choose {lo}–{hi}.")
        result[name] = v
    return result

def preset(value):
    if not isinstance(value, dict) or value.get("format") not in ("nextup-widget-v1", "nextup-widget-v2", "nextup-widget-v3"):
        raise ValueError("Select a NextUp widget preset JSON file.")
    name = value.get("name", "")
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
        raise ValueError("Widget name must be 1–60 characters.")
    if value.get("layout") not in ("spectrum", "gradient", "queue"):
        raise ValueError("Invalid widget layout.")
    if type(value.get("equalizer")) is not bool:
        raise ValueError("Invalid equalizer toggle.")
    ident = value.get("id") or hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]
    if not isinstance(ident, str) or not re.fullmatch("[a-f0-9]{16}", ident):
        raise ValueError("Invalid widget identity.")
    result = {"id":ident, "format":value["format"], "name":name.strip(), "layout":value["layout"],
            "equalizer":value["equalizer"], "equalizer_style":equalizer_style(value.get("equalizer_style", "bars")), "colors":colors(value.get("colors", {})), "equalizer_response":equalizer_response(value.get("equalizer_response", {}))}

    source = value.get("equalizer_color_source", "custom")
    if source not in ("custom", "artwork"):
        raise ValueError("Choose custom or album artwork equalizer colors.")
    result["equalizer_color_source"] = source
    if "label" in value:
        label = value["label"]
        if not isinstance(label, str) or len(label) > 80 or any(ord(c) < 32 or ord(c) == 127 for c in label):
            raise ValueError("Widget heading must be one line, up to 80 characters.")
        result["label"] = label
    if value["format"] == "nextup-widget-v2":
        from .widget_design import design
        result.update(design(value))
    if value["format"] == "nextup-widget-v3":
        from .widget_v3 import design
        result.update(design(value))
    return result
