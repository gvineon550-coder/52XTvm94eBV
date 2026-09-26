import os
import requests

REPO = os.environ.get("GITHUB_REPOSITORY")
TOKEN = os.environ.get("GITHUB_TOKEN")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TG_CHAT = os.environ.get("TELEGRAM_CHAT_ID")

WARN_MB = 700
ALERT_MB = 1000


def get_repo_size_kb():
    url = "https://api.github.com/repos/" + REPO
    headers = {
        "Authorization": "Bearer " + TOKEN,
        "Accept": "application/vnd.github+json",
    }
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    return r.json().get("size", 0)


def send_telegram(message):
    if not TG_TOKEN or not TG_CHAT:
        print("Telegram secrets not set, skipping")
        return
    url = "https://api.telegram.org/bot" + TG_TOKEN + "/sendMessage"
    r = requests.post(url, json={
        "chat_id": TG_CHAT,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }, timeout=10)
    print("Telegram: " + str(r.status_code))


def main():
    size_kb = get_repo_size_kb()
    size_mb = size_kb / 1024
    size_gb = size_mb / 1024

    if size_gb >= 1:
        size_str = "{:.2f} ГБ".format(size_gb)
    else:
        size_str = "{:.1f} МБ".format(size_mb)

    print("Repo size: " + size_str)

    if size_mb >= ALERT_MB:
        emoji = "🚨"
        advice = "<b>Пора делать shrink!</b>"
    elif size_mb >= WARN_MB:
        emoji = "⚠️"
        advice = "Приближается к 1 ГБ, планируй shrink"
    else:
        emoji = "✅"
        advice = "Всё ок"

    msg = (
        emoji + " <b>Размер репо</b>\n\n"
        "📦 " + size_str + "\n"
        "ℹ️ " + advice
    )

    send_telegram(msg)


main()
