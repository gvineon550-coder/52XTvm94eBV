import os
import re
import json
import time
import subprocess
import requests
import csv
from datetime import datetime, timezone, timedelta

MSK = timezone(timedelta(hours=3))

PLAYLIST_FILE = "all_channels.m3u"
FILTERED_FILE = "quality_check_input.m3u"
REPORT_FILE = "quality_report.txt"
CSV_FILE = "quality_results.csv"

CHECK_TIMEOUT = 15
MAX_WORKERS = 3
BATCH_SIZE = 50
BATCH_SLEEP = 30

MIN_UPTIME = 0.9
MIN_CHECKS = 5

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
        return
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    try:
        requests.post(url, json={
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }, timeout=15)
        print("Telegram sent")
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


def write_batch_file(channels, path):
    lines = ["#EXTM3U", ""]
    for ch in channels:
        lines.append(ch["extinf"])
        lines.append(ch["url"])
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def ensure_iptvchecker():
    if not os.path.exists("IPTVChecker"):
        print("Клонируем IPTVChecker...")
        subprocess.run(
            ["git", "clone", "https://github.com/kristofferR/IPTVChecker-Python.git", "IPTVChecker"],
            check=True
        )
        subprocess.run(
            ["pip", "install", "-r", "IPTVChecker/requirements.txt"],
            check=True
        )


def run_checker_on_file(input_file, output_csv):
    cmd = [
        "python", "IPTVChecker/IPTV_checker.py",
        input_file,
        "-split",
        "-rename",
        "-o", output_csv,
        "-t", str(CHECK_TIMEOUT),
        "-w", str(MAX_WORKERS),
    ]
    print("Команда: " + " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    print("STDOUT:")
    print(result.stdout[-2000:])
    if result.stderr:
        print("STDERR:")
        print(result.stderr[-500:])
    return result.returncode == 0


def run_iptv_checker_in_batches(channels):
    ensure_iptvchecker()

    batches = []
    for i in range(0, len(channels), BATCH_SIZE):
        batches.append(channels[i:i + BATCH_SIZE])

    print("Батчей: " + str(len(batches)) + " по " + str(BATCH_SIZE) + " каналов")

    all_rows = []
    header = None

    for idx, batch in enumerate(batches):
        print("")
        print("=== Батч " + str(idx + 1) + "/" + str(len(batches)) + " (" + str(len(batch)) + " каналов) ===")

        write_batch_file(batch, FILTERED_FILE)
        batch_csv = "batch_" + str(idx + 1) + ".csv"

        ok = run_checker_on_file(FILTERED_FILE, batch_csv)

        if ok and os.path.exists(batch_csv):
            with open(batch_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                if header is None:
                    header = reader.fieldnames
                for row in reader:
                    all_rows.append(row)
            os.remove(batch_csv)
        else:
            print("Батч упал или CSV не создан")

        if idx < len(batches) - 1:
            print("Пауза " + str(BATCH_SLEEP) + " сек...")
            time.sleep(BATCH_SLEEP)

    if header and all_rows:
        with open(CSV_FILE, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            writer.writeheader()
            for row in all_rows:
                writer.writerow(row)
        print("")
        print("Общий CSV: " + str(len(all_rows)) + " строк")
        return True

    return False


def analyze_results():
    if not os.path.exists(CSV_FILE):
        return {"error": "CSV-файл не создан"}

    total = 0
    alive = 0
    dead = 0
    mislabeled = 0
    low_fps = 0

    mislabeled_list = []
    low_fps_list = []
    dead_list = []

    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            status = (row.get("Status", "") or "").lower()
            name = row.get("Channel", "?") or row.get("Name", "?")

            if "alive" in status or "ok" in status:
                alive += 1

                issues = ((row.get("Issues", "") or "") + (row.get("Notes", "") or "")).lower()
                if "mislabeled" in issues or "mismatch" in issues:
                    mislabeled += 1
                    if len(mislabeled_list) < 10:
                        mislabeled_list.append(name)

                fps_str = row.get("Framerate", "") or row.get("FPS", "")
                try:
                    fps = float(re.sub(r'[^\d.]', '', fps_str))
                    if fps < 29:
                        low_fps += 1
                        if len(low_fps_list) < 10:
                            low_fps_list.append(name + " (" + str(int(fps)) + "fps)")
                except Exception:
                    pass
            else:
                dead += 1
                if len(dead_list) < 10:
                    dead_list.append(name)

    return {
        "total": total,
        "alive": alive,
        "dead": dead,
        "mislabeled": mislabeled,
        "low_fps": low_fps,
        "mislabeled_list": mislabeled_list,
        "low_fps_list": low_fps_list,
        "dead_list": dead_list,
    }


def main():
    now_msk = datetime.now(MSK).strftime("%d.%m.%Y %H:%M") + " МСК"
    print("Quality check at " + now_msk)

    selected, filter_stats = filter_channels()

    if "error" in filter_stats:
        send_telegram("❌ <b>Quality Check</b>\n" + filter_stats["error"])
        return

    if len(selected) == 0:
        send_telegram("⚠️ <b>Quality Check</b>\nНет каналов для проверки")
        return

    print("Проверяем " + str(len(selected)) + " каналов")

    success = run_iptv_checker_in_batches(selected)

    if not success:
        send_telegram("❌ <b>Quality Check</b>\nОшибка при запуске IPTVChecker")
        return

    stats = analyze_results()

    if "error" in stats:
        send_telegram("❌ <b>Quality Check</b>\n" + stats["error"])
        return

    msg = []
    msg.append("🔬 <b>Quality Check — еженедельный отчёт</b>")
    msg.append("")
    msg.append("🕐 " + now_msk)
    msg.append("")
    msg.append("📊 <b>Отобрано для проверки:</b>")
    msg.append("• Всего в all_channels: " + str(filter_stats["total_in_playlist"]))
    msg.append("• Whitelist: " + str(filter_stats["whitelist_count"]))
    msg.append("• Стабильные (uptime ≥" + str(int(MIN_UPTIME * 100)) + "%): " + str(filter_stats["stable_count"]))
    msg.append("• <b>Проверено: " + str(filter_stats["selected"]) + "</b>")
    msg.append("")
    msg.append("🔬 <b>Результат проверки:</b>")
    msg.append("✅ Живых: " + str(stats["alive"]))
    msg.append("❌ Мёртвых: <b>" + str(stats["dead"]) + "</b>")
    msg.append("⚠️ Несоответствие метки: " + str(stats["mislabeled"]))
    msg.append("🐢 Низкий FPS (<29): " + str(stats["low_fps"]))

    if stats["dead_list"]:
        msg.append("")
        msg.append("💀 <b>Упали:</b>")
        for ch in stats["dead_list"][:5]:
            msg.append("• " + ch)

    if stats["mislabeled_list"]:
        msg.append("")
        msg.append("🔍 <b>Несоответствия:</b>")
        for ch in stats["mislabeled_list"][:5]:
            msg.append("• " + ch)

    if stats["low_fps_list"]:
        msg.append("")
        msg.append("🐢 <b>Низкий FPS:</b>")
        for ch in stats["low_fps_list"][:5]:
            msg.append("• " + ch)

    send_telegram("\n".join(msg))

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(msg))


main()
