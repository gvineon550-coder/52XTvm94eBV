import os
import re
import json
import requests
from datetime import datetime, timezone, timedelta

MSK = timezone(timedelta(hours=3))

OUTPUT_FILE = "all_channels.m3u"
EPG_URL = "https://iptvx.one/epg/epg_lite.xml.gz"
QUALITY_FILE = "quality_data.json"
IPTV_ORG_CHANNELS_URL = "https://iptv-org.github.io/api/channels.json"

SOURCES = [
    "playlist.m3u",
    "romaxa55_russia.m3u",
    "iptvorg_rus.m3u",
    "ufotv_playlist.m3u",
]

BAD_PORTS = {":8080", ":8000", ":9999", ":8888"}
BAD_DOMAINS = (
    ".xyz", ".tk", ".ml", ".cf", ".ga",
    "cinerama.uz",
    "tinyurl.com", "bit.ly", "goo.gl", "clck.ru", "is.gd", "t.co", "ow.ly",
)

KIDS_KEYWORDS = [
    "kids", "kid", "junior", "jr", "baby", "cartoon", "toon",
    "nickelodeon", "nick", "nicktoons", "disney", "boomerang",
    "gulli", "tiji", "davinci", "da vinci", "carousel",
    "mult", "multimania", "multilandia",
    "детск", "детcк", "мульт", "малыш", "карусель", "ребенок", "ребёнок",
    "солнце",
]

KIDS_EXCEPTIONS = [
    "start air", "start world",
]

BLOCKED_CHANNELS = [
    "legislative rada",
    "rada tv",
    "рада",
    "rada",
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

# === Маппинг категорий IPTV-org → русские ===
IPTV_CATEGORY_MAP = {
    "general": "📺 Федеральные",
    "news": "📰 Новости",
    "sports": "⚽ Спорт",
    "movies": "🎬 Кино",
    "series": "🎬 Кино",
    "comedy": "🎬 Кино",
    "classic": "🎬 Кино",
    "animation": "🎬 Кино",
    "music": "🎵 Музыка",
    "documentary": "📚 Познавательные",
    "science": "📚 Познавательные",
    "culture": "📚 Познавательные",
    "education": "📚 Познавательные",
    "entertainment": "🎭 Развлечения",
    "lifestyle": "🎭 Развлечения",
    "cooking": "🎭 Развлечения",
    "family": "🎭 Развлечения",
    "travel": "🎭 Развлечения",
    "outdoor": "🎭 Развлечения",
    "auto": "🚗 Авто",
    "business": "💼 Бизнес",
    "shop": "🛒 Магазины",
    "relax": "🌿 Релакс",
    "weather": "🌤 Погода",
    "religious": "⛪ Религия",
    "kids": "📦 Прочее",
    "legislative": "📦 Прочее",
}

# === Маппинг group-title от источников ===
GROUP_TITLE_MAP = {
    "movies": "🎬 Кино", "кино": "🎬 Кино", "cinema": "🎬 Кино", "фильмы": "🎬 Кино",
    "sport": "⚽ Спорт", "спорт": "⚽ Спорт", "sports": "⚽ Спорт",
    "news": "📰 Новости", "новости": "📰 Новости", "новости ": "📰 Новости",
    "music": "🎵 Музыка", "музыка": "🎵 Музыка",
    "kids": "📦 Прочее", "детск": "📦 Прочее", "детские": "📦 Прочее",
    "russia": "📺 Федеральные", "россия": "📺 Федеральные", "российские": "📺 Федеральные",
    "ru": "📺 Федеральные",
    "general": "📺 Федеральные",
    "documentary": "📚 Познавательные", "познавательные": "📚 Познавательные",
    "entertainment": "🎭 Развлечения", "развлечения": "🎭 Развлечения",
    "auto": "🚗 Авто", "авто": "🚗 Авто",
    "shop": "🛒 Магазины", "магазин": "🛒 Магазины",
    "religion": "⛪ Религия", "религия": "⛪ Религия",
}

# === Fallback: ключевые слова в имени ===
CATEGORIES_KEYWORDS = {
    "📺 Федеральные": [
        "channel one", "первый канал", "1tv", "ort",
        "russia-1", "russia 1", "россия-1", "россия 1", "rossiya-1", "rossiya 1",
        "russia-24", "russia 24", "россия-24", "россия 24", "rossiya-24", "rossiya 24",
        "russia-k", "россия-к", "россия к", "kultura", "культура",
        "ntv", "нтв", "ren tv", "ren-tv", "рен тв", "рен-тв", "rentv",
        "tnt", "тнт", "sts", "стс", "tv3", "тв3", "тв-3",
        "tvc", "твц", "tv centr", "тв центр",
        "karusel", "карусель", "che", "че", "пятница", "pyatnica", "friday",
        "domashniy", "домашний", "zvezda", "звезда",
        "mir", "мир", "otr", "отр", "спас", "spas",
    ],
    "⚽ Спорт": [
        "match", "матч", "khl", "кхл", "setanta", "sport", "спорт",
        "eurosport", "football", "футбол", "futbol",
        "mma", "ufc", "boks", "бокс", "extreme sport", "экстрим",
        "okko sport", "okko futbol", "sportivnyy", "sportiv",
        "formula 1", "formula one",
    ],
    "🎬 Кино": [
        "кино", "kino", "cinema", "tv1000", "viju", "amedia", "амедиа",
        "fox", "fox life", "fx", "sony", "sci-fi", "scifi",
        "blockbuster", "блокбастер", "kinopokaz", "kinopremyera",
        "kinohit", "kinomix", "kinokomedija", "kinoseriya", "kinosvidanie",
        "kinouzhas", "киноужас", "kinosemja", "киносемья",
        "nashe novoe kino", "rodnoe kino", "russkiy illusion",
        "mosfilm", "мосфильм", "star cinema", "star family",
        "premialnoe", "dorama", "индийское", "indiyskoye",
        "comedy", "комедия", "start air", "start world", "start triumph",
        "kinowalk", "movietoper", "timetomovie", "timetohorror",
        "blockbusters", "kinolampa", "videoarsenal", "kinomix юрич",
        "cinema time", "scripachtv",
    ],
    "📰 Новости": [
        "24", "news", "новости", "rbc", "рбк", "izvestia", "известия",
        "russia today", "cgtn", "france 24", "euronews",
        "dw", "bbc", "cnn", "vmeste", "вместе",
        "moskva 24", "москва 24",
    ],
    "🎵 Музыка": [
        "муз", "muz", "mtv", "vh1", "europa plus", "европа плюс",
        "ru.tv", "ru tv", "rutv", "music box", "музыка", "muzyka",
        "bridge", "brigde", "1hd", "1 hd music", "mcm",
        "shanson", "шансон", "zhara", "жара", "tnt music",
        "sony music", "viva", "a-one", "tracce", "муз-тв",
    ],
    "🌍 Регионы": [
        "астрахань", "astrahan", "белгород", "belgorod",
        "волгоград", "volgograd", "воронеж", "voronezh",
        "екатеринбург", "сочи", "sochi", "крым", "crimea",
        "севастополь", "simferopol", "ульяновск", "самара",
        "казань", "уфа", "челябинск", "пермь", "тула",
        "ярославль", "тюмень", "омск", "красноярск",
        "иркутск", "хабаровск", "владивосток", "сахалин",
        "мурманск", "архангельск", "вологда", "калининград",
        "nnov", "novosibirsk", "новосибирск",
        "ростов", "rostov", "краснодар", "krasnodar",
        "ставрополь", "stavropol", "махачкала", "грозный",
        "регион", "region", "область", "край", "республика",
        "твк", "tvk", "твр", "c1", "енисей", "enisey",
    ],
    "🌐 Международные": [
        "rtr planeta", "rtr-planeta", "channel one cis",
        "channel one eurasia", "ntv mir", "ren tv international",
        "rt ", "rt balkan", "rt en espanol", "rtg",
    ],
}

# Порядок категорий в плейлисте
CATEGORY_ORDER = [
    "📺 Федеральные",
    "📰 Новости",
    "⚽ Спорт",
    "🎬 Кино",
    "🎵 Музыка",
    "📚 Познавательные",
    "🎭 Развлечения",
    "🌍 Регионы",
    "🌐 Международные",
    "🚗 Авто",
    "💼 Бизнес",
    "🛒 Магазины",
    "🌿 Релакс",
    "🌤 Погода",
    "⛪ Религия",
    "📦 Прочее",
]


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


def get_group(extinf):
    m = re.search(r'group-title="([^"]*)"', extinf, re.IGNORECASE)
    return m.group(1).lower().strip() if m else ""


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


def extract_tvg_id(extinf):
    m = re.search(r'tvg-id="([^"]*)"', extinf)
    if not m:
        return ""
    tvg_id = m.group(1).strip()
    if "@" in tvg_id:
        tvg_id = tvg_id.split("@")[0]
    return tvg_id


def is_whitelisted(extinf):
    name = base_name(extinf)
    for w in WHITELIST:
        pattern = r'(?<![a-zа-яё0-9])' + re.escape(w) + r'(?![a-zа-яё0-9])'
        if re.search(pattern, name):
            return True
    return False


def is_bad_url(url):
    u = url.lower()
    if re.match(r'^https?://\d+\.\d+\.\d+\.\d+', u):
        return True
    for port in BAD_PORTS:
        if port in u:
            return True
    for dom in BAD_DOMAINS:
        if dom + "/" in u or dom + ":" in u or dom + "?" in u:
            return True
    return False


def is_kids(extinf):
    name = base_name(extinf)
    group = get_group(extinf)

    for exc in KIDS_EXCEPTIONS:
        if exc in name:
            return False

    for kw in KIDS_KEYWORDS:
        if len(kw) <= 4:
            pattern = r'(?<![a-zа-яё0-9])' + re.escape(kw) + r'(?![a-zа-яё0-9])'
            if re.search(pattern, name):
                return True
        else:
            if kw in name:
                return True

    for kw in ["kids", "детск", "мульт", "cartoon", "junior"]:
        if kw in group:
            return True

    return False


def is_blocked(extinf):
    name = base_name(extinf)
    for w in BLOCKED_CHANNELS:
        if w in name:
            return True
    return False


def load_quality_data():
    if not os.path.exists(QUALITY_FILE):
        print("Quality data not found: " + QUALITY_FILE + " (skip filter)")
        return {}
    try:
        with open(QUALITY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        print("Quality data loaded: " + str(len(data)) + " entries")
        return data
    except Exception as e:
        print("Quality data error: " + str(e))
        return {}


def is_dead_by_quality(extinf, quality_data):
    if not quality_data:
        return False
    if is_whitelisted(extinf):
        return False
    name = base_name(extinf)
    entry = quality_data.get(name)
    if not entry:
        return False
    return entry.get("action") == "remove"


def download_iptv_org_db():
    """Скачивает базу каналов IPTV-org. Возвращает {id: категория_ru}."""
    print("Downloading IPTV-org channels DB...")
    try:
        r = requests.get(IPTV_ORG_CHANNELS_URL, timeout=60)
        r.raise_for_status()
        data = r.json()
        print("IPTV-org DB: " + str(len(data)) + " channels loaded")
    except Exception as e:
        print("IPTV-org DB download failed: " + str(e) + " (fallback to keywords)")
        return {}

    mapping = {}
    for ch in data:
        ch_id = ch.get("id")
        cats = ch.get("categories", [])
        if not ch_id or not cats:
            continue
        for cat in cats:
            ru = IPTV_CATEGORY_MAP.get(cat)
            if ru:
                mapping[ch_id] = ru
                break

    print("IPTV-org DB mapped: " + str(len(mapping)) + " channels")
    return mapping


def get_category(extinf, iptv_db):
    """3 уровня: tvg-id (база) → group-title (источник) → keywords → Прочее."""
    # 1. tvg-id из базы IPTV-org
    tvg_id = extract_tvg_id(extinf)
    if tvg_id and tvg_id in iptv_db:
        return iptv_db[tvg_id], "tvg-id"

    # 2. group-title источника
    group = get_group(extinf)
    if group:
        for k, v in GROUP_TITLE_MAP.items():
            if k in group:
                return v, "group-title"

    # 3. Keywords по имени
    name = base_name(extinf)
    for category, keywords in CATEGORIES_KEYWORDS.items():
        for kw in keywords:
            if len(kw) <= 4:
                pattern = r'(?<![a-zа-яё0-9])' + re.escape(kw) + r'(?![a-zа-яё0-9])'
                if re.search(pattern, name):
                    return category, "keywords"
            else:
                if kw in name:
                    return category, "keywords"

    return "📦 Прочее", "fallback"


def set_group(extinf, category):
    if re.search(r'group-title="[^"]*"', extinf, re.IGNORECASE):
        return re.sub(r'group-title="[^"]*"', 'group-title="' + category + '"', extinf, count=1, flags=re.IGNORECASE)
    if 'tvg-id="' in extinf:
        return re.sub(r'(tvg-id="[^"]*")', r'\1 group-title="' + category + '"', extinf, count=1)
    return extinf.replace("#EXTINF:-1", '#EXTINF:-1 group-title="' + category + '"', 1)


def main():
    all_channels = []
    source_stats = {}

    for src in SOURCES:
        if not os.path.exists(src):
            print("Skip (not found): " + src)
            continue
        with open(src, "r", encoding="utf-8") as f:
            text = f.read()
        channels = parse_m3u(text)
        source_stats[src] = len(channels)
        all_channels.extend(channels)
        print(src + ": " + str(len(channels)) + " channels")

    print("Total before filter: " + str(len(all_channels)))

    non_kids = [ch for ch in all_channels if not is_kids(ch["extinf"])]
    dropped_kids = len(all_channels) - len(non_kids)
    print("After kids filter: " + str(len(non_kids)) + " (dropped kids: " + str(dropped_kids) + ")")

    non_blocked = [ch for ch in non_kids if not is_blocked(ch["extinf"])]
    dropped_blocked = len(non_kids) - len(non_blocked)
    print("After blocked filter: " + str(len(non_blocked)) + " (dropped blocked: " + str(dropped_blocked) + ")")

    quality_data = load_quality_data()
    non_dead = []
    dropped_dead = 0
    whitelist_protected = 0
    dropped_dead_names = []
    for ch in non_blocked:
        if is_whitelisted(ch["extinf"]):
            whitelist_protected += 1
            non_dead.append(ch)
            continue
        if is_dead_by_quality(ch["extinf"], quality_data):
            dropped_dead += 1
            if len(dropped_dead_names) < 10:
                dropped_dead_names.append(get_name(ch["extinf"]))
        else:
            non_dead.append(ch)
    print("After quality filter: " + str(len(non_dead)) + " (dropped dead: " + str(dropped_dead) + ", whitelist protected: " + str(whitelist_protected) + ")")

    best = {}
    for ch in non_dead:
        key = base_name(ch["extinf"])
        q = get_quality(ch["extinf"])
        clean = 0 if is_bad_url(ch["url"]) else 1
        score = (clean, q)

        if key not in best or score > best[key][0]:
            best[key] = (score, ch)

    deduped = [v[1] for v in best.values()]
    dropped_dups = len(non_dead) - len(deduped)
    print("After dedup: " + str(len(deduped)) + " (dropped dups: " + str(dropped_dups) + ")")

    # === Скачиваем базу IPTV-org ===
    iptv_db = download_iptv_org_db()

    # === Категоризация ===
    categorized = {}
    source_used = {"tvg-id": 0, "group-title": 0, "keywords": 0, "fallback": 0}

    for ch in deduped:
        cat, src_used = get_category(ch["extinf"], iptv_db)
        source_used[src_used] += 1
        if cat not in categorized:
            categorized[cat] = []
        categorized[cat].append(ch)

    print("")
    print("=== Категории ===")
    for cat in CATEGORY_ORDER:
        if cat in categorized:
            print("  " + cat + ": " + str(len(categorized[cat])))
    print("")
    print("=== Источник категории ===")
    for k, v in source_used.items():
        print("  " + k + ": " + str(v))

    # Сортировка
    sorted_channels = []
    for cat in CATEGORY_ORDER:
        if cat not in categorized:
            continue
        group = sorted(categorized[cat], key=lambda ch: get_name(ch["extinf"]).lower())
        for ch in group:
            ch["extinf"] = set_group(ch["extinf"], cat)
        sorted_channels.extend(group)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = []
    lines.append('#EXTM3U url-tvg="' + EPG_URL + '" x-tvg-url="' + EPG_URL + '"')
    lines.append("# Combined from " + str(len(SOURCES)) + " sources | Updated: " + now)
    lines.append("# Total: " + str(len(sorted_channels)) + " unique channels | Categorized")
    lines.append("")
    for ch in sorted_channels:
        lines.append(ch["extinf"])
        lines.append(ch["url"])
        lines.append("")

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("")
    print("Saved " + OUTPUT_FILE)
    print("")
    print("=== ИТОГО ===")
    print("Источников: " + str(len(source_stats)))
    print("Всего: " + str(len(all_channels)))
    print("Детских удалено: " + str(dropped_kids))
    print("Заблокированных удалено: " + str(dropped_blocked))
    print("Мёртвых по Quality удалено: " + str(dropped_dead))
    print("Whitelist защищено: " + str(whitelist_protected))
    print("Дублей удалено: " + str(dropped_dups))
    print("В финале: " + str(len(sorted_channels)))


main()
