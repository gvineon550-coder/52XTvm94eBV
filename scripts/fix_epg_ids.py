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
    new_lines = []

    for line in lines:
        if line.startswith("#EXTINF"):
            total += 1
            name = extract_name(line)
            key = normalize(name)
            epg_id = name_to_id.get(key)
            if epg_id:
                new_line = re.sub(r'tvg-id="[^"]*"', 'tvg-id="' + epg_id + '"', line, count=1)
                if 'tvg-id="' not in new_line:
                    new_line = line.replace("#EXTINF:-1", '#EXTINF:-1 tvg-id="' + epg_id + '"', 1)
                if new_line != line:
                    fixed += 1
                new_lines.append(new_line)
            else:
                new_lines.append(line)
        elif line.startswith("#EXTM3U"):
            if "url-tvg" not in line:
                line = line.rstrip() + " " + EPG_PLAYLIST_URL
            new_lines.append(line)
        else:
            new_lines.append(line)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines))

    print(filepath + ": fixed " + str(fixed) + " / " + str(total))
    return fixed, total


def main():
    data = download_epg()
    name_to_id = parse_epg(data)

    for pl in PLAYLISTS:
        fix_playlist(pl, name_to_id)


main()
