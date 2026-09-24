import os
import re
import gzip
import io
import xml.etree.ElementTree as ET
import requests

EPG_URL = "https://iptvx.one/epg/epg_lite.xml.gz"
EPG_PLAYLIST_URL = 'url-tvg="https://iptvx.one/epg/epg_lite.xml.gz"'

PLAYLISTS = [
    "iptvorg_rus.m3u",
    "romaxa55_russia.m3u",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

SYNONYMS = {
    "channel one": ["первый канал", "первый", "1tv", "ort", "pervii", "pervyy"],
    "russia 1": ["россия 1", "russia1", "rtr1", "ртр1", "rossiya 1"],
    "russia 24": ["россия 24", "russia24", "rossiya 24"],
    "russia k": ["россия к", "russia k", "kultura", "культура"],
    "ntv": ["нтв", "ntv russia"],
    "tnt": ["тнт", "tnt russia"],
    "sts": ["стс", "sts russia"],
    "tv3": ["тв3", "тв-3", "tv-3"],
    "ren tv": ["рен тв", "rentv", "ren-tv"],
    "match tv": ["матч", "match", "matchtv"],
    "karusel": ["карусель"],
    "mir": ["мир", "mir 24", "мир 24"],
    "zvezda": ["звезда", "zvezda tv"],
    "tvc": ["твц", "tv centr", "тв центр"],
    "domashniy": ["домашний"],
    "pyatnica": ["пятница", "пятница!"],
    "che": ["че", "che!"],
    "2x2": ["2na2", "2+2", "2x2"],
    "360": ["360°", "360 news", "360 новости", "360° news"],
    "amedia": ["амедиа"],
    "tv1000": ["тв1000", "tv 1000"],
    "viasat": ["виасат"],
    "discovery": ["дискавери"],
    "natgeo": ["national geographic"],
    "travelxp": ["travel xp", "travel-xp-4k"],
    "trace sport": ["trace sport stars"],
    "okko": ["окко", "okko sport", "okko чемпионат", "okko-chemp"],
}


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


def find_by_synonyms(normalized, name_to_id):
    for syn_key, syn_list in SYNONYMS.items():
        candidates = [syn_key] + syn_list
        for cand in candidates:
            if cand in normalized:
                for syn in candidates:
                    if syn in name_to_id:
                        return name_to_id[syn]
    return None


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


def fix_playlist(filepath, name_to_id):
    if not os.path.exists(filepath):
        print("Not found: " + filepath)
        return 0, 0

    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()

    lines = text.splitlines()
    fixed = 0
    total = 0
    skipped_existing = 0
    new_lines = []

    for line in lines:
        if line.startswith("#EXTM3U"):
            new_lines.append("#EXTM3U " + EPG_PLAYLIST_URL)
            continue
        if line.startswith("#EXTINF"):
            m = re.search(r'tvg-id="([^"]*)"', line)
            if m and m.group(1).strip():
                skipped_existing += 1
                new_lines.append(line)
                continue

            total += 1
            name = extract_name(line)
            key = normalize(name)
            epg_id = name_to_id.get(key)
            if not epg_id:
                epg_id = find_by_synonyms(key, name_to_id)
            if epg_id:
                new_line = re.sub(r'tvg-id="[^"]*"', 'tvg-id="' + epg_id + '"', line, count=1)
                if 'tvg-id="' not in new_line:
                    new_line = line.replace("#EXTINF:-1", '#EXTINF:-1 tvg-id="' + epg_id + '"', 1)
                if new_line != line:
                    fixed += 1
                new_lines.append(new_line)
            else:
                new_lines.append(line)
            continue
        new_lines.append(line)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines))

    print(filepath + ": fixed " + str(fixed) + " / " + str(total) + " (skipped existing: " + str(skipped_existing) + ")")
    return fixed, total


def main():
    data = download_epg()
    name_to_id = parse_epg(data)

    for pl in PLAYLISTS:
        fix_playlist(pl, name_to_id)


main()
