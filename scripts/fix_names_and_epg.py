import os
import re
import gzip
import io
import xml.etree.ElementTree as ET
import requests

EPG_URL = "https://iptvx.one/epg/epg_lite.xml.gz"
PLAYLIST = "all_channels.m3u"
EPG_PLAYLIST_URL = 'url-tvg="https://iptvx.one/epg/epg_lite.xml.gz"'
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# URL-паттерны: НЕ трогаем эти каналы (kinowalk, rutube, нтв-сериалы)
SKIP_URL_PATTERNS = [
    "kinowalk.hopto.org",
    "bl.rutube.ru",
    "cdn-dvr.ntv.ru",
]

# Ручные исключения: имена, которые НЕ переименовывать (если автопоиск ошибся)
FORCE_SKIP = [
    "мир",     # слишком общее
    "360°",    # разные 360
]


def normalize(name):
    """Приводит название к единому виду для поиска."""
    if not name:
        return ""
    n = name.lower().strip()
    n = n.replace('ё', 'е')
    n = re.sub(r'\([^)]*\)', '', n)
    n = re.sub(r'\[[^\]]*\]', '', n)
    n = re.sub(r'\b(hd|fhd|uhd|sd|4k|1080p|720p|576p|480p|1080i|576i|480i)\b', '', n)
    n = re.sub(r'[\u2500-\u27bf\u2b00-\u2bff]', '', n)   # убираем разные символы (ℂℂ и т.п.)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def download_epg():
    print("Downloading EPG: " + EPG_URL)
    r = requests.get(EPG_URL, headers=HEADERS, timeout=180)
    r.raise_for_status()
    print("Downloaded " + str(len(r.content)) + " bytes (compressed)")
    with gzip.open(io.BytesIO(r.content), "rb") as f:
        data = f.read()
    print("Uncompressed: " + str(len(data)) + " bytes")
    return data


def build_epg_db(data):
    """Словарь: нормализованное имя -> (tvg_id, оригинальное имя)."""
    epg_db = {}
    count = 0
    print("Parsing EPG...")
    for event, elem in ET.iterparse(io.BytesIO(data), events=("end",)):
        if elem.tag == "channel":
            ch_id = elem.get("id")
            if not ch_id:
                elem.clear()
                continue
            for dn in elem.findall("display-name"):
                if dn.text:
                    key = normalize(dn.text)
                    if key and key not in epg_db:
                        epg_db[key] = (ch_id, dn.text.strip())
            count += 1
            if count % 1000 == 0:
                print("  parsed " + str(count) + " channels")
            elem.clear()
    print("Total EPG channels: " + str(count) + ", unique names: " + str(len(epg_db)))
    return epg_db


def get_name(extinf):
    return extinf.rsplit(",", 1)[-1].strip() if "," in extinf else extinf


def base_name(extinf):
    name = get_name(extinf)
    name = re.sub(r'\(?\s*(FHD|UHD|HD|SD|4K)\s*\)?', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\(?\s*\d{3,4}p\s*\)?', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\[[^\]]*\]', '', name)
    return re.sub(r'\s+', ' ', name).strip().lower()


def is_skip_url(url):
    u = url.lower()
    for p in SKIP_URL_PATTERNS:
        if p in u:
            return True
    return False


def is_force_skip(name):
    n = name.lower().strip()
    for s in FORCE_SKIP:
        if s in n:
            return True
    return False


def set_name_in_line(line, new_name):
    parts = line.rsplit(",", 1)
    if len(parts) == 2:
        return parts[0] + "," + new_name
    return line


def set_tvg_id_in_line(line, tvg_id):
    if 'tvg-id="' in line:
        return re.sub(r'tvg-id="[^"]*"', 'tvg-id="' + tvg_id + '"', line, count=1)
    return line.replace("#EXTINF:-1", '#EXTINF:-1 tvg-id="' + tvg_id + '"', 1)


def main():
    if not os.path.exists(PLAYLIST):
        print("Файл не найден: " + PLAYLIST)
        return

    data = download_epg()
    epg_db = build_epg_db(data)

    if not epg_db:
        print("EPG база пуста, выходим.")
        return

    with open(PLAYLIST, "r", encoding="utf-8") as f:
        text = f.read()

    lines = text.splitlines()
    new_lines = []
    fixed_epg = 0
    renamed = 0
    skipped_url = 0
    skipped_force = 0
    not_found = 0

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTM3U"):
            new_lines.append("#EXTM3U " + EPG_PLAYLIST_URL)
            i += 1
            continue
        if line.startswith("#EXTINF"):
            # Найти URL следующей строки
            url = ""
            if i + 1 < len(lines):
                url = lines[i + 1].strip()

            original_line = line
            name = get_name(line)
            key = base_name(line)

            # Пропускаем по URL
            if is_skip_url(url):
                skipped_url += 1
                new_lines.append(line)
                i += 1
                continue

            # Пропускаем по имени
            if is_force_skip(name):
                skipped_force += 1
                new_lines.append(line)
                i += 1
                continue

            epg_entry = epg_db.get(normalize(key))

            if not epg_entry:
                # Попробуем поиск по точному нормализованному имени
                epg_entry = epg_db.get(normalize(name))

            if epg_entry:
                tvg_id, epg_name = epg_entry

                # Ставим tvg-id если пустой
                m = re.search(r'tvg-id="([^"]*)"', line)
                if not m or not m.group(1).strip():
                    line = set_tvg_id_in_line(line, tvg_id)
                    fixed_epg += 1

                # Переименовываем если имя отличается (и в EPG не пусто)
                if epg_name and get_name(line) != epg_name:
                    line = set_name_in_line(line, epg_name)
                    renamed += 1
            else:
                not_found += 1

            new_lines.append(line)
            i += 1
            continue

        new_lines.append(line)
        i += 1

    with open(PLAYLIST, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines))

    print("")
    print("=== ИТОГО ===")
    print("Fixed tvg-id: " + str(fixed_epg))
    print("Renamed: " + str(renamed))
    print("Skipped by URL: " + str(skipped_url))
    print("Skipped by name: " + str(skipped_force))
    print("Not found in EPG: " + str(not_found))
    print("Saved " + PLAYLIST)


main()
