import os
import re
from collections import defaultdict

PLAYLIST_FILE = "all_channels.m3u"
REPORT_FILE = "duplicates_report.txt"


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


def extract_tvg_id(extinf):
    m = re.search(r'tvg-id="([^"]*)"', extinf)
    if not m:
        return ""
    tvg_id = m.group(1).strip()
    if "@" in tvg_id:
        tvg_id = tvg_id.split("@")[0]
    return tvg_id


def get_group(extinf):
    m = re.search(r'group-title="([^"]*)"', extinf, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def main():
    if not os.path.exists(PLAYLIST_FILE):
        print("Файл не найден: " + PLAYLIST_FILE)
        return

    with open(PLAYLIST_FILE, "r", encoding="utf-8") as f:
        channels = parse_m3u(f.read())

    print("Всего каналов: " + str(len(channels)))

    by_url = defaultdict(list)
    for ch in channels:
        by_url[ch["url"]].append(ch)
    url_dups = {url: chs for url, chs in by_url.items() if len(chs) > 1}

    by_name = defaultdict(list)
    for ch in channels:
        by_name[base_name(ch["extinf"])].append(ch)
    name_dups = {name: chs for name, chs in by_name.items() if len(chs) > 1}

    by_tvg = defaultdict(list)
    for ch in channels:
        tid = extract_tvg_id(ch["extinf"])
        if tid:
            by_tvg[tid].append(ch)
    tvg_dups = {tid: chs for tid, chs in by_tvg.items() if len(chs) > 1}

    total_url = sum(len(chs) - 1 for chs in url_dups.values())
    total_name = sum(len(chs) - 1 for chs in name_dups.values())
    total_tvg = sum(len(chs) - 1 for chs in tvg_dups.values())

    print("")
    print("=== СВОДКА ===")
    print("Дубли по URL:     " + str(len(url_dups)) + " групп, лишних: " + str(total_url))
    print("Дубли по имени:   " + str(len(name_dups)) + " групп, лишних: " + str(total_name))
    print("Дубли по tvg-id:  " + str(len(tvg_dups)) + " групп, лишних: " + str(total_tvg))
    print("")

    lines = []
    lines.append("# Отчёт по дублям")
    lines.append("")
    lines.append("Всего каналов: " + str(len(channels)))
    lines.append("")
    lines.append("Сводка:")
    lines.append("- URL дубли: " + str(len(url_dups)) + " групп (лишних: " + str(total_url) + ")")
    lines.append("- Имя дубли: " + str(len(name_dups)) + " групп (лишних: " + str(total_name) + ")")
    lines.append("- tvg-id дубли: " + str(len(tvg_dups)) + " групп (лишних: " + str(total_tvg) + ")")
    lines.append("")

    lines.append("## 1. Дубли по URL")
    lines.append("")
    for url, chs in sorted(url_dups.items()):
        lines.append("URL: " + url)
        for ch in chs:
            lines.append("  • " + get_name(ch["extinf"]) + " [" + get_group(ch["extinf"]) + "]")
        lines.append("")

    lines.append("## 2. Дубли по имени (base_name)")
    lines.append("")
    for name, chs in sorted(name_dups.items()):
        lines.append("Имя: " + name)
        for ch in chs:
            lines.append("  • " + get_name(ch["extinf"]) + " [" + get_group(ch["extinf"]) + "]")
        lines.append("")

    lines.append("## 3. Дубли по tvg-id")
    lines.append("")
    for tid, chs in sorted(tvg_dups.items()):
        lines.append("tvg-id: " + tid)
        for ch in chs:
            lines.append("  • " + get_name(ch["extinf"]) + " [" + get_group(ch["extinf"]) + "]")
        lines.append("")

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("Отчёт записан: " + REPORT_FILE)
    print("")
    print("=== ТОП-25 дублей по URL ===")
    for i, (url, chs) in enumerate(list(sorted(url_dups.items()))[:25]):
        names = " | ".join([get_name(ch["extinf"]) for ch in chs])
        print(str(i+1) + ". " + names)


main()
