import os
import re
import gzip
import io
import xml.etree.ElementTree as ET
import requests

EPG_URL = "https://iptvx.one/epg/epg_lite.xml.gz"
PLAYLIST = "all_channels.m3u"
EPG_PLAYLIST_URL = 'url-tvg="https://iptvx.one/epg/epg_lite.xml.gz"'
NOT_FOUND_FILE = "not_found_in_epg.txt"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

SKIP_URL_PATTERNS = [
    "kinowalk.hopto.org",
    "bl.rutube.ru",
    "cdn-dvr.ntv.ru",
]

FORCE_SKIP = [
    "мир",      # осторожно с "мир"
    "360°",
    "fresh ",
]

# === СИНОНИМЫ ===
# Ключ = как ХОТИМ (и как искать в EPG), значение = список наших вариантов
SYNONYMS = {
    # ============ ФЕДЕРАЛЬНЫЕ ============
    "первый канал": ["channel one", "channel one (russia)", "1tv", "ort", "1 канал", "первый"],
    "пятый канал": ["channel 5", "channel 5 (russia)", "5 kanal", "5канал", "пятый", "5 канал"],
    "россия 1": ["russia-1", "russia 1", "rossiya 1", "россия-1", "россия1"],
    "россия 24": ["russia-24", "russia 24", "rossiya 24", "россия-24", "россия24"],
    "россия к": ["russia-k", "russia k", "kultura", "россия-к", "культура", "россия к"],
    "россия к +2": ["russia-k +2", "russia k +2"],
    "россия к +4": ["russia-k +4", "russia k +4"],
    "россия к +7": ["russia-k +7", "russia k +7"],
    "нтв": ["ntv", "ntv (russia)", "нтв"],
    "нтв +1": ["ntv +1", "ntv (russia) +1"],
    "нтв +2": ["ntv +2", "ntv (russia) +2"],
    "нтв +4": ["ntv +4", "ntv (russia) +4"],
    "нтв +7": ["ntv +7", "ntv (russia) +7"],
    "тнт": ["tnt", "tnt (russia)", "тнт"],
    "тнт international": ["tnt international belarus", "тнт international"],
    "стс": ["sts", "sts (russia)", "стс"],
    "стс love": ["ctc love", "sts love", "стс love"],
    "тв-3": ["tv-3", "tv3", "тв3", "tv 3", "тв-3"],
    "рен тв": ["ren tv", "ren-tv", "rentv", "рен тв", "ren tv international"],
    "звезда": ["zvezda"],
    "звезда+": ["zvezda plus", "звезда+"],
    "твц": ["tvc", "tv centr", "тв центр", "твц"],
    "карусель": ["karusel", "carousel"],
    "че": ["che", "che!"],
    "ю": ["yu"],
    "суббота": ["subbota", "super"],
    "пятница": ["pyatnica", "friday", "piatnica"],
    "домашний": ["domashny", "domashniy"],
    "отр": ["otr"],
    "360": ["360° news", "360-lv news"],
    "спас": ["spas"],
    "союз": ["soyuz"],
    "8 канал": ["channel 8", "channel 8 (russia)"],
    "8 канал красноярск": ["channel 8 krasnoyarsk"],
    "8 канал новосибирск": ["channel 8 novosibirsk"],
    "тв-21": ["tv 21", "тв21", "tv21"],

    # ============ НОВОСТИ ============
    "беларусь 24": ["belarus-24", "belarus 24"],
    "известия": ["izvestia"],
    "москва 24": ["moskva 24"],
    "россия 24 новости": ["russia-24"],  # уже выше, но на всякий
    "соловьёв live": ["solovyov live", "соловьев live"],
    "вместе-рф": ["vmeste-rf"],
    "говорит москва": ["govorit moskva"],
    "продвижение": ["prodvizhenie"],
    "майдан": ["maidan"],
    "конгресс тв": ["kongress tv"],
    "первый информационный": ["perviy informationniy"],
    "дождь": ["tv rain"],
    "channel 9 israel": ["channel 9 (israel)"],

    # ============ СПОРТ ============
    "eurosport 1": ["eurosport1", "eurosport1 hd", "eurosport 1 hd"],
    "eurosport 2": ["eurosport2", "eurosport2 hd", "eurosport 2 hd"],
    "okko sport": ["okko sport", "okko sport hd"],
    "okko futbol": ["okko futbol", "okko futbol hd"],
    "okko prajm sport": ["okko prajm sport", "okko prajm sport hd"],
    "setanta sports 1 eurasia": ["setanta sports 1 eurasia", "setanta sports 1"],
    "setanta sports 2 eurasia": ["setanta sports 2 eurasia", "setanta sports 2"],
    "fast&funbox": ["fast&funbox", "fast funbox", "fast&funbox (russia)"],
    "mma-tv": ["mma-tv.com", "mma-tv"],
    "sportivnyy": ["sportivnyy"],
    "trace sport stars": ["trace sport stars russia"],
    "беларусь 5": ["belarus-5", "belarus 5"],
    "овертайм тв": ["оувертайм тв"],
    "удар": ["удар hd"],

    # ============ КИНО ============
    "блокбастер": ["blokbaster", "блокбастер"],
    "болт": ["bolt", "bolt (russia)"],
    "дом кино": ["dom kino", "дом кино"],
    "дом кино премиум": ["dom kino premium"],
    "дорама": ["dorama"],
    "душевное": ["dushevnoe"],
    "еврокино": ["evrokino"],
    "fan": ["fan", "fan hd"],
    "капитан фантастика": ["kapitan fantastika"],
    "кинобоевик": ["kinoboevik"],
    "кинопремьера": ["kinopremyera", "kinopremiera", "кинопремьера"],
    "комедийное": ["komediynoe", "комедийное"],
    "мировое кино": ["mirovoe kino"],
    "наше любимое кино украина": ["nashe lubimoe kino ukraine"],
    "наше мужское": ["nashe muzhskoe"],
    "остросюжетное": ["ostrosyuzhetnoye"],
    "премиальное": ["premialnoe"],
    "приключения": ["priklyucheniya"],
    "шокирующее": ["shokiruyushchee"],
    "время": ["время hd"],
    "киносат": ["киносат hd"],
    "нст": ["нст hd"],
    "кино 1": ["kino 1 (ukraine)", "kino 1"],
    "кино 2": ["kino 2"],
    "тв21": ["тв21"],

    # ============ МУЗЫКА ============
    "fashion tv": ["fashiontv", "fashion tv hd"],
    "hit fm": ["hit fm"],
    "kiss tv": ["kiss tv"],
    "kn music tv": ["kn music tv"],
    "kronehit": ["kronehit"],
    "мтв волгоград": ["mtv volgograd"],
    "radio m2o": ["radio m2o"],
    "songtv": ["songtv russia", "songtv"],
    "страна fm": ["strana fm"],
    "v2beat": ["v2beat", "v2beat hd"],
    "шансон тв": ["шансон тв"],
    "магнат": ["magnat"],

    # ============ ПОЗНАВАТЕЛЬНЫЕ ============
    "art": ["art", "art (russia)"],
    "большая азия": ["big asia"],
    "дикая охота": ["dikaya okhota"],
    "дикая рыбалка": ["dikaya rybalka"],
    "docubox": ["docubox russia"],
    "истоки": ["istoki"],
    "law tv": ["law tv"],
    "моя стихия": ["moya stikhiya"],
    "наука": ["nauka", "nauka (russia)"],
    "охотник и рыболов": ["ohotnik i rybolov"],
    "ost west 24": ["ost west 24"],
    "патриот": ["patriot"],
    "ржд тв": ["rzd tv"],
    "смотрим честный детектив": ["smotrim chestnyy detektiv", "смотрим честный детектив", "chestny-detektiv"],
    "travelxp": ["travelxp russia"],
    "трофей": ["trofei"],
    "в мире животных": ["v mire zhivotnykh"],
    "viju history": ["visast history"],
    "живая природа": ["zhivaya priroda"],
    "nat geo wild": ["nat geo wild", "nat geo wild hd"],

    # ============ РАЗВЛЕЧЕНИЯ ============
    "etv+": ["etv+"],
    "fashion&lifestyle": ["fashion&lifestyle"],
    "крик-тв": ["krik-tv"],
    "новый канал": ["novyi channel"],
    "теледом": ["teledom"],
    "tv pro": ["tv pro"],
    "wf мода": ["wf мода", "wf мода hd"],

    # ============ РЕГИОНЫ ============
    "86": ["86", "86 (1080p)"],
    "абаза тв": ["abaza tv"],
    "аист тв": ["aist tv"],
    "апсуа тв": ["apsua tv"],
    "арис 24": ["aris 24"],
    "архыз 24": ["arkhyz 24"],
    "астрахань 24": ["astrahan 24"],
    "белгород 24": ["belgorod 24"],
    "channel 12": ["channel 12 (1080p)"],
    "первый канал евразия": ["channel one eurasia"],
    "дагестан": ["dagestan"],
    "евразия": ["eurasia"],
    "грозный": ["groznyj"],
    "ингушетия": ["ingushetia"],
    "новгородское отв": ["novgorobltv"],
    "нтк 21": ["ntk 21"],
    "нтм": ["ntm"],
    "нтс": ["nts"],
    "нвк саха": ["nvk sakha"],
    "отв-прим": ["otv-prim"],
    "прима": ["prima", "prima (russia)"],
    "s1": ["s1"],
    "самара-гис": ["samara-gis"],
    "санкт-петербург": ["sankt-peterburg"],
    "сочи live": ["sochi live"],
    "сочи 24": ["sochi24"],
    "своё тв": ["svoyo tv"],
    "телеканал краснодар": ["telekanal krasnodar"],
    "ткр": ["tkr"],
    "тнв-татарстан": ["tnv-tatarstan"],
    "толк": ["tolk"],
    "тооку": ["tooku"],
    "твк": ["tvk", "tvk (russia)"],
    "югра тв": ["ugra-tv"],
    "волга": ["volga"],

    # ============ МЕЖДУНАРОДНЫЕ ============
    "беларусь 1": ["belarus-1"],
    "беларусь 4 витебск": ["belarus-4 vitebsk"],
    "первый канал снг": ["channel one cis"],
    "naxcivan tv": ["naxcivan tv"],
    "rt balkan": ["rt balkan"],
    "rt д": ["rt documentary russian"],
    "ртр-планета": ["rtr-planeta europe", "rtr planeta"],
    "rtvi": ["rtvi us", "rtvi"],
    "симон": ["simon"],
    "tsv": ["tsv"],
    "витебск": ["vitebsk"],
    "silk way": ["silk way"],

    # ============ МАГАЗИНЫ ============
    "нтв витрина": ["ntv vitrina"],
    "витрина тв": ["vitrina tv"],

    # ============ РЕЛИГИЯ ============
    "3abn": ["3abn russia", "3abn"],
    "надежда": ["hope channel russia"],
    "huzur tv": ["huzur tv"],
    "mana tserkov onlayn": ["mana tserkov' onlayn"],
    "tbn baltia": ["tbn baltia"],
    "tv mana": ["tv mana russkiy"],
}


def normalize(name):
    if not name:
        return ""
    n = name.lower().strip()
    n = n.replace('ё', 'е')
    n = re.sub(r'\([^)]*\)', '', n)
    n = re.sub(r'\[[^\]]*\]', '', n)
    n = re.sub(r'\b(hd|fhd|uhd|sd|4k|1080p|720p|576p|480p|1080i|576i|480i)\b', '', n)
    n = re.sub(r'[\u2500-\u27bf\u2b00-\u2bff]', '', n)
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def download_epg():
    print("Downloading EPG: " + EPG_URL)
    r = requests.get(EPG_URL, headers=HEADERS, timeout=180)
    r.raise_for_status()
    print("Downloaded " + str(len(r.content)) + " bytes (compressed)")
    with gzip.open(io.BytesIO(r.content), "rb") as f:
        data = f.read()
    print("Uncompressed: " + str(len(data)) + " bytes")
    return data


def build_epg_db(data):
    epg_db = {}
    count = 0
    print("Parsing EPG...")
    for event, elem in ET.iterparse(io.BytesIO(data), events=("end",)):
        if elem.tag == "channel":
            ch_id = elem.get("id")
            if ch_id:
                for dn in elem.findall("display-name"):
                    if dn.text:
                        key = normalize(dn.text)
                        if key and key not in epg_db:
                            epg_db[key] = (ch_id, dn.text.strip())
                count += 1
                if count % 1000 == 0:
                    print("  parsed " + str(count) + " channels")
            elem.clear()
        elif elem.tag == "programme":
            elem.clear()

    print("Total EPG channels: " + str(count) + ", unique names: " + str(len(epg_db)))
    return epg_db


def build_reverse_synonyms():
    """Разворачиваем SYNONYMS в: наш_вариант -> ключ_в_EPG."""
    rev = {}
    for epg_key, variants in SYNONYMS.items():
        epg_norm = normalize(epg_key)
        for v in variants:
            v_norm = normalize(v)
            if v_norm and v_norm not in rev:
                rev[v_norm] = epg_norm
    return rev


def get_name(extinf):
    return extinf.rsplit(",", 1)[-1].strip() if "," in extinf else extinf


def base_name(extinf):
    name = get_name(extinf)
    name = re.sub(r'\(?\s*(FHD|UHD|HD|SD|4K)\s*\)?', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\(?\s*\d{3,4}p\s*\)?', '', name, flags=re.IGNORECASE)
    name = re.sub(r'\[[^\]]*\]', '', name)
    return re.sub(r'\s+', ' ', name).strip().lower()


def is_skip_url(url):
    u = url.lower()
    for p in SKIP_URL_PATTERNS:
        if p in u:
            return True
    return False


def is_force_skip(name):
    n = name.lower().strip()
    for s in FORCE_SKIP:
        if s in n:
            return True
    return False


def set_name_in_line(line, new_name):
    parts = line.rsplit(",", 1)
    if len(parts) == 2:
        return parts[0] + "," + new_name
    return line


def set_tvg_id_in_line(line, tvg_id):
    if 'tvg-id="' in line:
        return re.sub(r'tvg-id="[^"]*"', 'tvg-id="' + tvg_id + '"', line, count=1)
    return line.replace("#EXTINF:-1", '#EXTINF:-1 tvg-id="' + tvg_id + '"', 1)


def find_in_epg(name_norm, epg_db, rev_syn):
    """Ищем: 1) точное, 2) через синонимы. Возвращает (tvg_id, epg_name, источник)."""
    # 1. Точное
    if name_norm in epg_db:
        tid, n = epg_db[name_norm]
        return tid, n, "exact"

    # 2. Синонимы
    epg_key_norm = rev_syn.get(name_norm)
    if epg_key_norm and epg_key_norm in epg_db:
        tid, n = epg_db[epg_key_norm]
        return tid, n, "synonym"

    return None, None, None


def main():
    if not os.path.exists(PLAYLIST):
        print("Файл не найден: " + PLAYLIST)
        return

    data = download_epg()
    epg_db = build_epg_db(data)

    if not epg_db:
        print("EPG база пуста, выходим.")
        return

    rev_syn = build_reverse_synonyms()
    print("Loaded synonyms: " + str(len(rev_syn)) + " variants")

    with open(PLAYLIST, "r", encoding="utf-8") as f:
        text = f.read()

    lines = text.splitlines()
    new_lines = []
    matched_exact = 0
    matched_synonym = 0
    fixed_epg = 0
    renamed = 0
    skipped_url = 0
    skipped_force = 0
    not_found_names = []

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTM3U"):
            new_lines.append("#EXTM3U " + EPG_PLAYLIST_URL)
            i += 1
            continue
        if line.startswith("#EXTINF"):
            url = ""
            if i + 1 < len(lines):
                url = lines[i + 1].strip()

            name = get_name(line)
            key = base_name(line)

            if is_skip_url(url):
                skipped_url += 1
                new_lines.append(line)
                i += 1
                continue

            if is_force_skip(name):
                skipped_force += 1
                new_lines.append(line)
                i += 1
                continue

            tvg_id, epg_name, src = find_in_epg(normalize(key), epg_db, rev_syn)

            if not (tvg_id and epg_name):
                # Попробуем от полного имени
                tvg_id, epg_name, src = find_in_epg(normalize(name), epg_db, rev_syn)

            if tvg_id and epg_name:
                if src == "exact":
                    matched_exact += 1
                else:
                    matched_synonym += 1

                m = re.search(r'tvg-id="([^"]*)"', line)
                if not m or not m.group(1).strip():
                    line = set_tvg_id_in_line(line, tvg_id)
                    fixed_epg += 1

                if get_name(line) != epg_name:
                    line = set_name_in_line(line, epg_name)
                    renamed += 1
            else:
                not_found_names.append((name, normalize(name)))

            new_lines.append(line)
            i += 1
            continue

        new_lines.append(line)
        i += 1

    with open(PLAYLIST, "w", encoding="utf-8") as f:
        f.write("\n".join(new_lines))

    with open(NOT_FOUND_FILE, "w", encoding="utf-8") as f:
        f.write("# Каналы, не найденные в EPG\n")
        f.write("# Всего: " + str(len(not_found_names)) + "\n")
        f.write("#\n")
        f.write("# Имя | Нормализованное имя (что искали в EPG)\n")
        f.write("#" + "-" * 70 + "\n")
        for name, norm in not_found_names:
            f.write(name + " | " + norm + "\n")

    print("")
    print("=== ИТОГО ===")
    print("Matched exact: " + str(matched_exact))
    print("Matched synonym: " + str(matched_synonym))
    print("Fixed tvg-id: " + str(fixed_epg))
    print("Renamed: " + str(renamed))
    print("Skipped by URL: " + str(skipped_url))
    print("Skipped by name: " + str(skipped_force))
    print("Not found in EPG: " + str(len(not_found_names)))
    print("Saved " + PLAYLIST)
    print("Saved " + NOT_FOUND_FILE)
    print("")

    if not_found_names:
        print("=== НЕ НАЙДЕНЫ В EPG (" + str(len(not_found_names)) + ") ===")
        for name, norm in not_found_names:
            print("  " + name + "  →  [" + norm + "]")
        print("=== КОНЕЦ ===")


main()
