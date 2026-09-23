import os
import concurrent.futures
from datetime import datetime, timezone
import requests

MASTER_FILE = "Keuqxg2a9Dd.m3u"
OUTPUT_FILE = "playlist.m3u"
TIMEOUT = 15
MAX_WORKERS = 15
CHUNK_SIZE = 20000

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


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
        return

    with open(MASTER_FILE, "r", encoding="utf-8") as f:
        channels = parse_m3u(f.read())

    print("Total channels: " + str(len(channels)))

    results = {}
    reasons = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        future_map = {pool.submit(check_url, ch["url"]): ch["url"] for ch in channels}
        for fut in concurrent.futures.as_completed(future_map):
            url = future_map[fut]
            ok, reason = fut.result()
            results[url] = ok
            reasons[url] = reason

    alive = [ch for ch in channels if results.get(ch["url"])]
    dead = [ch for ch in channels if not results.get(ch["url"])]

    print("Alive: " + str(len(alive)) + " / " + str(len(channels)))
    print("Dead: " + str(len(dead)))

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

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
    report.append("")
    if dead:
        report.append("## Dead channels")
        report.append("")
        for ch in dead:
            name = ch["extinf"].rsplit(",", 1)[-1].strip() if "," in ch["extinf"] else ch["extinf"]
            report.append("- " + name + " | " + reasons.get(ch["url"], "unknown"))
        report.append("")

    with open("report.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(report))

    print("Saved " + OUTPUT_FILE)
    print("Saved report.txt")


main()
