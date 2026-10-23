"""Persisted user profile (~/.config/kbm-tg700/profile.json)."""
import json
import os

CONFIG_DIR = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "kbm-tg700")
PROFILE_PATH = os.path.join(CONFIG_DIR, "profile.json")


def default_profile():
    return {
        "model": "TG700",
        "macros": [],       # [{"name": str, "repeat": int, "events": [[code, down, mouse, delay], ...]}]
        "bindings": {},     # {"row,col": {"type": "key"|"macro"|"disabled", "value": int}}
    }


def load():
    try:
        with open(PROFILE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return default_profile()
    profile = default_profile()
    profile.update(data)
    return profile


def save(profile):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    tmp = PROFILE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(profile, f, indent=2, ensure_ascii=False)
    os.replace(tmp, PROFILE_PATH)
