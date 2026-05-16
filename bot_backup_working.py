import telebot
from telebot import util
import google.generativeai as genai
import requests
import base64
import os
import re
import urllib.parse
import urllib3
from bs4 import BeautifulSoup

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("Не найден TELEGRAM_TOKEN в переменных окружения")

if not GOOGLE_API_KEY:
    raise ValueError("Не найден GOOGLE_API_KEY в переменных окружения")

genai.configure(api_key=GOOGLE_API_KEY)

SELECTED_MODEL = "models/gemini-2.5-flash"

bot = telebot.TeleBot(TELEGRAM_TOKEN)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/91.0.4472.124 Safari/537.36"
    )
}

LAW_URLS = {
    "ecocode": "https://adilet.zan.kz/rus/docs/K2100000400",
    "koap": "https://adilet.zan.kz/rus/docs/K1400000235",
    "atom": "https://adilet.zan.kz/rus/docs/Z1600000442",
    "nedra": "https://adilet.zan.kz/rus/docs/K1700000125",
    "trud": "https://adilet.zan.kz/rus/docs/K150000251_",
    "pozhar": "https://adilet.zan.kz/rus/docs/Z1400000188",
}

LAW_TITLES = {
    "ecocode": "Экологический кодекс РК от 02.01.2021 N 400-VI",
    "koap": "КоАП РК от 05.07.2014 N 235-V",
    "atom": "Закон РК Об использовании атомной энергии от 12.01.2016 N 442-V",
    "nedra": "Кодекс РК О недрах и недропользовании от 27.12.2017 N 125-VI",
    "trud": "Трудовой кодекс РК от 23.11.2015 N 414-V",
    "pozhar": "Закон РК О гражданской защите от 11.04.2014 N 188-V",
}

FILE_KEYWORDS = {
    "ecocode": [
        "нефт", "разлив", "розлив", "загрязнен", "загрязнение", "отход",
        "мусор", "свалк", "замазучен", "мазут", "масло", "нефтепродукт",
        "шлам", "земл", "почв", "вод", "сточн", "выброс", "атмосфер",
        "воздух", "рекультив", "ущерб", "экологич", "контейнер", "тбо",
        "коммунальн", "захоронен", "размещен", "утилизац", "раздельн",
        "сортировк", "урна", "пластов", "скважин", "факел", "эмисс", "сброс",
        "площадк", "накоплен", "подрядчик",
    ],
    "koap": [
        "штраф", "ответственност", "нарушени", "загрязнен", "загрязнение",
        "отход", "земл", "почв", "атмосфер", "вод", "недр", "радиац",
        "нефт", "мазут", "шлам", "мусор", "свалк", "контейнер", "масло",
        "раздельн", "сбор", "подрядчик",
    ],
    "atom": [
        "радиац", "излучен", "ядерн", "атомн", "изотоп", "дозиметр",
        "рао", "нро", "нуклид", "радионуклид", "фон", "доза", "зиверт",
        "мэд", "микрозиверт", "беккерель",
    ],
    "nedra": [
        "недр", "скважин", "месторожден", "добыч", "пластов",
        "углеводород", "нефт", "газ", "недропользован", "бурен",
    ],
    "trud": [
        "работник", "труд", "охран труда", "несчастн", "травм", "рабочее",
        "спецодежд", "сиз", "инструктаж", "опасн", "безопасност",
    ],
    "pozhar": [
        "пожар", "огнетушит", "эвакуац", "возгоран", "горюч", "огонь",
        "пожароопасн", "искр", "дым",
    ],
}

PRIORITY_PHRASES = {
    "замазуч": [
        "загрязнение земель",
        "загрязнение почвы нефтепродуктами",
        "экологические требования при использовании земель",
        "обращение с отходами",
        "ликвидация загрязнения",
    ],
    "масло": [
        "загрязнение земель маслом",
        "загрязнение почвы нефтепродуктами",
        "загрязнение территории нефтепродуктами",
        "экологические требования при использовании земель",
    ],
    "нефт": [
        "загрязнение земель нефтью",
        "загрязнение почвы нефтепродуктами",
        "экологический ущерб",
        "ликвидация последствий загрязнения",
    ],
    "мусор": [
        "обращение с отходами",
        "накопление отходов",
        "коммунальные отходы",
        "места накопления отходов",
        "несанкционированное размещение отходов",
        "раздельный сбор отходов",
    ],
    "контейнер": [
        "накопление отходов",
        "места накопления отходов",
        "коммунальные отходы",
        "обращение с отходами",
        "раздельный сбор отходов",
    ],
    "свалк": [
        "несанкционированное размещение отходов",
        "обращение с отходами",
        "загрязнение земель отходами",
    ],
    "раздельн": [
        "раздельный сбор отходов",
        "сортировка отходов",
        "обращение с отходами",
        "накопление отходов",
    ],
    "радиац": [
        "радиационная безопасность",
        "радиоактивные отходы",
        "источники ионизирующего излучения",
        "доза облучения",
    ],
}

BAD_ARTICLES = {
    "ecocode": ["3", "4"],
}

FORCED_KOAP_CONTEXT = {
    "environment_general": """
Статья 324. Нарушение санитарно-эпидемиологических и экологических требований по охране окружающей среды.
Нарушение норм санитарно-эпидемиологических и экологических требований, а также гигиенических нормативов по охране окружающей среды влечет предупреждение или штраф:
на физических лиц - 10 МРП,
на должностных лиц, субъектов малого предпринимательства или некоммерческие организации - 15 МРП,
на субъектов среднего предпринимательства - 20 МРП,
на субъектов крупного предпринимательства - 100 МРП.
Ссылка: https://adilet.zan.kz/rus/docs/K1400000235#z324
""",
    "waste_management": """
Статья 344. Нарушение экологических требований по управлению отходами.
Нарушение экологических требований к операциям по управлению отходами влечет штраф:
на физических лиц - 20 МРП,
на субъектов малого предпринимательства или некоммерческие организации - 50 МРП,
на субъектов среднего предпринимательства - 100 МРП,
на субъектов крупного предпринимательства - 300 МРП.
Ссылка: https://adilet.zan.kz/rus/docs/K1400000235#z344
"""
}

SYSTEM_PROMPT = (
    "Ты - нормативный ассистент инженера-эколога отдела ООС АО ПетроКазахстан Кумколь Ресорсиз, Казахстан.\n"
    "Пользователь составляет внутренние предписания, замечания, служебные записки и письма для цехов, участков, подрядчиков и ответственных лиц предприятия.\n"
    "Пользователь не является государственным инспектором, поэтому формулировки должны быть внутренними, рабочими и инженерными, без превышения полномочий.\n\n"

    "ГЛАВНАЯ ЗАДАЧА:\n"
    "По описанию нарушения или по описанию фото определить, какие требования законодательства Республики Казахстан могут быть нарушены, и подготовить короткий, точный и практичный текст для внутреннего предписания.\n\n"

    "ИСТОЧНИКИ:\n"
    "- Используй только те нормы, статьи и фрагменты законов, которые предоставлены ниже в контексте.\n"
    "- Не придумывай статьи, пункты, штрафы, названия законов и ссылки.\n"
    "- Никогда не используй законодательство Российской Федерации или других стран.\n"
    "- Если в предоставленном контексте нет подходящих конкретных норм, прямо напиши: В предоставленных фрагментах подходящих статей не найдено.\n"
    "- Не ссылайся на общие статьи о целях, задачах и принципах законодательства, если есть конкретные статьи с обязанностями, запретами, требованиями или ответственностью.\n"
    "- Статьи 3 и 4 Экологического кодекса РК не использовать как основное основание для предписания, если есть другие более конкретные статьи.\n\n"

    "ПРИОРИТЕТ ВЫБОРА НОРМ:\n"
    "1. Сначала выбирай конкретные статьи, где указаны обязанности, запреты, требования, нормативы, меры по предотвращению загрязнения, порядок обращения с отходами или требования к использованию земель.\n"
    "2. Затем выбирай статьи, связанные с экологическим ущербом, загрязнением почвы, вод, атмосферного воздуха, отходами, рекультивацией, производственным экологическим контролем.\n"
    "3. КоАП используй только в разделе о возможных последствиях при проверке государственными органами.\n"
    "4. Не ставь КоАП в раздел НАРУШЕНЫ ТРЕБОВАНИЯ, если это не требуется по смыслу. КоАП - это ответственность, а не производственное требование.\n"
    "5. Максимум используй 3 нормы. Лучше 1-2 точные статьи, чем 3 слабые.\n"
    "6. Не повторяй одну и ту же статью два раза. Если статья одна, но в ней несколько требований, объедини их в один пункт.\n\n"

    "КАК ПОНИМАТЬ НАРУШЕНИЯ:\n"
    "- Если указано замазучено, замазученность, мазут, нефть, нефтепродукты, масло, понимай это как возможное загрязнение территории, почвы, оборудования или площадки нефтепродуктами.\n"
    "- Если указано вокруг мусорки, контейнер, мусорный контейнер, ТБО, коммунальные отходы, понимай это как нарушение содержания места накопления отходов и риск загрязнения площадки или почвы.\n"
    "- Если указано нет раздельного сбора, отсутствует раздельный сбор, все отходы смешаны, понимай это как нарушение порядка раздельного накопления и обращения с отходами.\n"
    "- Если указано проверка территории подрядчика, понимай это как внутреннюю проверку объекта подрядной организации на территории предприятия.\n"
    "- Если указано разлив, порыв, утечка, понимай это как загрязнение окружающей среды с необходимостью локализации, очистки, вывоза загрязненного грунта и устранения причины.\n"
    "- Если указано свалка, мусор на земле, разбросан мусор, понимай это как ненадлежащее обращение с отходами и нарушение санитарного или экологического порядка на территории.\n"
    "- Если указано радиация, фон, дозиметр, МЭД, радионуклиды, понимай это как вопрос радиационной безопасности и обращения с радиоактивными веществами или отходами.\n"
    "- Опечатки, разговорные выражения и неполные фразы понимай по контексту.\n\n"

    "СТИЛЬ ОТВЕТА:\n"
    "- Пиши кратко, понятно и по-деловому.\n"
    "- Не пиши длинные юридические рассуждения.\n"
    "- Не используй формулировки от имени государственного инспектора.\n"
    "- Не пиши вы обязаны слишком резко. Лучше использовать: необходимо, требуется, следует обеспечить, принять меры.\n"
    "- Формулировки должны быть пригодны для копирования во внутреннее предписание или служебную переписку.\n"
    "- Если нарушение описано коротко, сам сформулируй его инженерно и конкретно.\n\n"

    "ФОРМАТ ОТВЕТА СТРОГО СОБЛЮДАТЬ:\n\n"

    "НАРУШЕНИЕ:\n"
    "[Одним предложением опиши, что выявлено. Например: На территории подрядчика выявлена замазученность вокруг контейнерной площадки для накопления отходов и отсутствие раздельного сбора отходов, что создает риск загрязнения почвы нефтепродуктами.]\n\n"

    "НАРУШЕНЫ ТРЕБОВАНИЯ:\n"
    "1. [Название закона] - статья [номер] - [название статьи, если оно есть]\n"
    "[Кратко своими словами суть требования из предоставленного фрагмента. Не более 2 строк.]\n"
    "Ссылка: [ссылка на adilet.zan.kz, если она есть в контексте]\n\n"

    "2. [Если есть вторая подходящая статья]\n"
    "[Краткая суть требования]\n"
    "Ссылка: [ссылка]\n\n"

    "ЧТО НЕОБХОДИМО УСТРАНИТЬ:\n"
    "- Очистить замазученную территорию или поверхность.\n"
    "- Убрать загрязненный грунт или загрязненные материалы с передачей в установленное место накопления или обращения с отходами.\n"
    "- Установить и устранить причину загрязнения.\n"
    "- Обеспечить содержание контейнерной площадки и прилегающей территории в надлежащем санитарном и экологическом состоянии.\n"
    "- Организовать раздельный сбор отходов по видам отходов.\n"
    "- При необходимости выполнить фотофиксацию после устранения и представить подтверждение в ООС.\n\n"

    "ПРИ ПРОВЕРКЕ ГОСОРГАНАМИ:\n"
    "[Если в контексте есть КоАП РК статья 324 или статья 344, обязательно укажи их в этом разделе, если они подходят по смыслу нарушения.]\n"
    "[Для загрязнения территории, почвы, земли, замазученности, масла, нефти или нефтепродуктов используй КоАП РК статью 324, если она есть в контексте.]\n"
    "[Для отсутствия раздельного сбора отходов, неправильного накопления отходов, мусора, контейнеров, ТБО, коммунальных отходов используй КоАП РК статью 344, если она есть в контексте.]\n"
    "[Если подходят обе статьи, укажи обе.]\n"
    "[Формулируй осторожно: при проверке госорганами нарушение может быть квалифицировано по следующим статьям КоАП РК.]\n"
    "[Размер штрафа указывай в МРП. В тенге указывай только для 2026 года из расчета 1 МРП = 4325 тенге.]\n"
    "[Не пиши, что подходящих статей КоАП не найдено, если в контексте есть статья 324 или 344.]\n\n"

    "ВАЖНО:\n"
    "- Не используй статьи 3 и 4 Экологического кодекса как основное нарушение.\n"
    "- Не делай вывод, что причинен экологический ущерб, если из описания ясно только наличие загрязнения. Пиши осторожно: создает риск загрязнения, может привести к загрязнению, требует устранения.\n"
    "- Если есть фото, сначала кратко опиши, что видно на фото, затем дай нормы.\n"
)

PHOTO_PROMPT = (
    "Ты помощник инженера-эколога нефтегазового предприятия в Казахстане.\n"
    "Посмотри на фото и кратко опиши, какое экологическое, санитарное, производственное или природоохранное нарушение видно.\n"
    "Пиши 1-2 предложения.\n"
    "Если видна замазученность, нефть, мазут, масло, пятна на земле, грязь вокруг контейнера или мусорки, так и напиши.\n"
    "Если видно отсутствие раздельного сбора отходов, смешанные отходы, переполненный контейнер или мусор вокруг контейнера, так и напиши.\n"
    "Если нарушение не видно явно, напиши осторожно: по фото возможно имеется нарушение, требуется уточнение на месте.\n"
    "Не выдумывай то, чего не видно на фото."
)

def normalize_query(query):
    if not query:
        return ""

    text = query.lower()

    replacements = {
        "мусорки": "мусорный контейнер контейнерная площадка место накопления отходов раздельный сбор отходов",
        "мусорка": "мусорный контейнер контейнерная площадка место накопления отходов раздельный сбор отходов",
        "мусорный бак": "мусорный контейнер контейнерная площадка место накопления отходов",
        "замазучено": "замазученность загрязнение нефтепродуктами загрязнение почвы загрязнение земель",
        "замазученно": "замазученность загрязнение нефтепродуктами загрязнение почвы загрязнение земель",
        "замазучена": "замазученность загрязнение нефтепродуктами загрязнение почвы загрязнение земель",
        "замазученность": "замазученность загрязнение нефтепродуктами загрязнение почвы загрязнение земель",
        "нефть": "нефть нефтепродукты загрязнение почвы загрязнение земель",
        "мазут": "мазут нефтепродукты загрязнение почвы загрязнение земель",
        "масло": "масло нефтепродукты загрязнение почвы загрязнение земель",
        "тбо": "коммунальные отходы отходы место накопления отходов контейнерная площадка раздельный сбор отходов",
        "нет раздельного сбора": "отсутствие раздельного сбора отходов нарушение обращения с отходами",
        "раздельного сбора нет": "отсутствие раздельного сбора отходов нарушение обращения с отходами",
        "все загрязнено": "загрязнение территории загрязнение почвы загрязнение земель",
        "всё загрязнено": "загрязнение территории загрязнение почвы загрязнение земель",
    }

    expanded = text

    for key, value in replacements.items():
        if key in text:
            expanded += " " + value

    for key, phrases in PRIORITY_PHRASES.items():
        if key in text:
            expanded += " " + " ".join(phrases)

    return expanded

def get_relevant_laws(query):
    query_expanded = normalize_query(query)
    words = set(w for w in re.findall(r"[а-яёА-ЯЁ]{4,}", query_expanded.lower()))

    laws_to_check = set()

    for law_key, keywords in FILE_KEYWORDS.items():
        for kw in keywords:
            if any(kw in w or w in kw for w in words):
                laws_to_check.add(law_key)
                break

    laws_to_check.add("koap")

    if not laws_to_check - {"koap"}:
        laws_to_check.add("ecocode")

    return laws_to_check

def make_search_queries(query):
    query_expanded = normalize_query(query)
    query_lower = query_expanded.lower()

    queries = [query_expanded]

    if any(x in query_lower for x in ["замазуч", "нефт", "мазут", "масло", "нефтепродукт"]):
        queries.extend([
            "загрязнение земель нефтепродуктами",
            "загрязнение почвы нефтепродуктами",
            "экологические требования при использовании земель",
            "ликвидация загрязнения земель",
            "обращение с отходами загрязненный грунт",
        ])

    if any(x in query_lower for x in ["мусор", "контейнер", "тбо", "коммунальн", "отход"]):
        queries.extend([
            "обращение с отходами",
            "накопление отходов",
            "коммунальные отходы",
            "несанкционированное размещение отходов",
            "контейнерная площадка отходы",
            "раздельный сбор отходов",
        ])

    if any(x in query_lower for x in ["раздельн", "сортировк", "сбор отход"]):
        queries.extend([
            "раздельный сбор отходов",
            "сортировка отходов",
            "экологические требования по управлению отходами",
        ])

    if any(x in query_lower for x in ["радиац", "фон", "дозиметр", "мэд", "рао", "нро"]):
        queries.extend([
            "радиационная безопасность",
            "радиоактивные отходы",
            "источники ионизирующего излучения",
            "доза облучения",
        ])

    clean_queries = []

    for q in queries:
        q = q.strip()
        if q and q not in clean_queries:
            clean_queries.append(q)

    return clean_queries[:8]

def search_on_adilet(query, law_key=None):
    try:
        if law_key and law_key in LAW_URLS:
            doc_id = LAW_URLS[law_key].split("/")[-1]
            search_url = (
                "https://adilet.zan.kz/rus/search/content?q="
                + urllib.parse.quote(query)
                + "&doc="
                + doc_id
            )
        else:
            search_url = (
                "https://adilet.zan.kz/rus/search/content?q="
                + urllib.parse.quote(query)
            )

        response = requests.get(search_url, headers=HEADERS, timeout=20, verify=False)
        soup = BeautifulSoup(response.text, "html.parser")

        results = []
        items = soup.select("div.search-result-item")[:5]

        for item in items:
            link = item.select_one("a")
            snippet = item.select_one("div.snippet, p")

            if link:
                href = link.get("href", "")

                if href.startswith("http"):
                    url = href
                else:
                    url = "https://adilet.zan.kz" + href

                results.append({
                    "title": link.get_text(strip=True),
                    "url": url,
                    "snippet": snippet.get_text(strip=True)[:700] if snippet else "",
                })

        return results

    except Exception as e:
        print("Ошибка поиска на adilet: " + str(e))
        return []

def article_number(block):
    match = re.search(r"Статья\s+(\d+)", block.strip())

    if match:
        return match.group(1)

    return None

def is_bad_article(law_key, block):
    number = article_number(block)

    if not number:
        return False

    bad_numbers = BAD_ARTICLES.get(law_key, [])

    return number in bad_numbers

def score_article(block, query, law_key):
    block_lower = block.lower()
    query_expanded = normalize_query(query)
    words = set(w for w in re.findall(r"[а-яёА-ЯЁ]{4,}", query_expanded.lower()))

    score = 0

    for w in words:
        if w in block_lower:
            score += 2

    strong_terms = [
        "обязан", "обязаны", "запрещ", "не допускается", "должны",
        "требования", "загрязнен", "загрязнение", "отход", "земель",
        "почв", "ликвидац", "рекультивац", "ущерб", "норматив",
        "производственный экологический контроль", "эмисси", "сброс",
        "выброс", "вод", "атмосфер", "радиацион", "раздельн", "накоплен",
        "сортировк", "коммунальн",
    ]

    for term in strong_terms:
        if term in block_lower:
            score += 3

    if law_key == "koap":
        if "влечет штраф" in block_lower or "влекут штраф" in block_lower:
            score += 10
        if "субъектов крупного предпринимательства" in block_lower:
            score += 4
        if "экологических требований" in block_lower:
            score += 4
        if "управлению отходами" in block_lower:
            score += 8
        if "охране окружающей среды" in block_lower:
            score += 8

    if law_key == "ecocode":
        if "цель" in block_lower and "задач" in block_lower:
            score -= 20
        if "принцип" in block_lower:
            score -= 15

    if any(x in query_expanded for x in ["замазуч", "нефт", "мазут", "масло", "нефтепродукт"]):
        for term in ["загрязнение земель", "почв", "нефт", "рекультивац", "ликвидац", "земель"]:
            if term in block_lower:
                score += 6

    if any(x in query_expanded for x in ["мусор", "контейнер", "отход", "тбо", "коммунальн", "раздельн"]):
        for term in ["отход", "накоплен", "сбор", "размещен", "захоронен", "коммунальн", "раздельн", "сортировк"]:
            if term in block_lower:
                score += 6

    return score

def fetch_article_text(law_key, query):
    if law_key not in LAW_URLS:
        return ""

    try:
        url = LAW_URLS[law_key]
        response = requests.get(url, headers=HEADERS, timeout=25, verify=False)

        if response.status_code != 200:
            print("Не удалось загрузить " + law_key + ": " + str(response.status_code))
            return ""

        soup = BeautifulSoup(response.text, "html.parser")

        content = soup.select_one("div.document-text, div.law-text, article, #document")

        if not content:
            content = soup

        full_text = content.get_text(separator="\n", strip=True)

        blocks = re.split(r"(?=Статья\s+\d+)", full_text)
        scored = []

        for block in blocks:
            block = block.strip()

            if len(block) < 80:
                continue

            if is_bad_article(law_key, block):
                continue

            score = score_article(block, query, law_key)

            if score > 0:
                number = article_number(block)
                article_link = url

                if number:
                    article_link = url + "#z" + number

                block_short = block[:1800]
                block_with_link = block_short + "\nСсылка: " + article_link
                scored.append((score, block_with_link))

        scored.sort(key=lambda x: x[0], reverse=True)

        selected = [b for _, b in scored[:5]]

        if selected:
            return "\n\n".join(selected)

        return ""

    except Exception as e:
        print("Ошибка загрузки " + law_key + ": " + str(e))
        return ""

def fetch_search_context(query, law_key):
    context = ""
    queries = make_search_queries(query)

    for q in queries[:4]:
        results = search_on_adilet(q, law_key)

        for result in results:
            if result.get("title") or result.get("snippet"):
                context += (
                    "\nРезультат поиска: "
                    + result.get("title", "")
                    + "\n"
                    + result.get("snippet", "")
                    + "\nСсылка: "
                    + result.get("url", "")
                    + "\n"
                )

    return context[:4000]

def get_forced_koap_context(query):
    query_expanded = normalize_query(query).lower()
    context = ""

    environment_words = [
        "замазуч", "нефт", "мазут", "масло", "нефтепродукт",
        "загрязнен", "загрязнение", "почв", "земл", "территор",
        "разлив", "розлив", "пятно",
    ]

    waste_words = [
        "мусор", "мусорка", "контейнер", "тбо", "коммунальн",
        "отход", "раздельн", "сбор", "накоплен", "свалк",
        "сортировк", "урна",
    ]

    if any(word in query_expanded for word in environment_words):
        context += "\n" + FORCED_KOAP_CONTEXT["environment_general"] + "\n"

    if any(word in query_expanded for word in waste_words):
        context += "\n" + FORCED_KOAP_CONTEXT["waste_management"] + "\n"

    return context

def build_context(query):
    laws_to_check = get_relevant_laws(query)

    forced_koap = get_forced_koap_context(query)

    koap_context = ""
    if forced_koap:
        koap_context += "\n=== КоАП РК от 05.07.2014 N 235-V - статьи для раздела ответственности ===\n"
        koap_context += forced_koap
        koap_context += "\n"

    laws_context = ""

    for law_key in laws_to_check:
        title = LAW_TITLES.get(law_key, law_key)

        article_text = fetch_article_text(law_key, query)
        search_text = fetch_search_context(query, law_key)

        if article_text or search_text:
            laws_context += "\n=== " + title + " ===\n"

            if article_text:
                laws_context += article_text + "\n"

            if search_text:
                laws_context += "\nДополнительные результаты поиска по adilet:\n" + search_text + "\n"

    max_total_length = 20000
    available_for_laws = max_total_length - len(koap_context)

    if available_for_laws < 5000:
        available_for_laws = 5000

    final_context = koap_context + laws_context[:available_for_laws]

    return final_context[:max_total_length]

def send_long_message(chat_id, text):
    if not text:
        bot.send_message(chat_id, "Пустой ответ.")
        return

    for part in util.smart_split(text, chars_per_string=3000):
        bot.send_message(chat_id, part)

@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    bot.send_message(
        message.chat.id,
        "Нормативный ассистент ПККР\n\n"
        "Опиши нарушение или отправь фото.\n\n"
        "Примеры:\n"
        "- Замазучено вокруг мусорки\n"
        "- Проверка территории подрядчика, нет раздельного сбора отходов, вокруг мусорки загрязнено маслом\n"
        "- Разлив нефти на скважине\n"
        "- Замазученность вокруг контейнеров\n"
        "- Несанкционированная свалка ТБО\n"
        "- Превышение радиационного фона\n"
        "- Нарушение охраны труда\n"
        "- Нарушение пожарной безопасности"
    )

@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    wait_msg = bot.send_message(message.chat.id, "Анализирую фото и ищу нормы РК...")

    try:
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        file_url = (
            "https://api.telegram.org/file/bot"
            + TELEGRAM_TOKEN
            + "/"
            + file_info.file_path
        )

        photo_bytes = requests.get(file_url, timeout=30).content
        photo_b64 = base64.b64encode(photo_bytes).decode("utf-8")
        caption = message.caption or ""

        model = genai.GenerativeModel(SELECTED_MODEL)

        photo_response = model.generate_content([
            PHOTO_PROMPT + "\n\nПодпись пользователя: " + caption,
            {"mime_type": "image/jpeg", "data": photo_b64}
        ])

        violation_desc = photo_response.text.strip()
        context = build_context(violation_desc + " " + caption)

        if not context:
            bot.edit_message_text(
                "Не удалось получить подходящие нормы с adilet.zan.kz. Попробуйте позже или опишите нарушение текстом подробнее.",
                message.chat.id,
                wait_msg.message_id
            )
            return

        full_query = (
            SYSTEM_PROMPT
            + "\n\n=== ФРАГМЕНТЫ ИЗ АКТУАЛЬНЫХ ЗАКОНОВ РК И ADILET ===\n"
            + context
            + "\n\n=== НАРУШЕНИЕ НА ФОТО ===\n"
            + violation_desc
            + "\n\n=== ПОДПИСЬ ПОЛЬЗОВАТЕЛЯ ===\n"
            + caption
        )

        response = model.generate_content(full_query)
        answer = response.text.strip()

        bot.delete_message(message.chat.id, wait_msg.message_id)
        bot.send_message(message.chat.id, "На фото: " + violation_desc)
        send_long_message(message.chat.id, answer)

    except Exception as e:
        try:
            bot.edit_message_text(
                "Ошибка: " + str(e),
                message.chat.id,
                wait_msg.message_id
            )
        except Exception:
            bot.send_message(message.chat.id, "Ошибка: " + str(e))

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_text = message.text or ""

    wait_msg = bot.send_message(message.chat.id, "Ищу в актуальных законах РК...")

    try:
        context = build_context(user_text)

        if not context:
            bot.edit_message_text(
                "Не удалось получить подходящие нормы с adilet.zan.kz. Попробуйте позже или опишите нарушение подробнее.",
                message.chat.id,
                wait_msg.message_id
            )
            return

        model = genai.GenerativeModel(SELECTED_MODEL)

        full_query = (
            SYSTEM_PROMPT
            + "\n\n=== ФРАГМЕНТЫ ИЗ АКТУАЛЬНЫХ ЗАКОНОВ РК И ADILET ===\n"
            + context
            + "\n\n=== НАРУШЕНИЕ ===\n"
            + user_text
        )

        response = model.generate_content(full_query)
        answer = response.text.strip()

        bot.delete_message(message.chat.id, wait_msg.message_id)
        send_long_message(message.chat.id, answer)

    except Exception as e:
        try:
            bot.edit_message_text(
                "Ошибка: " + str(e),
                message.chat.id,
                wait_msg.message_id
            )
        except Exception:
            bot.send_message(message.chat.id, "Ошибка: " + str(e))

print("БОТ ЗАПУЩЕН - adilet.zan.kz + Gemini + pyTelegramBotAPI + КоАП в начале контекста")

bot.polling(none_stop=True, interval=1)
