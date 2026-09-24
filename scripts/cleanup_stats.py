import os
import re
import json
from datetime import datetime, timezone

STATS_FILES = [
    "romaxa55_stats.json",
    "iptvorg_stats.json",
    "ufotv_stats.json",
]

PLAYLIST_FILES = [
    "playlist.m3u",
    "romaxa55_russia.m3u",
    "iptvorg_rus.m3u",
    "ufotv_playlist.m3u",
    "all_channels.m3u",
]

MAX_AGE_DAYS = 90


def parse_m3u(text):
    channels = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("#EXTINF"):
            extinf = lines[i].strip()
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j].strip().startswith("#")):
                j += 1
            if j < len(lines):
                channels.append({"extinf": extinf, "url": lines[j].strip()})
                i = j
        i += 1
    return channels


def get_name(extinf):
    return extinf.rsplit(",", 1)[-1].strip() if "," in extinf else extinf


def base_name(extinf):
    name = get_name(extinf)
    name = re.sub(r'\(?\s*(FHD|UHD|HD|SD|4K)\s*\)?', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\(?\s*\d{3,4}p\s*\)?', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\[[^\]]*\]', '', name)
    name = re.sub(r'\s+', ' ', name).strip().lower()
    return name


def load_playlist_names():
    names = set()
    for pl in PLAYLIST_FILES:
        if not os.path.exists(pl):
            continue
        with open(pl, "r", encoding="utf-8") as f:
            for ch in parse_m3u(f.read()):
                names.add(base_name(ch["extinf"]))
    return names


def cleanup_stats(path, valid_names):
    if not os.path.exists(path):
        return 0, 0

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    original = len(data)
    now = datetime.now(timezone.utc)

    cleaned = {}
    for name, entry in data.items():
        if name in valid_names:
            cleaned[name] = entry
            continue

        last_check_str = entry.get("last_check", "")
        try:
            last_check_dt = datetime.strptime(last_check_str, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
            age_days = (now - last_check_dt).days
            if age_days <= MAX_AGE_DAYS:
                cleaned[name] = entry
        except Exception:
            pass

    with open(path, "w", encoding="utf-8") as f:
        json.dump(cleaned, f, ensure_ascii=False, indent=2)

    removed = original - len(cleaned)
    return original, removed


def main():
    valid_names = load_playlist_names()
    print("Valid names in playlists: " + str(len(valid_names)))

    for path in STATS_FILES:
        original, removed = cleanup_stats(path, valid_names)
        kept = original - removed
        print(path + ": " + str(original) + " -> " + str(kept) + " (removed " + str(removed) + ")")


main()
