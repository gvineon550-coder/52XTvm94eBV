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

SOURCES = ["playlist.m3u", "romaxa55_russia.m3u", "iptvorg_rus.m3u", "ufotv_playlist.m3u"]

BAD_PORTS = {":8080", ":8000", ":9999", ":8888"}
BAD_DOMAINS = (".xyz", ".tk", ".ml", ".cf", ".ga", "cinerama.uz",
               "tinyurl.com", "bit.ly", "goo.gl", "clck.ru", "is.gd", "t.co", "ow.ly")

KIDS_KEYWORDS = ["kids", "kid", "junior", "jr", "baby", "cartoon", "toon",
                 "nickelodeon", "nick", "nicktoons", "disney", "boomerang",
                 "gulli", "tiji", "davinci", "da vinci", "carousel",
                 "mult", "multimania", "multilandia", "kidzone",
                 "детск", "детcк", "мульт", "малыш", "карусель", "ребенок", "ребёнок"]
KIDS_EXCEPTIONS = ["start air", "start world"]

BLOCKED_CHANNELS = ["legislative rada", "rada tv", "рада", "rada"]
BLOCKED_URL_PATTERNS = ["radiorecord.hostingradio.ru", "radiorecord.ru", "hostingradio.ru"]

RADIO_NAME_KEYWORDS = [
    "radio 1", "radio rossii", "radio russia", "radio mir", "radio mayak",
    "vesti fm", "радио 1", "радио россии", "радио маяк", "радио шансон",
]

WHITELIST = ["channel one", "первый канал", "1tv", "ort",
             "ren tv", "ren-tv", "рен тв", "рен-тв", "rentv",
             "russia-1", "russia 1", "russia1", "россия-1", "россия 1",
             "rossiya-1", "rossiya 1", "russia-24", "россия-24", "rossiya-24",
             "russia-k", "россия-к", "kultura", "культура",
             "start air", "start-air", "startair", "start world", "start-world", "startworld",
             "ntv", "нтв"]

# URL-детекция (уникальные ID стримов)
URL_CATEGORY_MAP = [
    ("kinowalk.hopto.org", "🎬 Кино"),
    ("5c9327074e25ca86f3111d4085cbbb65", "📺 Федеральные"),  # U / Ю
]

IPTV_CATEGORY_MAP = {
    "news": "📰 Новости", "sports": "⚽ Спорт",
    "movies": "🎬 Кино", "series": "🎬 Кино", "comedy": "🎬 Кино",
    "classic": "🎬 Кино", "animation": "🎬 Кино",
    "music": "🎵 Музыка",
    "documentary": "📚 Познавательные", "science": "📚 Познавательные",
    "culture": "📚 Познавательные", "education": "📚 Познавательные",
    "entertainment": "🎭 Развлечения", "lifestyle": "🎭 Развлечения",
    "cooking": "🎭 Развлечения", "family": "🎭 Развлечения",
    "travel": "📚 Познавательные", "outdoor": "📚 Познавательные",
    "auto": "🚗 Авто", "business": "💼 Бизнес",
    "shop": "🛒 Магазины", "relax": "🌿 Релакс",
    "weather": "🌤 Погода", "religious": "⛪ Религия",
}

# ТОЧНЫЕ tvg-id → категория
TVG_CATEGORY = {
    # ФЕДЕРАЛЬНЫЕ
    "pervy": "📺 Федеральные", "ntv": "📺 Федеральные",
    "tnt": "📺 Федеральные", "tnt4": "📺 Федеральные",
    "che": "📺 Федеральные", "sts": "📺 Федеральные",
    "sts-love": "📺 Федеральные", "tv3-ru": "📺 Федеральные",
    "tvcentr": "📺 Федеральные", "piatnica": "📺 Федеральные",
    "domashny": "📺 Федеральные", "zvezda": "📺 Федеральные",
    "zvezda-plus": "📺 Федеральные", "mir": "📺 Федеральные",
    "mir-24": "📺 Федеральные", "kultura": "📺 Федеральные",
    "rossia1": "📺 Федеральные", "rossia-24": "📺 Федеральные",
    "rentv": "📺 Федеральные", "5kanal-ru": "📺 Федеральные",
    "piaty-int": "📺 Федеральные", "super": "📺 Федеральные",
    "yu": "📺 Федеральные", "otr": "📺 Федеральные",
    "tvc": "📺 Федеральные", "360": "📺 Федеральные",
    "360-lv": "📺 Федеральные",

    # КИНО
    "amedia-hit": "🎬 Кино", "amedia-2": "🎬 Кино",
    "vip-comedy": "🎬 Кино", "vip-megahit": "🎬 Кино",
    "vip-premiere": "🎬 Кино", "vip-serial": "🎬 Кино",
    "star-family": "🎬 Кино", "star-cinema": "🎬 Кино",
    "dom-kino": "🎬 Кино", "dom-kino-premium": "🎬 Кино",
    "kinopokaz": "🎬 Кино", "kinopremyera": "🎬 Кино",
    "kinohit": "🎬 Кино", "kinomix": "🎬 Кино",
    "kinokomedija": "🎬 Кино", "kinoseriya": "🎬 Кино",
    "kinosvidanie": "🎬 Кино", "kinouzhas": "🎬 Кино",
    "kinosemja": "🎬 Кино", "indiyskoye-kino": "🎬 Кино",
    "russkiy-illusion": "🎬 Кино", "evrokino": "🎬 Кино",
    "kapitan-fantastika": "🎬 Кино", "komediynoe": "🎬 Кино",
    "premialnoe": "🎬 Кино", "priklyucheniya": "🎬 Кино",
    "shokiruyushchee": "🎬 Кино", "ostrosyuzhetnoye": "🎬 Кино",
    "nashe-novoe-kino": "🎬 Кино", "rodnoe-kino": "🎬 Кино",
    "nonestopmovie": "🎬 Кино", "zagar": "🎬 Кино",
    "skladfilm": "🎬 Кино", "kinolenta": "🎬 Кино",
    "filmscope": "🎬 Кино", "kinoshkino": "🎬 Кино",
    "kinofans": "🎬 Кино", "kinojam": "🎬 Кино",
    "kinopro": "🎬 Кино", "kinofon": "🎬 Кино",
    "no_epg_cinema": "🎬 Кино",
    "pes": "🎬 Кино", "shef": "🎬 Кино",

    # СПОРТ
    "match": "⚽ Спорт", "match-tv": "⚽ Спорт",
    "match-arena": "⚽ Спорт", "match-boets": "⚽ Спорт",
    "match-igra": "⚽ Спорт", "match-strana": "⚽ Спорт",
    "match-ultra": "⚽ Спорт", "khl": "⚽ Спорт",
    "khl-prime": "⚽ Спорт", "setanta-sports": "⚽ Спорт",
    "eurosport": "⚽ Спорт", "football": "⚽ Спорт",
    "mma-tv": "⚽ Спорт", "okko-sport": "⚽ Спорт",
    "okko-futbol": "⚽ Спорт", "okko-prajm-sport": "⚽ Спорт",
    "extreme-sports": "⚽ Спорт", "sportivnyy": "⚽ Спорт",

    # МУЗЫКА
    "ru-tv": "🎵 Музыка", "muz-tv": "🎵 Музыка",
    "mtv": "🎵 Музыка", "vh1": "🎵 Музыка",
    "europa-plus": "🎵 Музыка", "songtv": "🎵 Музыка",
    "bridge": "🎵 Музыка", "mcm": "🎵 Музыка",
    "mcm-top": "🎵 Музыка", "shanson": "🎵 Музыка",
    "shanson-tv": "🎵 Музыка", "zhara": "🎵 Музыка",
    "tnt-music": "🎵 Музыка", "muzyka": "🎵 Музыка",
    "mezzo": "🎵 Музыка", "mezzo-live-hd": "🎵 Музыка",
    "1hd": "🎵 Музыка", "magnat": "🎵 Музыка",

    # НОВОСТИ
    "rbc": "📰 Новости", "rbc-tv": "📰 Новости",
    "izvestia": "📰 Новости", "moskva-24": "📰 Новости",
    "tsargrad": "📰 Новости", "tsargrad-tv": "📰 Новости",
    "tv-rain": "📰 Новости", "solovyov-live": "📰 Новости",
    "solovjinypomiot": "📰 Новости", "vmeste-rf": "📰 Новости",
    "prodvizhenie": "📰 Новости", "maidan": "📰 Новости",
    "osn": "📰 Новости", "rt": "📰 Новости",
    "pro-business": "💼 Бизнес",

    # ПОЗНАВАТЕЛЬНЫЕ
    "natgeo": "📚 Познавательные", "national-geographic": "📚 Познавательные",
    "discovery": "📚 Познавательные", "viju-explore": "📚 Познавательные",
    "viju-nature": "📚 Познавательные", "nauka": "📚 Познавательные",
    "istoriya": "📚 Познавательные", "big-planet": "📚 Познавательные",
    "chestny-detektiv": "📚 Познавательные", "law-tv": "📚 Познавательные",
    "rzd-tv": "📚 Познавательные", "big-asia": "📚 Познавательные",
    "travel-adventure": "📚 Познавательные",
    "dikaya-okhota": "📚 Познавательные", "dikaya-rybalka": "📚 Познавательные",
    "ohotnik-i-rybolov": "📚 Познавательные", "moya-stikhiya": "📚 Познавательные",
    "viasat-nature-history-hd": "📚 Познавательные",

    # РЕГИОНЫ
    "abaza-tv": "🌍 Регионы", "aist-tv": "🌍 Регионы",
    "apsua-tv": "🌍 Регионы", "aris-24": "🌍 Регионы",
    "arkhyz-24": "🌍 Регионы", "astrahan-24": "🌍 Регионы",
    "belgorod-24": "🌍 Регионы", "channel-8-krasnoyarsk": "🌍 Регионы",
    "channel-8-novosibirsk": "🌍 Регионы", "dagestan": "🌍 Регионы",
    "eurasia": "🌍 Регионы", "groznyj": "🌍 Регионы",
    "ingushetia": "🌍 Регионы", "novgor-obl-tv": "🌍 Регионы",
    "ntk-21": "🌍 Регионы", "ntm": "🌍 Регионы",
    "nts": "🌍 Регионы", "nvk-sakha": "🌍 Регионы",
    "otv-prim": "🌍 Регионы", "s1": "🌍 Регионы",
    "samara-gis": "🌍 Регионы", "sankt-peterburg": "🌍 Регионы",
    "sochi-live": "🌍 Регионы", "sochi24": "🌍 Регионы",
    "svoyo-tv": "🌍 Регионы", "telekanal-krasnodar": "🌍 Регионы",
    "tkr": "🌍 Регионы", "tnv-tatarstan": "🌍 Регионы",
    "tolk": "🌍 Регионы", "tooku": "🌍 Регионы",
    "ugra-tv": "🌍 Регионы", "ulytau": "🌍 Регионы",
    "volga": "🌍 Регионы", "prima": "🌍 Регионы",
    "kharkov-z": "🌍 Регионы",

    # МЕЖДУНАРОДНЫЕ
    "belarus1": "🌐 Международные", "belarus4": "🌐 Международные",
    "moldova1": "🌐 Международные", "moldova2": "🌐 Международные",
    "kentron-tv": "🌐 Международные", "naxcivan-tv": "🌐 Международные",
    "silk-way": "🌐 Международные", "rtr-planeta": "🌐 Международные",
    "rtrplaneta": "🌐 Международные",
    "rt-balkan": "🌐 Международные", "rtd-ru": "🌐 Международные",
    "rtg-tv": "🌐 Международные", "simon": "🌐 Международные",
    "stv-by": "🌐 Международные", "tsv": "🌐 Международные",
    "channel-one-cis": "🌐 Международные", "channel-one-eurasia": "🌐 Международные",
    "ntv-mir": "🌐 Международные", "ren-tv-international": "🌐 Международные",
    "rtvi-us": "🌐 Международные", "raz3international": "🌐 Международные",

    # МАГАЗИНЫ
    "shopping-live": "🛒 Магазины", "leomax-24": "🛒 Магазины",
    "ntv-vitrina": "🛒 Магазины", "vitrina-tv": "🛒 Магазины",

    # РЕЛИГИЯ
    "spas": "⛪ Религия", "soyuz": "⛪ Религия",
    "3abn-russia": "⛪ Религия", "hope-channel-russia": "⛪ Религия",

    # АВТО
    "auto-plus": "🚗 Авто", "avto-24": "🚗 Авто", "drive": "🚗 Авто",

    # РАЗВЛЕЧЕНИЯ
    "fashiontv": "🎭 Развлечения", "krik-tv": "🎭 Развлечения",
    "kvn-tv": "🎭 Развлечения", "tele-dom": "🎭 Развлечения",
    "world-fashion-channel": "🎭 Развлечения",
    "gags-network": "🎭 Развлечения",
}

GROUP_TITLE_MAP = {
    "movies": "🎬 Кино", "кино": "🎬 Кино", "cinema": "🎬 Кино", "фильмы": "🎬 Кино",
    "sport": "⚽ Спорт", "спорт": "⚽ Спорт",
    "news": "📰 Новости", "новости": "📰 Новости",
    "music": "🎵 Музыка", "музыка": "🎵 Музыка",
    "documentary": "📚 Познавательные", "познавательные": "📚 Познавательные",
    "entertainment": "🎭 Развлечения", "развлечения": "🎭 Развлечения",
    "auto": "🚗 Авто", "авто": "🚗 Авто",
    "shop": "🛒 Магазины",
    "religion": "⛪ Религия", "религия": "⛪ Религия",
}

CATEGORIES_KEYWORDS = {
    "🎬 Fresh": ["fresh adventure", "fresh family", "fresh fantastic",
                 "fresh horror", "fresh premiere", "fresh rating",
                 "fresh romantic", "fresh series", "fresh thriller",
                 "fresh cinema", "fresh comedy"],

    "⚽ Спорт": ["okko sport", "okko futbol", "okko prajm", "setanta",
                "mma-tv", "khl", "khl prime", "eurosport", "football",
                "match tv", "match! arena", "match! boets", "match! igra",
                "match! strana", "match! ultra", "sportivnyy", "extreme sport",
                "astrahan.ru sport", "formula 1"],

    "🎬 Кино": ["amedia", "viju", "tv1000", "tv 1000", "viasat",
                "kinopokaz", "kinopremyera", "kinohit", "kinomix",
                "kinokomedija", "kinoseriya", "kinosvidanie",
                "kinouzhas", "киноужас", "kinosemja",
                "premialnoe", "ostrosyuzhetnoye", "komediynoe",
                "dushevnoe", "evrokino", "horoshee kino",
                "kapitan fantastika", "priklyucheniya", "shokiruyushchee",
                "star family", "star cinema", "blockbuster",
                "dom kino", "indiyskoye", "russkiy illusion",
                "nashe novoe kino", "rodnoe kino", "mosfilm", "мосфильм",
                "megahit", "vip comedy", "vip premiere",
                "kinowalk", "movietoper", "timetomovie", "timetohorror",
                "blockbusters", "kinolampa", "videoarsenal",
                "cinema time", "scripachtv", "kinolenta", "kinofans",
                "kinofon", "kinopro", "kinojam", "kino24",
                "сериал", "serial", "vhs", "кассета", "kasseta",
                "film", "фильм", "movie", "кинотеатр", "kinoshkino",
                "filmscope", "skladfilm", "nonestopmovie", "ncd",
                "city eden kino", "cityeden kino",
                "city eden sirtaki", "city eden telenovella",
                "nevskiy", "невский",
                "perviy otdel", "первый отдел",
                "shef", "skoraya pomoshch", "pes",
                "nashe muzhskoe", "мужской",
                "время"],

    "📰 Новости": ["izvestia", "moskva 24", "rbc", "рбк", "solovyov",
                   "tsargrad", "tv rain", "vmeste-rf", "prodvizhenie",
                   "maidan", "osn", "russia today", "euronews",
                   "france 24", "dw ", "bbc news", "cnn",
                   "kongress"],

    "🎵 Музыка": ["ru.tv", "ru tv", "rutv", "муз-тв", "muz-tv", "mtv",
                  "vh1", "europa plus", "европа плюс", "music box",
                  "songtv", "mezzo", "muzyka", "1hd", "1 hd music",
                  "mcm", "shanson", "шансон", "zhara", "жара",
                  "tnt music", "kn music", "strana fm", "bridge",
                  "fashion tv", "fashiontv", "magnat",
                  "city eden classic music"],

    "📚 Познавательные": ["nat geo", "national geographic", "discovery",
                          "istoriya", "viju explore", "viju nature",
                          "nauka", "big planet", "big asia", "law tv",
                          "rzd tv", "chestny", "dikaya okhota", "dikaya rybalka",
                          "ohotnik", "moya stikhiya", "v mire zhivotnykh",
                          "zhivaya priroda", "travel+adventure", "health",
                          "med-", "recepty",
                          "istoki", "истоки",
                          "patriot", "патриот",
                          "dialogi o rybalke", "диалоги о рыбалке",
                          "oruzhie", "оружие",
                          "rybalka", "рыбалка",
                          "kto kuda", "кто куда",
                          "dacha", "дача",
                          "city eden medzdrav"],

    "🎭 Развлечения": ["fashion", "krik-tv", "kvn", "tele-dom",
                       "tnt4 comedy", "humor", "юмор",
                       "gagsnetwork", "gags",
                       "raz 3", "raz3",
                       "rutube tv",
                       "tv pro",
                       "аппетитный",
                       "бобер",
                       "зал суда",
                       "кухня тв",
                       "наша тема",
                       "телекафе",
                       "city eden play",
                       "teledom", "tele dom"],

    "🌍 Регионы": ["krasnoyarsk", "novosibirsk", "dagestan", "ingushetia",
                   "belgorod", "astrahan", "arkhyz", "abaza", "apsua",
                   "aris 24", "grozny", "uly", "ugra", "tooku", "tolk",
                   "tnv", "ntm", "nts", "nvk sakha", "volga", "krasnodar",
                   "prima", "sochi", "svoyo", "telekanal", "sankt-peterburg",
                   "novgor", "otv-prim", "ntk 21", "хабаровск", "иркутск",
                   "владивосток", "сахалин", "мурманск", "архангельск",
                   "вологда", "калининград", "ростов", "ставрополь",
                   "махачкала", "грозный", "твк", "tvk", "твр",
                   "енисей", "enisey", "nnov", "vitebsk", "витебск",
                   "s1", "samara-gis", "самара",
                   "tkr", "ткр",
                   "ulytau", "улытау",
                   "eurasia", "евразия",
                   "харьков"],

    "🌐 Международные": ["belarus", "moldova", "kentron", "naxcivan",
                         "silk way", "rtr planeta", "rtr-planeta", "rtvi",
                         "rt balkan", "rt documentary", "rtd", "rtg", "simon",
                         "channel one cis", "channel one eurasia",
                         "ntv mir", "ren tv international", "stv ",
                         "tsv", "vitebsk"],

    "🛒 Магазины": ["shopping live", "leomax", "vitrina", "shop"],

    "⛪ Религия": ["3abn", "hope channel", "soyuz", "союз", "спас"],

    "🚗 Авто": ["auto plus", "avto 24", "avto24", "drive", "авто",
                "city eden autogid"],

    "💼 Бизнес": ["pro business", "business"],

    "📺 Федеральные": ["channel one", "первый канал", "1tv",
                       "russia-1", "россия 1", "россия-1", "rossiya 1",
                       "russia-24", "россия 24", "россия-24",
                       "russia-k", "россия к", "россия-к", "kultura",
                       "нтв hd", "ntv (russia)", "ntv hd",
                       "рен тв", "ren tv",
                       "тнт hd", "tnt hd", "тнт 4", "tht hd", "tht4",
                       "стс hd", "sts hd", "ctc love", "ctc",
                       "тв3 hd", "tv-3 hd", "tv3",
                       "твц hd", "tvcentr", "tv centr",
                       "пятый канал", "channel 5 (russia)", "5 kanal",
                       "мир hd", "мир 24", "mir hd", "mir 24", "moy mir",
                       "отр", "otr",
                       "суббота", "subbota", "смотрим", "smotrim",
                       "пятница", "pyatnica", "friday",
                       "домашний", "domashny",
                       "звезда", "zvezda",
                       "360", "8 канал", "карусель", "karusel",
                       "че!", "che!", "ю ", "yu ",
                       "мир"],
}

CATEGORY_ORDER = ["📺 Федеральные", "📰 Новости", "⚽ Спорт", "🎬 Кино", "🎬 Fresh",
                  "🎵 Музыка", "📚 Познавательные", "🎭 Развлечения",
                  "🌍 Регионы", "🌐 Международные", "🚗 Авто", "💼 Бизнес",
                  "🛒 Магазины", "🌿 Релакс", "🌤 Погода", "⛪ Религия", "📦 Прочее"]


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


def is_blocked_url(url):
    u = url.lower()
    for p in BLOCKED_URL_PATTERNS:
        if p in u:
            return True
    return False


def is_radio_by_name(extinf):
    name = base_name(extinf)
    for kw in RADIO_NAME_KEYWORDS:
        if kw in name:
            return True
    return False


def load_quality_data():
    if not os.path.exists(QUALITY_FILE):
        return {}
    try:
        with open(QUALITY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
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
    print("Downloading IPTV-org channels DB...")
    try:
        r = requests.get(IPTV_ORG_CHANNELS_URL, timeout=60)
        r.raise_for_status()
        data = r.json()
        print("IPTV-org DB: " + str(len(data)) + " channels loaded")
    except Exception as e:
        print("IPTV-org DB failed: " + str(e))
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
                mapping[ch_id.lower()] = ru
                break
    print("IPTV-org DB mapped: " + str(len(mapping)) + " channels")
    return mapping


def get_category(extinf, url, iptv_db):
    url_lower = url.lower()
    for pattern, cat in URL_CATEGORY_MAP:
        if pattern in url_lower:
            return cat, "url"

    tvg_id = extract_tvg_id(extinf)
    if tvg_id:
        tvg_id_low = tvg_id.lower()
        if tvg_id_low in TVG_CATEGORY:
            return TVG_CATEGORY[tvg_id_low], "tvg-id"
        if tvg_id_low in iptv_db:
            return iptv_db[tvg_id_low], "tvg-id-db"
        t = tvg_id_low
        if any(p in t for p in ["kino", "film", "cinema", "kasseta", "serial"]):
            return "🎬 Кино", "tvg-pattern"
        if any(p in t for p in ["music", "radio", "mtv", "muz"]) and "brigde" not in t:
            return "🎵 Музыка", "tvg-pattern"
        if any(p in t for p in ["sport", "match", "futbol"]):
            return "⚽ Спорт", "tvg-pattern"
        if any(p in t for p in ["news"]) and "rtvi" not in t:
            return "📰 Новости", "tvg-pattern"

    group = get_group(extinf)
    if group:
        for k, v in GROUP_TITLE_MAP.items():
            if k in group:
                return v, "group-title"

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
            continue
        with open(src, "r", encoding="utf-8") as f:
            channels = parse_m3u(f.read())
        source_stats[src] = len(channels)
        all_channels.extend(channels)
        print(src + ": " + str(len(channels)) + " channels")

    print("Total before filter: " + str(len(all_channels)))

    non_kids = [ch for ch in all_channels if not is_kids(ch["extinf"])]
    dropped_kids = len(all_channels) - len(non_kids)
    print("After kids: " + str(len(non_kids)) + " (dropped: " + str(dropped_kids) + ")")

    non_blocked = []
    dropped_blocked = 0
    dropped_radio = 0
    for ch in non_kids:
        if is_blocked(ch["extinf"]):
            dropped_blocked += 1
            continue
        if is_blocked_url(ch["url"]):
            dropped_radio += 1
            continue
        if is_radio_by_name(ch["extinf"]):
            dropped_radio += 1
            continue
        non_blocked.append(ch)
    print("After blocked+radio: " + str(len(non_blocked)) + " (blocked: " + str(dropped_blocked) + ", radio: " + str(dropped_radio) + ")")

    quality_data = load_quality_data()
    non_dead = []
    dropped_dead = 0
    whitelist_protected = 0
    for ch in non_blocked:
        if is_whitelisted(ch["extinf"]):
            whitelist_protected += 1
            non_dead.append(ch)
            continue
        if is_dead_by_quality(ch["extinf"], quality_data):
            dropped_dead += 1
        else:
            non_dead.append(ch)
    print("After quality: " + str(len(non_dead)) + " (dead: " + str(dropped_dead) + ", wl: " + str(whitelist_protected) + ")")

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
    print("After dedup: " + str(len(deduped)) + " (dups: " + str(dropped_dups) + ")")

    iptv_db = download_iptv_org_db()

    categorized = {}
    source_used = {"url": 0, "tvg-id": 0, "tvg-id-db": 0, "tvg-pattern": 0, "group-title": 0, "keywords": 0, "fallback": 0}

    for ch in deduped:
        cat, src_used = get_category(ch["extinf"], ch["url"], iptv_db)
        source_used[src_used] = source_used.get(src_used, 0) + 1
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

    sorted_channels = []
    for cat in CATEGORY_ORDER:
        if cat not in categorized:
            continue
        group = sorted(categorized[cat], key=lambda ch: get_name(ch["extinf"]).lower())
        for ch in group:
            ch["extinf"] = set_group(ch["extinf"], cat)
        sorted_channels.extend(group)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = ['#EXTM3U url-tvg="' + EPG_URL + '" x-tvg-url="' + EPG_URL + '"',
             "# Combined from " + str(len(SOURCES)) + " sources | Updated: " + now,
             "# Total: " + str(len(sorted_channels)) + " unique channels | Categorized",
             ""]
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
    print("Всего: " + str(len(all_channels)))
    print("Детских: " + str(dropped_kids))
    print("Заблокированных: " + str(dropped_blocked))
    print("Радио: " + str(dropped_radio))
    print("Мёртвых: " + str(dropped_dead))
    print("Whitelist: " + str(whitelist_protected))
    print("Дублей: " + str(dropped_dups))
    print("В финале: " + str(len(sorted_channels)))


main()
