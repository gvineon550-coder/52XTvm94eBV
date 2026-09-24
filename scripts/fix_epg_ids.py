import os
import re
import gzip
import io
import xml.etree.ElementTree as ET
import requests

EPG_URL = "https://iptvx.one/epg/epg_lite.xml.gz"
EPG_PLAYLIST_URL = 'url-tvg="https://iptvx.one/epg/epg_lite.xml.gz"'
SUGGESTIONS_FILE = "epg_suggestions.txt"

PLAYLISTS = [
    "iptvorg_rus.m3u",
    "romaxa55_russia.m3u",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

ALIASES = {}


def normalize(name):
    if not name:
        return ""
    n = name.lower().strip()
    n = re.sub(r'\([^)]*\)', '', n)
    n = re.sub(r'\[[^\]]*\]', '', n)
    n = re.sub(r'\b(hd|fhd|uhd|sd|4k)\b', '', n)
    n = re.sub(r'\s+', ' ', n).strip()
    n = n.replace('ё', 'е')
    return n


def search_similar(key, epg_keys):
    if not key:
        return []
    words = [w for w in key.split() if len(w) >= 4]
    if not words:
        words = [w for w in key.split() if len(w) >= 3]
    if not words:
        return []
    found = []
    for epg_key in epg_keys:
        for w in words:
            if w in epg_key:
                found.append(epg_key)
                break
        if len(found) >= 5:
            break
    return found


def download_epg():
    print("Downloading EPG: " + EPG_URL)
    r = requests.get(EPG_URL, headers=HEADERS, timeout=120)
    r.raise_for_status()
    print("Downloaded " + str(len(r.content)) + " bytes (compressed)")
    with gzip.open(io.BytesIO(r.content), "rb") as f:
        data = f.read()
    print("Uncompressed: " + str(len(data)) + " bytes")
    return data


def parse_epg(data):
    print("Parsing EPG...")
    name_to_id = {}
    count = 0
    for event, elem in ET.iterparse(io.BytesIO(data), events=("end",)):
        if elem.tag == "channel":
            ch_id = elem.get("id")
            if not ch_id:
                elem.clear()
                continue
            for dn in elem.findall("display-name"):
                text = dn.text
                if text:
                    key = normalize(text)
                    if key and key not in name_to_id:
                        name_to_id[key] = ch_id
            count += 1
            if count % 500 == 0:
                print("  parsed " + str(count) + " channels")
            elem.clear()
    print("Total EPG channels: " + str(count) + ", names: " + str(len(name_to_id)))
    return name_to_id


def extract_name(extinf):
    return extinf.rsplit(",", 1)[-1].strip() if "," in extinf else extinf


def fix_playlist(filepath, name_to_id, all_suggestions):
    if not os.path.exists(filepath):
        print("Not found: " + filepath)
        return 0, 0

    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    lines = text.splitlines()
    fixed = 0
    total = 0
    new_lines = []
    epg_keys = list(name_to_id.keys())

    for line in lines:
        if line.startswith("#EXTM3U"):
            new_lines.append("#EXTM3U " + EPG_PLAYLIST_URL)
            continue
        if line.startswith("#EXTINF"):
            total += 1
            name = extract_name(line)
            key = normalize(name)
            epg_id = name_to_id.get(key)
            if not epg_id:
                epg_id = ALIASES.get(key)
            if epg_id:
                new_line = re.sub(r'tvg-id="[^"]*"', 'tvg-id="' + epg_id + '"', line, count=1)
                if 'tvg-id="' not in new_line:
                    new_line = line.replace("#EXTINF:-1", '#EXTINF:-1 tvg-id="' + epg_id + '"', 1)
                if new_line != line:
                    fixed += 1
                new_lines.append(new_line)
            else:
                new_lines.append(line)
                variants = search_similar(key, epg_keys)
                all_suggestions.append({
                    "playlist": filepath,
                    "name": name,
                    "key": key,
                    "variants": variants,
                })
            continue
        new_lines.append(line)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines))

    print(filepath + ": fixed " + str(fixed) + " / " + str(total))
    return fixed, total


def save_suggestions(suggestions, name_to_id):
    with open(SUGGESTIONS_FILE, "w", encoding="utf-8") as f:
        f.write("# EPG Suggestions\n")
        f.write("# Формат: НАШ КАНАЛ -> ВАРИАНТЫ в EPG\n")
        f.write("# Смотри варианты, выбирай правильный, присылай для добавления в ALIASES\n\n")
        for s in suggestions:
            f.write("[" + s["playlist"] + "] " + s["name"] + "\n")
            if s["variants"]:
                for v in s["variants"]:
                    epg_id = name_to_id.get(v, "?")
                    f.write("    variant: " + v + "  (id: " + epg_id + ")\n")
            else:
                f.write("    no variants found\n")
            f.write("\n")
    print("Saved " + SUGGESTIONS_FILE + ": " + str(len(suggestions)) + " channels without match")


def main():
    data = download_epg()
    name_to_id = parse_epg(data)

    all_suggestions = []
    for pl in PLAYLISTS:
        fix_playlist(pl, name_to_id, all_suggestions)

    save_suggestions(all_suggestions, name_to_id)


main()
