import os
import re
import json
import concurrent.futures
from datetime import datetime, timezone, timedelta
import requests

MSK = timezone(timedelta(hours=3))

SOURCE_URL = "https://raw.githubusercontent.com/UFOTVM/TV/refs/heads/main/ufo.m3u"
OUTPUT_FILE = "ufotv_playlist.m3u"
UNSTABLE_FILE = "ufotv_unstable.m3u"
REPORT_FILE = "ufotv_report.txt"
STATS_FILE = "ufotv_stats.json"

TIMEOUT = 15
MAX_WORKERS = 15
CHUNK_SIZE = 50000

MIN_CHECKS = 3
MIN_UPTIME = 0.7

BAD_PORTS = {":8080", ":8000", ":9999", ":8888"}
BAD_DOMAINS = (".xyz", ".tk", ".ml", ".cf", ".ga", "cinerama.uz")

WHITELIST = [
    "pervy", "rossia1", "rossia-24", "ntv", "tnt", "sts", "tv3", "piatnica",
    "che", "domashny", "super", "360", "moskva-24", "izvestia", "ren-tv",
    "match", "karusel", "mir", "zvezda", "tvc", "pyatnica"
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


def send_telegram(message):
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print("Telegram secrets not set, skipping")
        return
    try:
        url = "https://api.telegram.org/bot" + token + "/sendMessage"
        r = requests.post(
            url,
            json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
                "disable_web_page_preview": True,
            },
            timeout=10,
        )
        if r.status_code == 200:
            print("Telegram sent")
        else:
            print("Telegram failed: " + str(r.status_code))
    except Exception as e:
        print("Telegram error: " + str(e))


def extract_header(text):
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#EXTM3U"):
            return line
        if line and not line.startswith("#"):
            break
    return "#EXTM3U"


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


def is_whitelisted(extinf):
    name = base_name(extinf)
    for w in WHITELIST:
        if w in name:
            return True
    return False


def is_bad_url(url):
    u = url.lower()
    if re.match(r'^https?://\d+\.\d+\.\d+\.\d+', u):
        return True, "bare_ip"
    for port in BAD_PORTS:
        if port in u:
            return True, "bad_port" + port
    for dom in BAD_DOMAINS:
        if dom + "/" in u or dom + ":" in u or dom + "?" in u:
            return True, "bad_domain" + dom
    return False, ""


def is_geo_blocked(extinf):
    return "[geo" in get_name(extinf).lower()


def mark_geo(extinf):
    return re.sub(
        r'group-title="[^"]*"',
        'group-title="UFOTV [Geo]"',
        extinf,
        count=1,
        flags=re.IGNORECASE
    )


def is_live_stream(chunk):
    if not chunk or len(chunk) < 100:
        return False, "too_short_response"
    head = chunk[:2000]
    if b"#EXTM3U" in head or b"#EXT-X-" in head:
        return True, "hls_playlist"
    if b"ftyp" in head[:500] or b"moof" in head or b"moov" in head:
        return True, "mp4_stream"
    ts_count = chunk.count(b"\x47")
    if ts_count > len(chunk) * 0.05:
        return True, "mpeg_ts"
    lower = head.lower()
    if b"<html" in lower or b"<!doctype" in lower:
        return False, "html_page"
    if chunk[:3] == b"\xff\xd8\xff":
        return False, "jpeg_image"
    if chunk[:8] == b"\x89PNG\r\n\x1a\n":
        return False, "png_image"
    if len(chunk) > 5000:
        return True, "unknown_but_big"
    return False, "unknown_format"


def check_url(url):
    if not url:
        return False, "empty"
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True, stream=True)
        if r.status_code >= 400:
            return False, "http_" + str(r.status_code)
        chunk = b""
        for piece in r.iter_content(chunk_size=4096):
            chunk += piece
            if len(chunk) >= CHUNK_SIZE:
                break
        r.close()
        return is_live_stream(chunk)
    except requests.exceptions.Timeout:
        return False, "timeout"
    except requests.exceptions.ConnectionError:
        return False, "conn_error"
    except Exception as e:
        return False, "err_" + type(e).__name__


def load_stats():
    if os.path.exists(STATS_FILE):
        try:
            with open(STATS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_stats(stats):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)


def main():
    print("Downloading: " + SOURCE_URL)
    try:
        r = requests.get(SOURCE_URL, headers=HEADERS, timeout=60)
        r.raise_for_status()
        text = r.text
    except Exception as e:
        print("Download failed: " + str(e))
        send_telegram("❌ <b>UFOTV</b>\nНе удалось скачать плейлист:\n" + str(e))
        return

    header_line = extract_header(text)
    print("Header: " + header_line)

    all_channels = parse_m3u(text)
    print("Total in source: " + str(len(all_channels)))

    after_clean = []
    dropped_mud = 0
    for ch in all_channels:
        bad, _r = is_bad_url(ch["url"])
        if not bad:
            after_clean.append(ch)
        else:
            dropped_mud += 1
    print("After URL cleanup: " + str(len(after_clean)) + " (dropped " + str(dropped_mud) + ")")

    best_by_name = {}
    for ch in after_clean:
        key = base_name(ch["extinf"])
        q = get_quality(ch["extinf"])
        if key not in best_by_name or q > get_quality(best_by_name[key]["extinf"]):
            best_by_name[key] = ch

    deduped = list(best_by_name.values())
    dropped_dups = len(after_clean) - len(deduped)
    print("After dedup: " + str(len(deduped)) + " (dropped " + str(dropped_dups) + ")")

    whitelist_channels = []
    geo_channels = []
    check_channels = []

    for ch in deduped:
        if is_whitelisted(ch["extinf"]):
            whitelist_channels.append(ch)
        elif is_geo_blocked(ch["extinf"]):
            geo_channels.append(ch)
        else:
            check_channels.append(ch)

    for ch in geo_channels:
        ch["extinf"] = mark_geo(ch["extinf"])

    print("Whitelist (skip check): " + str(len(whitelist_channels)))
    print("Geo-blocked: " + str(len(geo_channels)))
    print("To check: " + str(len(check_channels)))

    results = {}
    reasons = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_map = {pool.submit(check_url, ch["url"]): ch["url"] for ch in check_channels}
        for fut in concurrent.futures.as_completed(future_map):
            url = future_map[fut]
            ok, reason = fut.result()
            results[url] = ok
            reasons[url] = reason

    alive_checked = [ch for ch in check_channels if results.get(ch["url"])]
    dead_today = [ch for ch in check_channels if not results.get(ch["url"])]

    print("Alive checked: " + str(len(alive_checked)) + " / " + str(len(check_channels)))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    now_msk = datetime.now(MSK).strftime("%d.%m.%Y %H:%M") + " МСК"

    stats = load_stats()

    for ch in check_channels:
        name = base_name(ch["extinf"])
        if name not in stats:
            stats[name] = {"checks": 0, "success": 0, "first_seen": now, "last_check": None, "last_ok": None}
        stats[name]["checks"] += 1
        stats[name]["last_check"] = now
        if results.get(ch["url"]):
            stats[name]["success"] += 1
            stats[name]["last_ok"] = now

    save_stats(stats)

    stable = []
    unstable = []
    new_channels = 0

    for ch in alive_checked:
        name = base_name(ch["extinf"])
        s = stats.get(name, {})
        checks = s.get("checks", 0)
        success = s.get("success", 0)

        if checks < MIN_CHECKS:
            stable.append(ch)
            new_channels += 1
            continue

        uptime = success / checks if checks > 0 else 0
        if uptime >= MIN_UPTIME:
            stable.append(ch)
        else:
            unstable.append(ch)

    stable = stable + whitelist_channels + geo_channels

    print("Stable: " + str(len(stable)))
    print("Unstable: " + str(len(unstable)))
    print("Too new: " + str(new_channels))

    lines = []
    lines.append(header_line)
    lines.append("# Updated: " + now + " | Total: " + str(len(stable)))
    lines.append("")
    for ch in stable:
        lines.append(ch["extinf"])
        lines.append(ch["url"])
        lines.append("")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    if unstable:
        ulines = []
        ulines.append(header_line)
        ulines.append("# Unstable channels (uptime below " + str(int(MIN_UPTIME * 100)) + "%)")
        ulines.append("")
        for ch in unstable:
            name = base_name(ch["extinf"])
            s = stats.get(name, {})
            uptime = s.get("success", 0) / s.get("checks", 1)
            ulines.append("# Uptime: " + str(round(uptime * 100, 1)) + "% (" + str(s.get("success")) + "/" + str(s.get("checks")) + ")")
            ulines.append(ch["extinf"])
            ulines.append(ch["url"])
            ulines.append("")
        with open(UNSTABLE_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(ulines))

    report = []
    report.append("# UFOTV Report")
    report.append("")
    report.append("Date: " + now)
    report.append("")
    report.append("## Funnel")
    report.append("- Total in source: " + str(len(all_channels)))
    report.append("- After URL cleanup: " + str(len(after_clean)) + " (dropped " + str(dropped_mud) + ")")
    report.append("- After dedup: " + str(len(deduped)) + " (dropped " + str(dropped_dups) + ")")
    report.append("- Whitelist (skip check): " + str(len(whitelist_channels)))
    report.append("- Geo-blocked (auto-include): " + str(len(geo_channels)))
    report.append("- To check: " + str(len(check_channels)))
    report.append("- Alive checked: " + str(len(alive_checked)))
    report.append("- Stable in playlist: " + str(len(stable)))
    report.append("- Filtered as unstable: " + str(len(unstable)))
    report.append("- Too new (collecting stats): " + str(new_channels))
    report.append("")
    report.append("Thresholds: min checks " + str(MIN_CHECKS) + ", uptime >= " + str(int(MIN_UPTIME * 100)) + "%")
    report.append("")

    if dead_today:
        report.append("## Dead today (" + str(len(dead_today)) + ")")
        report.append("")
        for ch in dead_today:
            name = get_name(ch["extinf"])
            report.append("- " + name + " | " + reasons.get(ch["url"], "unknown"))
        report.append("")

    if unstable:
        report.append("## Filtered as unstable (" + str(len(unstable)) + ")")
        report.append("")
        for ch in unstable:
            name = base_name(ch["extinf"])
            s = stats.get(name, {})
            uptime = s.get("success", 0) / s.get("checks", 1)
            report.append("- " + get_name(ch["extinf"]) + " | uptime " + str(round(uptime * 100, 1)) + "% (" + str(s.get("success")) + "/" + str(s.get("checks")) + ")")
        report.append("")

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(report))

    print("Saved " + OUTPUT_FILE)
    print("Saved " + REPORT_FILE)

    msg_lines = []
    msg_lines.append("📊 <b>UFOTV — ежедневный отчёт</b>")
    msg_lines.append("")
    msg_lines.append("🕐 " + now_msk)
    msg_lines.append("")
    msg_lines.append("✅ В плейлисте: <b>" + str(len(stable)) + "</b>")
    msg_lines.append("🌍 Geo-blocked: " + str(len(geo_channels)))
    msg_lines.append("⭐ Whitelist: " + str(len(whitelist_channels)))
    msg_lines.append("❌ Мёртвых сегодня: <b>" + str(len(dead_today)) + "</b>")
    msg_lines.append("⚠️ Нестабильных (отсеяно): " + str(len(unstable)))
    msg_lines.append("🆕 Новых (собираем статистику): " + str(new_channels))
    msg_lines.append("")
    msg_lines.append("📥 Источник: " + str(len(all_channels)) + " каналов")
    msg_lines.append("🧹 После фильтров: " + str(len(deduped)))
    msg_lines.append("📅 EPG: сохранён из источника")

    if dead_today and len(dead_today) <= 10:
        msg_lines.append("")
        msg_lines.append("🚫 <b>Упали сегодня:</b>")
        for ch in dead_today[:10]:
            name = get_name(ch["extinf"])
            reason = reasons.get(ch["url"], "unknown")
            msg_lines.append("• " + name + " — <i>" + reason + "</i>")

    send_telegram("\n".join(msg_lines))


main()
