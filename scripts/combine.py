import os
import re
from datetime import datetime, timezone, timedelta

MSK = timezone(timedelta(hours=3))

OUTPUT_FILE = "all_channels.m3u"
EPG_URL = "https://iptvx.one/epg/epg_lite.xml.gz"

SOURCES = [
    "playlist.m3u",
    "romaxa55_russia.m3u",
    "iptvorg_rus.m3u",
    "ufotv_playlist.m3u",
]

BAD_PORTS = {":8080", ":8000", ":9999", ":8888"}
BAD_DOMAINS = (
    ".xyz", ".tk", ".ml", ".cf", ".ga",
    "cinerama.uz",
    "tinyurl.com", "bit.ly", "goo.gl", "clck.ru", "is.gd", "t.co", "ow.ly",
)

KIDS_KEYWORDS = [
    # Латиница
    "kids", "kid", "junior", "jr", "baby", "cartoon", "toon",
    "nickelodeon", "nick", "nicktoons", "disney", "boomerang",
    "gulli", "tiji", "davinci", "da vinci", "carousel",
    "mult", "multimania", "multilandia",
    # Кириллица
    "детск", "детcк", "мульт", "малыш", "карусель", "ребенок", "ребёнок",
    "солнце",
]

KIDS_EXCEPTIONS = [
    "start air", "start world",
]


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


def get_group(extinf):
    m = re.search(r'group-title="([^"]*)"', extinf, re.IGNORECASE)
    return m.group(1).lower() if m else ""


def get_quality(extinf):
    name = get_name(extinf).lower()
    m = re.search(r'(\d{3,4})p', name)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    if "fhd" in name or "1080" in name:
        return 1080
    if "hd" in name or "720" in name:
        return 720
    if "sd" in name:
        return 480
    return 720


def base_name(extinf):
    name = get_name(extinf)
    name = re.sub(r'\(?\s*(FHD|UHD|HD|SD|4K)\s*\)?', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\(?\s*\d{3,4}p\s*\)?', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\[[^\]]*\]', '', name)
    name = re.sub(r'\s+', ' ', name).strip().lower()
    return name


def is_bad_url(url):
    u = url.lower()
    if re.match(r'^https?://\d+\.\d+\.\d+\.\d+', u):
        return True
    for port in BAD_PORTS:
        if port in u:
            return True
    for dom in BAD_DOMAINS:
        if dom + "/" in u or dom + ":" in u or dom + "?" in u:
            return True
    return False


def is_kids(extinf):
    name = base_name(extinf)
    group = get_group(extinf)

    for exc in KIDS_EXCEPTIONS:
        if exc in name:
            return False

    for kw in KIDS_KEYWORDS:
        if len(kw) <= 4:
            pattern = r'(?<![a-zа-яё0-9])' + re.escape(kw) + r'(?![a-zа-яё0-9])'
            if re.search(pattern, name):
                return True
        else:
            if kw in name:
                return True

    for kw in ["kids", "детск", "мульт", "cartoon", "junior"]:
        if kw in group:
            return True

    return False


def main():
    all_channels = []
    source_stats = {}

    for src in SOURCES:
        if not os.path.exists(src):
            print("Skip (not found): " + src)
            continue
        with open(src, "r", encoding="utf-8") as f:
            text = f.read()
        channels = parse_m3u(text)
        source_stats[src] = len(channels)
        all_channels.extend(channels)
        print(src + ": " + str(len(channels)) + " channels")

    print("Total before filter: " + str(len(all_channels)))

    non_kids = [ch for ch in all_channels if not is_kids(ch["extinf"])]
    dropped_kids = len(all_channels) - len(non_kids)
    print("After kids filter: " + str(len(non_kids)) + " (dropped kids: " + str(dropped_kids) + ")")

    best = {}
    for ch in non_kids:
        key = base_name(ch["extinf"])
        q = get_quality(ch["extinf"])
        clean = 0 if is_bad_url(ch["url"]) else 1
        score = (clean, q)

        if key not in best or score > best[key][0]:
            best[key] = (score, ch)

    deduped = [v[1] for v in best.values()]
    dropped_dups = len(non_kids) - len(deduped)
    print("After dedup: " + str(len(deduped)) + " (dropped dups: " + str(dropped_dups) + ")")

    def sort_key(ch):
        group = get_group(ch["extinf"]) or "zzz"
        return (group, get_name(ch["extinf"]).lower())

    deduped.sort(key=sort_key)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append('#EXTM3U url-tvg="' + EPG_URL + '" x-tvg-url="' + EPG_URL + '"')
    lines.append("# Combined from " + str(len(SOURCES)) + " sources | Updated: " + now)
    lines.append("# Total: " + str(len(deduped)) + " unique channels | Kids removed")
    lines.append("")
    for ch in deduped:
        lines.append(ch["extinf"])
        lines.append(ch["url"])
        lines.append("")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("Saved " + OUTPUT_FILE)
    print("")
    print("Source breakdown:")
    for src, count in source_stats.items():
        print("  " + src + ": " + str(count))


main()
