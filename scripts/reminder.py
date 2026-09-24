import os
import requests
from datetime import datetime, timezone, timedelta

MSK = timezone(timedelta(hours=3))

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
REPO = os.environ.get("GITHUB_REPOSITORY", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

WORKFLOWS = [
    ("check.yml", "Daily Check (Kinowalk)"),
    ("romaxa55.yml", "Romaxa55 Russia"),
    ("iptvorg.yml", "IPTV-org RUS"),
    ("ufotv.yml", "UFOTV"),
    ("fix_epg.yml", "Fix EPG IDs"),
    ("combine.yml", "Combine Playlists"),
]


def send_telegram(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram secrets not set")
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
            print("Telegram sent")
            return True
        print("Telegram failed: " + str(r.status_code))
        return False
    except Exception as e:
        print("Telegram error: " + str(e))
        return False


def get_last_run(workflow_file):
    url = ("https://api.github.com/repos/" + REPO +
           "/actions/workflows/" + workflow_file + "/runs?per_page=1")
    headers = {
        "Authorization": "Bearer " + GITHUB_TOKEN,
        "Accept": "application/vnd.github+json",
    }
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code != 200:
            print("GitHub API failed for " + workflow_file + ": " + str(r.status_code))
            return None
        data = r.json()
        runs = data.get("workflow_runs", [])
        if not runs:
            return None
        run = runs[0]
        return {
            "status": run.get("status"),
            "conclusion": run.get("conclusion"),
            "started_at": run.get("run_started_at"),
        }
    except Exception as e:
        print("GitHub API error for " + workflow_file + ": " + str(e))
        return None


def format_age(iso_time):
    if not iso_time:
        return "?"
    try:
        dt = datetime.fromisoformat(iso_time.replace("Z", "+00:00"))
        age_sec = (datetime.now(timezone.utc) - dt).total_seconds()
        if age_sec < 3600:
            return str(int(age_sec / 60)) + " мин назад"
        if age_sec < 86400:
            return str(round(age_sec / 3600, 1)) + " ч назад"
        return str(round(age_sec / 86400, 1)) + " дн назад"
    except Exception:
        return "?"


def icon_for(conclusion):
    if conclusion == "success":
        return "✅"
    if conclusion == "failure":
        return "❌"
    if conclusion == "cancelled":
        return "⚪"
    if conclusion == "skipped":
        return "⚪"
    if conclusion is None:
        return "🟡"
    return "❓"


def main():
    now_msk = datetime.now(MSK).strftime("%d.%m.%Y %H:%M") + " МСК"
    print("Reminder at " + now_msk)

    results = []
    any_failed = False

    for wf_file, wf_name in WORKFLOWS:
        run = get_last_run(wf_file)
        results.append((wf_name, run))
        if run is not None and run.get("conclusion") == "failure":
            any_failed = True

    msg = []
    msg.append("🔔 <b>Напоминание: проверка IPTV-системы</b>")
    msg.append("")
    msg.append("🕐 " + now_msk)
    msg.append("")

    if any_failed:
        msg.append("⚠️ <b>Есть проблемы!</b>")
    else:
        msg.append("✅ <b>Всё в порядке</b>")
    msg.append("")

    msg.append("📊 <b>Последние запуски:</b>")
    for wf_name, run in results:
        if run is None:
            msg.append("❓ " + wf_name + " — нет данных")
            continue
        icon = icon_for(run.get("conclusion"))
        age = format_age(run.get("started_at"))
        conclusion = run.get("conclusion") or "in progress"
        msg.append(icon + " " + wf_name + " — " + conclusion + ", " + age)

    msg.append("")
    msg.append("🔗 <a href=\"https://github.com/" + REPO + "/actions\">Открыть Actions</a>")

    if any_failed:
        msg.append("")
        msg.append("📖 <b>Что делать если красный:</b>")
        msg.append("")
        msg.append("1️⃣ Открой Actions, кликни на красный workflow")
        msg.append("2️⃣ Посмотри в логе, на каком шаге упал")
        msg.append("")
        msg.append("<b>Частые ошибки:</b>")
        msg.append("• <code>rejected / fetch first</code> → git-конфликт, напиши в чат")
        msg.append("• <code>404</code> на источник → URL умер, искать новый")
        msg.append("• <code>timeout / ConnectionError</code> → временный сбой, ждать завтра")
        msg.append("• <code>Telegram failed</code> → проверить токен бота в Secrets")
        msg.append("• <code>ModuleNotFoundError</code> → проверить requirements.txt")
        msg.append("")
        msg.append("3️⃣ Если ошибка непонятная — копируй лог и пиши мне в чат")
    else:
        msg.append("")
        msg.append("<i>Раз в месяц: скачай свежий ZIP-бэкап репо на ПК.</i>")

    send_telegram("\n".join(msg))


main()
