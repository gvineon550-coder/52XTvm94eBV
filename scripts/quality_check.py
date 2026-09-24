import os
import re
import json
import time
import subprocess
import requests
import csv
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

MSK = timezone(timedelta(hours=3))

PLAYLIST_FILE = "all_channels.m3u"
REPORT_FILE = "quality_report.txt"
CSV_FILE = "quality_results.csv"
QUALITY_FILE = "quality_data.json"

FFPROBE_TIMEOUT = 15
MAX_WORKERS = 5
BATCH_SIZE = 50
BATCH_SLEEP = 20

MIN_UPTIME = 0.9
MIN_CHECKS = 5
MIN_BITRATE_MBPS = 0.3

STATS_FILES = [
    "romaxa55_stats.json",
    "iptvorg_stats.json",
    "ufotv_stats.json",
]

WHITELIST = [
    "channel one", "первый канал", "1tv", "ort",
    "ren tv", "ren-tv", "рен тв", "рен-тв", "rentv",
    "russia-1", "russia 1", "russia1",
    "россия-1", "россия 1", "россия1",
    "rossiya-1", "rossiya 1", "rossiya1",
    "russia-24", "russia 24", "russia24",
    "россия-24", "россия 24", "россия24",
    "rossiya-24", "rossiya 24", "rossiya24",
    "russia-k", "russia k", "россия-к", "россия к",
    "rossiya-k", "rossiya k", "kultura", "культура",
    "russia hd", "россия hd", "rossiya hd",
    "start air", "start-air", "startair",
    "start world", "start-world", "startworld",
    "ntv", "нтв",
]

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")


def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram secrets not set, skipping")
        return False
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=15)
        if r.status_code == 200:
            print("Telegram sent (200)")
            return True
        print("Telegram HTML failed: " + str(r.status_code) + " - " + r.text[:300])

        r2 = requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "disable_web_page_preview": True,
        }, timeout=15)
        if r2.status_code == 200:
            print("Telegram sent (plain text fallback)")
            return True
        print("Telegram fallback failed: " + str(r2.status_code) + " - " + r2.text[:300])
        return False
    except Exception as e:
        print("Telegram error: " + str(e))
        return False


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


def is_whitelisted(extinf):
    name = base_name(extinf)
    for w in WHITELIST:
        pattern = r'(?<![a-zа-яё0-9])' + re.escape(w) + r'(?![a-zа-яё0-9])'
        if re.search(pattern, name):
            return True
    return False


def load_all_stats():
    merged = {}
    for path in STATS_FILES:
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
                for name, s in data.items():
                    merged[name] = s
        except Exception as e:
            print("Stats load error " + path + ": " + str(e))
    return merged


def is_stable_by_stats(extinf, stats):
    name = base_name(extinf)
    s = stats.get(name)
    if not s:
        return False
    checks = s.get("checks", 0)
    success = s.get("success", 0)
    if checks < MIN_CHECKS:
        return False
    uptime = success / checks
    return uptime >= MIN_UPTIME


def filter_channels():
    if not os.path.exists(PLAYLIST_FILE):
        return [], {"error": "all_channels.m3u не найден"}

    with open(PLAYLIST_FILE, "r", encoding="utf-8") as f:
        channels = parse_m3u(f.read())

    stats = load_all_stats()
    print("Stats loaded: " + str(len(stats)) + " entries")

    selected = []
    whitelist_count = 0
    stable_count = 0

    for ch in channels:
        if is_whitelisted(ch["extinf"]):
            selected.append(ch)
            whitelist_count += 1
        elif is_stable_by_stats(ch["extinf"], stats):
            selected.append(ch)
            stable_count += 1

    print("Selected: " + str(len(selected)) + " (whitelist: " + str(whitelist_count) + ", stable: " + str(stable_count) + ")")

    return selected, {
        "total_in_playlist": len(channels),
        "selected": len(selected),
        "whitelist_count": whitelist_count,
        "stable_count": stable_count,
    }


def check_url_with_ffprobe(url):
    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        "-analyzeduration", "5000000",
        "-probesize", "5000000",
        "-rw_timeout", "10000000",
        url,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=FFPROBE_TIMEOUT,
        )
        if result.returncode != 0:
            return {"status": "dead", "error": "ffprobe_rc_" + str(result.returncode)}

        if not result.stdout.strip():
            return {"status": "dead", "error": "empty_output"}

        data = json.loads(result.stdout)

        video = None
        for s in data.get("streams", []):
            if s.get("codec_type") == "video":
                video = s
                break

        if not video:
            return {"status": "dead", "error": "no_video_stream"}

        width = video.get("width", 0) or 0
        height = video.get("height", 0) or 0
        codec = video.get("codec_name", "?")

        fps = 0.0
        avg = video.get("avg_frame_rate", "0/0")
        if "/" in avg:
            num, den = avg.split("/")
            try:
                num_f = float(num)
                den_f = float(den)
                if den_f > 0:
                    fps = num_f / den_f
            except Exception:
                pass

        bitrate = 0.0
        br = video.get("bit_rate")
        if not br:
            br = data.get("format", {}).get("bit_rate")
        if br:
            try:
                bitrate = float(br) / 1000000.0
            except Exception:
                pass

        if height >= 2000:
            res = "4K"
        elif height >= 1000:
            res = "1080p"
        elif height >= 700:
            res = "720p"
        elif height >= 500:
            res = "576p"
        elif height >= 400:
            res = "480p"
        elif height > 0:
            res = str(height) + "p"
        else:
            res = "?"

        return {
            "status": "alive",
            "width": width,
            "height": height,
            "resolution": res,
            "codec": codec,
            "fps": round(fps, 1),
            "bitrate_mbps": round(bitrate, 2),
        }

    except subprocess.TimeoutExpired:
        return {"status": "dead", "error": "timeout"}
    except json.JSONDecodeError:
        return {"status": "dead", "error": "json_error"}
    except Exception as e:
        return {"status": "dead", "error": type(e).__name__}


def run_checks_in_batches(channels):
    batches = []
    for i in range(0, len(channels), BATCH_SIZE):
        batches.append(channels[i:i + BATCH_SIZE])

    print("Батчей: " + str(len(batches)) + " по " + str(BATCH_SIZE) + " каналов")

    all_results = []

    for idx, batch in enumerate(batches):
        print("")
        print("=== Батч " + str(idx + 1) + "/" + str(len(batches)) + " (" + str(len(batch)) + " каналов) ===")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            future_map = {pool.submit(check_url_with_ffprobe, ch["url"]): ch for ch in batch}
            for fut in as_completed(future_map):
                ch = future_map[fut]
                try:
                    result = fut.result()
                except Exception as e:
                    result = {"status": "dead", "error": type(e).__name__}
                result["name"] = get_name(ch["extinf"])
                result["url"] = ch["url"]
                all_results.append(result)

        ok_count = sum(1 for r in all_results if r["status"] == "alive")
        print("Прогресс: " + str(len(all_results)) + "/" + str(len(channels)) + " проверено, живых: " + str(ok_count))

        if idx < len(batches) - 1:
            print("Пауза " + str(BATCH_SLEEP) + " сек...")
            time.sleep(BATCH_SLEEP)

    return all_results


def write_csv(results):
    fields = ["name", "status", "resolution", "width", "height", "codec", "fps", "bitrate_mbps", "error", "url"]
    with open(CSV_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for r in results:
            writer.writerow(r)


def write_quality_data(results):
    """Сохраняет мёртвые каналы в JSON. Объединяет со старыми (макс 30 дней)."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    now_dt = datetime.now(timezone.utc)

    existing = {}
    if os.path.exists(QUALITY_FILE):
        try:
            with open(QUALITY_FILE, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception as e:
            print("Quality file load error: " + str(e))

    checked_keys = set()
    data = {}

    for r in results:
        raw = r["name"].lower().strip()
        key = re.sub(r'\(?\s*(FHD|UHD|HD|SD|4K)\s*\)?', '', raw, flags=re.IGNORECASE)
        key = re.sub(r'\(?\s*\d{3,4}p\s*\)?', '', key, flags=re.IGNORECASE)
        key = re.sub(r'\[[^\]]*\]', '', key)
        key = re.sub(r'\s+', ' ', key).strip()
        checked_keys.add(key)

        if r["status"] == "dead":
            entry = {
                "status": "dead",
                "last_check": now_iso,
                "reason": r.get("error", "unknown"),
                "action": "remove",
            }
            data[key] = entry

    kept_old = 0
    for key, entry in existing.items():
        if key in checked_keys:
            continue
        last_check_str = entry.get("last_check", "")
        try:
            last_check_dt = datetime.strptime(last_check_str, "%Y-%m-%d %H:%M UTC").replace(tzinfo=timezone.utc)
            age_days = (now_dt - last_check_dt).days
            if age_days <= 30:
                data[key] = entry
                kept_old += 1
        except Exception:
            pass

    with open(QUALITY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("Quality data saved: " + str(len(data)) + " entries (kept old: " + str(kept_old) + ")")
    return data


def analyze(results):
    total = len(results)
    alive = [r for r in results if r["status"] == "alive"]
    dead = [r for r in results if r["status"] != "alive"]

    low_fps = [r for r in alive if r.get("fps", 0) > 0 and r.get("fps", 0) < 29]
    low_bitrate = [r for r in alive if 0 < r.get("bitrate_mbps", 0) < 1.0]
    low_res = [r for r in alive if r.get("resolution") in ("480p", "576p", "?")]

    return {
        "total": total,
        "alive": len(alive),
        "dead": len(dead),
        "dead_list": dead[:10],
        "low_fps": len(low_fps),
        "low_fps_list": low_fps[:10],
        "low_bitrate": len(low_bitrate),
        "low_bitrate_list": low_bitrate[:10],
        "low_res": len(low_res),
        "low_res_list": low_res[:10],
    }


def main():
    now_msk = datetime.now(MSK).strftime("%d.%m.%Y %H:%M") + " МСК"
    print("Quality check at " + now_msk)

    selected, filter_stats = filter_channels()

    if "error" in filter_stats:
        send_telegram("❌ Quality Check\n" + filter_stats["error"])
        return

    if len(selected) == 0:
        send_telegram("⚠️ Quality Check\nНет каналов для проверки")
        return

    print("Проверяем " + str(len(selected)) + " каналов через ffprobe")

    start_time = time.time()
    results = run_checks_in_batches(selected)
    elapsed = round((time.time() - start_time) / 60, 1)

    write_csv(results)
    print("CSV записан: " + CSV_FILE)

    quality_data = write_quality_data(results)

    stats = analyze(results)

    msg = []
    msg.append("🔬 Quality Check — еженедельный отчёт")
    msg.append("")
    msg.append("🕐 " + now_msk + " (за " + str(elapsed) + " мин)")
    msg.append("")
    msg.append("📊 Проверено: " + str(filter_stats["selected"]) + " каналов")
    msg.append("• Whitelist: " + str(filter_stats["whitelist_count"]))
    msg.append("• Стабильные: " + str(filter_stats["stable_count"]))
    msg.append("")
    msg.append("🔬 Результат:")
    msg.append("✅ Живых: " + str(stats["alive"]))
    msg.append("❌ Мёртвых: " + str(stats["dead"]))
    msg.append("⚠️ Низкий битрейт (<1 Мбит/с): " + str(stats["low_bitrate"]))
    msg.append("🐢 Низкий FPS (<29): " + str(stats["low_fps"]))
    msg.append("📺 SD-разрешение: " + str(stats["low_res"]))
    msg.append("")
    msg.append("🗑 К удалению из all_channels: " + str(len(quality_data)))

    if stats["dead_list"]:
        msg.append("")
        msg.append("💀 Топ-5 мёртвых:")
        for r in stats["dead_list"][:5]:
            msg.append("• " + r["name"] + " — " + r.get("error", "?"))

    send_telegram("\n".join(msg))

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(msg))


main()
