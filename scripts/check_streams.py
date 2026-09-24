import os
import concurrent.futures
from datetime import datetime, timezone, timedelta
import requests

MSK = timezone(timedelta(hours=3))

MASTER_FILE = "Keuqxg2a9Dd.m3u"
OUTPUT_FILE = "playlist.m3u"
TIMEOUT = 15
MAX_WORKERS = 15
CHUNK_SIZE = 20000

WHITELIST = [
    "kinowalk",
    "movietoper",
    "timetomovie",
    "timetohorror",
    "blockbusters time",
    "kinolampa",
    "videoarsenal",
    "kinomix юрич",
    "cinema time",
    "scripachtv",
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
    name = get_name(extinf).lower().strip()
    return name


def is_whitelisted(extinf):
    name = base_name(extinf)
    for w in WHITELIST:
        if w in name:
            return True
    return False


def is_live_stream(chunk):
    if not chunk or len(chunk) < 100:
        return False, "too_short_response"

    head = chunk[:1000]

    if b"#EXTM3U" in head or b"#EXT-X-" in head:
        return True, "hls_playlist"

    if b"ftyp" in head[:200] or b"moof" in head or b"moov" in head:
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

    return False, "unknown_format"


def check_url(url):
    if not url:
        return False, "empty"

    try:
        r = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT,
            allow_redirects=True,
            stream=True,
        )
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


def main():
    if not os.path.exists(MASTER_FILE):
        print("Master file not found: " + MASTER_FILE)
        send_telegram("❌ <b>Kinowalk</b>\nМастер-файл не найден: " + MASTER_FILE)
        return

    with open(MASTER_FILE, "r", encoding="utf-8") as f:
        channels = parse_m3u(f.read())

    print("Total channels: " + str(len(channels)))

    whitelist_channels = []
    check_channels = []

    for ch in channels:
        if is_whitelisted(ch["extinf"]):
            whitelist_channels.append(ch)
        else:
            check_channels.append(ch)

    print("Whitelist (skip check): " + str(len(whitelist_channels)))
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
    dead = [ch for ch in check_channels if not results.get(ch["url"])]

    alive = alive_checked + whitelist_channels

    print("Alive: " + str(len(alive)) + " / " + str(len(channels)))
    print("Dead: " + str(len(dead)))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    now_msk = datetime.now(MSK).strftime("%d.%m.%Y %H:%M") + " МСК"

    lines = []
    lines.append("#EXTM3U")
    lines.append("# Updated: " + now + " | Alive: " + str(len(alive)) + "/" + str(len(channels)))
    lines.append("")
    for ch in alive:
        lines.append(ch["extinf"])
        lines.append(ch["url"])
        lines.append("")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    report = []
    report.append("# Report")
    report.append("")
    report.append("Date: " + now)
    report.append("Alive: " + str(len(alive)))
    report.append("Dead: " + str(len(dead)))
    report.append("Whitelist: " + str(len(whitelist_channels)))
    report.append("")
    if dead:
        report.append("## Dead channels")
        report.append("")
        for ch in dead:
            name = get_name(ch["extinf"])
            report.append("- " + name + " | " + reasons.get(ch["url"], "unknown"))
        report.append("")

    with open("report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(report))

    print("Saved " + OUTPUT_FILE)
    print("Saved report.txt")

    total = len(channels)
    alive_count = len(alive)
    dead_count = len(dead)
    pct = round(alive_count * 100 / total, 1) if total > 0 else 0

    msg_lines = []
    msg_lines.append("📊 <b>Kinowalk — ежедневный отчёт</b>")
    msg_lines.append("")
    msg_lines.append("🕐 " + now_msk)
    msg_lines.append("")
    msg_lines.append("✅ Живых: <b>" + str(alive_count) + "</b> / " + str(total) + " (" + str(pct) + "%)")
    msg_lines.append("⭐ Whitelist: " + str(len(whitelist_channels)))
    msg_lines.append("❌ Мёртвых: <b>" + str(dead_count) + "</b>")

    if 0 < dead_count <= 15:
        msg_lines.append("")
        msg_lines.append("🚫 <b>Упали:</b>")
        for ch in dead[:15]:
            name = get_name(ch["extinf"])
            reason = reasons.get(ch["url"], "unknown")
            msg_lines.append("• " + name + " — <i>" + reason + "</i>")

    if dead_count > 15:
        msg_lines.append("")
        msg_lines.append("🚫 <b>Упало больше 15 каналов</b>")
        msg_lines.append("Полный список — в report.txt")

    if dead_count == 0:
        msg_lines.append("")
        msg_lines.append("🎉 Все каналы работают!")

    send_telegram("\n".join(msg_lines))


main()
