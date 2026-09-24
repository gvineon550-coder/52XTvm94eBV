import os
import re
import subprocess
import requests
import csv
from datetime import datetime, timezone, timedelta

MSK = timezone(timedelta(hours=3))

PLAYLIST_FILE = "all_channels.m3u"
REPORT_FILE = "quality_report.txt"
CSV_FILE = "quality_results.csv"

CHECK_TIMEOUT = 20
MAX_WORKERS = 5

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


def run_iptv_checker():
    print("=== Запуск IPTVChecker-Python ===")

    if not os.path.exists("IPTVChecker"):
        subprocess.run(
            ["git", "clone", "https://github.com/kristofferR/IPTVChecker-Python.git", "IPTVChecker"],
            check=True
        )
        subprocess.run(
            ["pip", "install", "-r", "IPTVChecker/requirements.txt"],
            check=True
        )

    cmd = [
        "python", "IPTVChecker/IPTV_checker.py",
        PLAYLIST_FILE,
        "-split",
        "-rename",
        "-o", CSV_FILE,
        "-t", str(CHECK_TIMEOUT),
        "-w", str(MAX_WORKERS),
    ]

    print("Команда: " + " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)

    print("STDOUT:")
    print(result.stdout[-3000:])
    if result.stderr:
        print("STDERR:")
        print(result.stderr[-1000:])

    return result.returncode == 0


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

    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            status = (row.get("Status", "") or "").lower()
            if "alive" in status or "ok" in status:
                alive += 1

                issues = ((row.get("Issues", "") or "") + (row.get("Notes", "") or "")).lower()
                if "mislabeled" in issues or "mismatch" in issues:
                    mislabeled += 1
                    if len(mislabeled_list) < 10:
                        mislabeled_list.append(row.get("Channel", "?"))

                fps_str = row.get("Framerate", "") or row.get("FPS", "")
                try:
                    fps = float(re.sub(r'[^\d.]', '', fps_str))
                    if fps < 29:
                        low_fps += 1
                        if len(low_fps_list) < 10:
                            low_fps_list.append(row.get("Channel", "?") + " (" + str(int(fps)) + "fps)")
                except Exception:
                    pass
            else:
                dead += 1

    return {
        "total": total,
        "alive": alive,
        "dead": dead,
        "mislabeled": mislabeled,
        "low_fps": low_fps,
        "mislabeled_list": mislabeled_list,
        "low_fps_list": low_fps_list,
    }


def main():
    now_msk = datetime.now(MSK).strftime("%d.%m.%Y %H:%M") + " МСК"
    print("Quality check at " + now_msk)

    success = run_iptv_checker()

    if not success:
        send_telegram("❌ <b>Quality Check</b>\nОшибка при запуске IPTVChecker")
        return

    stats = analyze_results()

    if "error" in stats:
        send_telegram("❌ <b>Quality Check</b>\n" + stats["error"])
        return

    msg = []
    msg.append("🔬 <b>Quality Check — отчёт по качеству</b>")
    msg.append("")
    msg.append("🕐 " + now_msk)
    msg.append("")
    msg.append("📊 Проверено каналов: <b>" + str(stats['total']) + "</b>")
    msg.append("✅ Живых: " + str(stats['alive']))
    msg.append("❌ Мёртвых: " + str(stats['dead']))
    msg.append("⚠️ Несоответствие метки: " + str(stats['mislabeled']))
    msg.append("🐢 Низкий FPS (<29): " + str(stats['low_fps']))

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


main()
