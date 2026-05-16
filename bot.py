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

SELECTED_MODEL = os.environ.get("GEMINI_MODEL", "models/gemini-2.5-flash")

bot = telebot.TeleBot(TELEGRAM_TOKEN)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0 Safari/537.36"
    )
}

LAW_URLS = {
    "ecocode": "https://adilet.zan.kz/rus/docs/K2100000400",
    "koap": "https://adilet.zan.kz/rus/docs/K1400000235",
}

LAW_TITLES = {
    "ecocode": "Экологический кодекс РК от 02.01.2021 N 400-VI",
    "koap": "КоАП РК от 05.07.2014 N 235-V",
}

ECO_KEYWORDS = [
    "эколог", "загряз", "замазуч", "нефт", "масло", "мазут", "нефтепродукт",
    "разлив", "розлив", "утеч", "пятно", "грунт", "почв", "земл", "территор",
    "отход", "мусор", "тбо", "коммунальн", "контейнер", "урна", "свалк",
    "раздельн", "сортиров", "накоплен", "хранен", "складирован", "тара",
    "маркиров", "журнал", "учет", "учёт", "накладн", "акт", "талон", "взвеш",
    "ртут", "ламп", "люминесцент", "батар", "аккумулятор", "электрон", "лом",
    "ветош", "сорбент", "фильтр", "отработан", "шина", "поддон",
    "нефтешлам", "шлам", "буров", "раствор", "пластов", "сточн", "вода",
    "сброс", "перелив", "кнс", "кос", "биопруд", "рвс", "упсв", "бкнс",
    "факел", "учетчик", "учётчик", "расходомер", "сжигаем", "газ",
    "выброс", "атмосфер", "дым", "пыл", "запах", "пэк", "проб", "лаборатор",
    "рекультив", "восстанов", "очистк", "ликвидац",
]

NON_ECO_KEYWORDS = [
    "огнетуш", "пожар", "каск", "без каски", "инструктаж", "электр",
    "удлинитель", "розетка", "ночная смена", "смена", "зарплата", "договор",
    "подряд", "радиац", "мэд", "доза", "вхнро",
]

BAD_ARTICLES = {
    "ecocode": {"3", "4"},
}

WEAK_ECO_ARTICLES = {"397"}

SYSTEM_PROMPT = (
    "Ты - Эко Помощник ПККР, ассистент инженера-эколога для внутренней проверки объектов и подрядчиков в Казахстане.\n"
    "Работай только по экологическому направлению.\n"
    "Используй только предоставленные ниже фрагменты Экологического кодекса РК и КоАП РК.\n"
    "Не используй пожарную безопасность, охрану труда, трудовой кодекс, гражданский кодекс, радиацию, санитарные правила и ПУО.\n"
    "Если вопрос не экологический, напиши: В текущей версии анализируются только экологические замечания.\n\n"
    "Главная задача:\n"
    "По фото или тексту определить экологическое замечание, возможные статьи Экологического кодекса РК, действия по устранению и возможную ответственность по КоАП РК.\n\n"
    "Строгие правила:\n"
    "- Не придумывай статьи, пункты, ссылки, штрафы и названия документов.\n"
    "- Если статьи нет в предоставленном контексте, не указывай ее.\n"
    "- Не используй статьи 3 и 4 Экологического кодекса как основание нарушения.\n"
    "- Не используй статью 397 Экологического кодекса, если запрос не связан с бурением, скважинами, добычей, недропользованием или проектными документами.\n"
    "- Не повторяй одну и ту же статью два раза.\n"
    "- КоАП указывай только в разделе ПРИ ПРОВЕРКЕ ГОСОРГАНАМИ.\n"
    "- Не делай категоричный вывод о причинении экологического ущерба только по фото или короткому описанию. Пиши осторожно: создает риск загрязнения, может привести к загрязнению, требует устранения.\n"
    "- Не используй Markdown-разметку: не ставь звездочки, таблицы, решетки и лишнее форматирование.\n"
    "- Пиши коротко, инженерно и по делу.\n\n"
    "Что считать экологическими замечаниями:\n"
    "- замазученность, загрязнение территории, земли, почвы, грунта;\n"
    "- разлив или утечка нефти, масла, нефтепродуктов, пластовой воды, сточных вод;\n"
    "- отходы вне установленного места, мусор вокруг контейнеров, переполненные контейнеры;\n"
    "- отсутствие раздельного сбора отходов, смешивание отходов;\n"
    "- нарушение накопления, хранения, маркировки, тары, поддонов;\n"
    "- отсутствие журналов учета отходов, накладных, актов, талонов взвешивания;\n"
    "- ртутные и люминесцентные лампы, батарейки, аккумуляторы, электронный лом;\n"
    "- нефтешлам, замазученный грунт, загрязненная ветошь, СИЗ, сорбент, фильтры, отработанные масла;\n"
    "- буровой шлам, буровой раствор, буровые сточные воды;\n"
    "- факел без учетчика, отсутствие учета сжигаемого газа, дымление, пыление, выбросы;\n"
    "- отсутствие экологического контроля, отбора проб, подтверждения устранения загрязнения, рекультивации.\n\n"
    "Формат ответа строго:\n\n"
    "ЭКОЛОГИЧЕСКАЯ ОЦЕНКА:\n"
    "[Кратко опиши выявленное экологическое замечание.]\n\n"
    "ВОЗМОЖНО НАРУШЕНЫ ТРЕБОВАНИЯ:\n"
    "1. [Экологический кодекс РК - статья номер - название статьи]\n"
    "[Краткая суть требования из предоставленного фрагмента.]\n"
    "Ссылка: [ссылка]\n\n"
    "ЧТО НЕОБХОДИМО УСТРАНИТЬ:\n"
    "- [Конкретное действие]\n"
    "- [Конкретное действие]\n"
    "- [Конкретное действие]\n\n"
    "ПРИ ПРОВЕРКЕ ГОСОРГАНАМИ:\n"
    "[Укажи подходящие статьи КоАП РК только если они есть в предоставленном контексте. Формулируй осторожно: может быть квалифицировано. Если подходящих статей КоАП нет, напиши: В предоставленных фрагментах подходящая статья КоАП не найдена.]\n"
)

PHOTO_PROMPT = (
    "Ты помощник инженера-эколога нефтегазового предприятия в Казахстане.\n"
    "Проанализируй фото только с экологической точки зрения.\n"
    "Опиши экологические признаки, если они видны: загрязнение территории, пятна нефти или масла, отходы, мусор, контейнеры, отсутствие раздельного сбора, разлив жидкости, шлам, сточные воды, пластовая вода, дым, пыль, факел.\n"
    "Не анализируй пожарную безопасность, охрану труда, каски, огнетушители, электрику, ржавчину и бытовой порядок, если нет экологического аспекта.\n"
    "Если экологическое замечание не видно, напиши: По фото явное экологическое замечание не выявлено."
)

def normalize_query(query):
    if not query:
        return ""

    text = query.lower()
    expanded = text

    replacements = {
        "мусорки": "мусорный контейнер место накопления отходов отходы коммунальные отходы раздельный сбор",
        "мусорка": "мусорный контейнер место накопления отходов отходы коммунальные отходы раздельный сбор",
        "мусор": "отходы коммунальные отходы захламление накопление отходов",
        "тбо": "коммунальные отходы отходы место накопления раздельный сбор",
        "замазучено": "замазученность загрязнение нефтепродуктами загрязнение почвы загрязнение земель",
        "замазученно": "замазученность загрязнение нефтепродуктами загрязнение почвы загрязнение земель",
        "замазучена": "замазученность загрязнение нефтепродуктами загрязнение почвы загрязнение земель",
        "замазученность": "замазученность загрязнение нефтепродуктами загрязнение почвы загрязнение земель",
        "нефть": "нефть нефтепродукты загрязнение почвы загрязнение земель разлив",
        "масло": "масло нефтепродукты загрязнение почвы загрязнение земель",
        "мазут": "мазут нефтепродукты загрязнение почвы загрязнение земель",
        "раздельного сбора нет": "отсутствие раздельного сбора отходов смешивание отходов",
        "нет раздельного сбора": "отсутствие раздельного сбора отходов смешивание отходов",
        "без маркировки": "отсутствие маркировки контейнеров отходов место накопления отходов",
        "нет журнала": "отсутствие журнала учета отходов учет отходов",
        "нет журналов": "отсутствие журналов учета отходов учет отходов",
        "нет накладных": "отсутствие накладных подтверждающих документов передача отходов",
        "нет актов": "отсутствие актов передачи отходов подтверждающих документов",
        "нет талонов": "отсутствие талонов взвешивания учет отходов",
        "ртутные лампы": "ртутьсодержащие отходы ртутные лампы люминесцентные лампы раздельное накопление отходов",
        "люминесцентные лампы": "ртутьсодержащие отходы люминесцентные лампы отдельное накопление отходов",
        "батарейки": "опасные отходы батарейки отдельное накопление отходов",
        "аккумуляторы": "опасные отходы аккумуляторы отдельное накопление отходов",
        "электронный лом": "электронный лом отходы отдельное накопление отходов",
        "ветошь": "загрязненная ветошь нефтесодержащие отходы отдельное накопление",
        "сорбент": "загрязненный сорбент нефтесодержащие отходы отдельное накопление",
        "нефтешлам": "нефтешлам нефтесодержащие отходы загрязнение",
        "замазученный грунт": "замазученный грунт нефтесодержащие отходы загрязнение почвы",
        "буровой шлам": "буровой шлам буровые отходы отходы бурения",
        "буровой раствор": "буровой раствор буровые отходы",
        "пластовая вода": "пластовая вода производственная жидкость разлив загрязнение почвы",
        "сточные воды": "сточные воды сброс перелив загрязнение",
        "перелив": "перелив сточные воды производственные жидкости загрязнение",
        "сброс": "сброс сточные воды загрязнение вод",
        "факел": "факельная установка выбросы атмосферный воздух сжигание газа",
        "учетчика": "отсутствие учетчика расходомер учет выбросов факельная установка",
        "учётчика": "отсутствие учетчика расходомер учет выбросов факельная установка",
        "расходомер": "расходомер учет выбросов факельная установка",
        "дым": "дымление выбросы атмосферный воздух",
        "пыль": "пыление атмосферный воздух выбросы",
        "рекультивация": "рекультивация восстановление загрязненного участка",
    }

    for key, value in replacements.items():
        if key in text:
            expanded += " " + value

    return expanded

def is_ecology_query(query):
    text = normalize_query(query).lower()
    if any(word in text for word in ECO_KEYWORDS):
        return True
    if any(word in text for word in NON_ECO_KEYWORDS):
        return False
    return True

def build_search_queries(query):
    text = normalize_query(query).lower()
    queries = [normalize_query(query)]

    if any(x in text for x in ["замазуч", "нефт", "масло", "мазут", "нефтепродукт", "разлив", "загряз"]):
        queries.extend([
            "загрязнение земель нефтепродуктами",
            "экологические требования при использовании земель",
            "загрязнение почвы",
            "ликвидация загрязнения",
        ])

    if any(x in text for x in ["отход", "мусор", "контейнер", "тбо", "коммунальн", "раздельн", "накоплен", "хранен"]):
        queries.extend([
            "экологические требования по управлению отходами",
            "накопление отходов",
            "раздельный сбор отходов",
            "несанкционированное размещение отходов",
        ])

    if any(x in text for x in ["журнал", "учет", "учёт", "накладн", "акт", "талон", "взвеш"]):
        queries.extend([
            "учет отходов",
            "экологическая отчетность",
            "производственный экологический контроль",
            "управление отходами",
        ])

    if any(x in text for x in ["пластов", "сточн", "сброс", "перелив", "вод"]):
        queries.extend([
            "сброс сточных вод",
            "загрязнение вод",
            "экологические требования при использовании вод",
            "производственные сточные воды",
        ])

    if any(x in text for x in ["буров", "шлам", "раствор", "скважин"]):
        queries.extend([
            "буровые отходы",
            "экологические требования при проведении операций по недропользованию",
            "отходы бурения",
            "буровой шлам",
        ])

    if any(x in text for x in ["факел", "выброс", "атмосфер", "дым", "пыл", "газ", "расходомер", "учетчик"]):
        queries.extend([
            "атмосферный воздух выбросы",
            "источники выбросов",
            "учет выбросов",
            "производственный экологический контроль выбросы",
            "факельное сжигание газа",
        ])

    if any(x in text for x in ["рекультив", "восстанов", "очистк", "ликвидац"]):
        queries.extend([
            "рекультивация земель",
            "восстановление земель",
            "ликвидация загрязнения",
        ])

    clean = []
    for q in queries:
        q = q.strip()
        if q and q not in clean:
            clean.append(q)

    return clean[:10]

def article_number(block):
    match = re.search(r"Статья\s+(\d+)", block.strip())
    if match:
        return match.group(1)
    return None

def is_bad_article(law_key, block, query):
    number = article_number(block)
    if not number:
        return False

    if number in BAD_ARTICLES.get(law_key, set()):
        return True

    if law_key == "ecocode" and number in WEAK_ECO_ARTICLES:
        text = normalize_query(query).lower()
        nedra_words = [
            "недр", "скважин", "бурен", "буров", "добыч", "месторожден",
            "операции по недропользованию", "проектные документы", "пластов",
            "углеводород"
        ]
        if not any(word in text for word in nedra_words):
            return True

    return False

def score_article(block, query, law_key):
    block_lower = block.lower()
    text = normalize_query(query).lower()
    words = set(re.findall(r"[а-яёА-ЯЁ]{4,}", text))
    score = 0

    for word in words:
        if word in block_lower:
            score += 2

    strong_terms = [
        "запрещ", "обязан", "обязаны", "не допускается", "должны",
        "требования", "загрязнение", "загрязнен", "отход", "управлению отходами",
        "накопление", "сбор", "сортировка", "раздельный", "размещен", "захоронен",
        "земель", "почв", "вод", "сброс", "атмосфер", "выброс", "рекультивац",
        "производственный экологический контроль", "учет", "отчетность", "норматив",
        "влечет штраф", "влекут штраф", "субъектов крупного предпринимательства",
    ]

    for term in strong_terms:
        if term in block_lower:
            score += 3

    if law_key == "koap":
        if "влечет штраф" in block_lower or "влекут штраф" in block_lower:
            score += 12
        if "субъектов крупного предпринимательства" in block_lower:
            score += 5
        if any(x in block_lower for x in ["управлению отходами", "охране окружающей среды", "загрязнение", "выброс", "сброс"]):
            score += 8

    if law_key == "ecocode":
        if "цель" in block_lower and "задач" in block_lower:
            score -= 25
        if "принцип" in block_lower:
            score -= 15

    if any(x in text for x in ["замазуч", "нефт", "масло", "мазут", "загряз", "почв", "земл"]):
        for term in ["загрязнение земель", "почв", "земель", "рекультивац", "использовании земель"]:
            if term in block_lower:
                score += 8

    if any(x in text for x in ["отход", "мусор", "контейнер", "раздельн", "накоплен", "хранен", "ртут", "ламп"]):
        for term in ["отход", "накопление", "сбор", "сортировка", "раздельный", "размещен", "управлению отходами"]:
            if term in block_lower:
                score += 8

    if any(x in text for x in ["журнал", "учет", "учёт", "наклад", "талон", "акт"]):
        for term in ["учет", "отчетность", "производственный экологический контроль", "управлению отходами"]:
            if term in block_lower:
                score += 8

    if any(x in text for x in ["факел", "выброс", "атмосфер", "дым", "пыл", "газ"]):
        for term in ["атмосферный воздух", "выброс", "источников выбросов", "производственный экологический контроль"]:
            if term in block_lower:
                score += 8

    if any(x in text for x in ["вод", "сброс", "сточн", "пластов", "перелив"]):
        for term in ["вод", "сброс", "загрязнение вод", "сточные воды"]:
            if term in block_lower:
                score += 8

    return score

def fetch_law_text(law_key, query):
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

            if is_bad_article(law_key, block, query):
                continue

            score = score_article(block, query, law_key)
            if score <= 0:
                continue

            number = article_number(block)
            article_link = url
            if number:
                article_link = url + "#z" + number

            scored.append((score, block[:1800] + "\nСсылка: " + article_link))

        scored.sort(key=lambda item: item[0], reverse=True)
        selected = [text for _, text in scored[:6]]
        return "\n\n".join(selected)

    except Exception as error:
        print("Ошибка загрузки " + law_key + ": " + str(error))
        return ""

def search_adilet_context(query, law_key):
    context = ""
    doc_id = LAW_URLS[law_key].split("/")[-1]

    for q in build_search_queries(query)[:4]:
        try:
            search_url = (
                "https://adilet.zan.kz/rus/search/content?q="
                + urllib.parse.quote(q)
                + "&doc="
                + doc_id
            )

            response = requests.get(search_url, headers=HEADERS, timeout=20, verify=False)
            soup = BeautifulSoup(response.text, "html.parser")
            items = soup.select("div.search-result-item")[:3]

            for item in items:
                link = item.select_one("a")
                snippet = item.select_one("div.snippet, p")

                if not link:
                    continue

                href = link.get("href", "")
                if href.startswith("http"):
                    item_url = href
                else:
                    item_url = "https://adilet.zan.kz" + href

                context += (
                    "\nРезультат поиска: "
                    + link.get_text(strip=True)
                    + "\n"
                    + (snippet.get_text(strip=True)[:600] if snippet else "")
                    + "\nСсылка: "
                    + item_url
                    + "\n"
                )

        except Exception as error:
            print("Ошибка поиска на adilet: " + str(error))

    return context[:3500]

def build_context(query):
    if not is_ecology_query(query):
        return ""

    context = ""

    for law_key in ["ecocode", "koap"]:
        title = LAW_TITLES[law_key]
        article_text = fetch_law_text(law_key, query)
        search_text = search_adilet_context(query, law_key)

        if article_text or search_text:
            context += "\n=== " + title + " ===\n"
            if article_text:
                context += article_text + "\n"
            if search_text:
                context += "\nДополнительные результаты поиска по Adilet:\n" + search_text + "\n"

    return context[:18000]

def clean_answer(text):
    if not text:
        return "Пустой ответ."

    text = text.replace("**", "")
    text = text.replace("###", "")
    text = text.replace("##", "")
    text = text.replace("#", "")
    text = text.replace("\u00A0", " ")
    return text.strip()

def send_long_message(chat_id, text):
    text = clean_answer(text)
    for part in util.smart_split(text, chars_per_string=3000):
        bot.send_message(chat_id, part)

@bot.message_handler(commands=["start", "help"])
def send_welcome(message):
    bot.send_message(
        message.chat.id,
        "Эко Помощник ПККР 1.0\n\n"
        "Пришли фото или опиши экологическое замечание.\n\n"
        "Бот анализирует только экологические вопросы по Экологическому кодексу РК и КоАП РК.\n\n"
        "Примеры:\n"
        "- замазучено вокруг мусорки\n"
        "- нет раздельного сбора отходов\n"
        "- ртутные лампы лежат вместе с мусором\n"
        "- нет журналов учета отходов\n"
        "- пластовая вода попала на грунт\n"
        "- на факеле нет учетчика\n"
        "- замазученный грунт не вывезен"
    )

@bot.message_handler(content_types=["photo"])
def handle_photo(message):
    wait_msg = bot.send_message(message.chat.id, "Анализирую фото по экологическому блоку...")

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

        photo_description = clean_answer(photo_response.text)

        if "явное экологическое замечание не выявлено" in photo_description.lower() and not caption:
            bot.delete_message(message.chat.id, wait_msg.message_id)
            bot.send_message(message.chat.id, photo_description)
            return

        query = photo_description + " " + caption
        context = build_context(query)

        if not context:
            bot.delete_message(message.chat.id, wait_msg.message_id)
            bot.send_message(
                message.chat.id,
                "По фото экологическое замечание не определено либо вопрос относится не к экологическому блоку текущей версии."
            )
            return

        full_query = (
            SYSTEM_PROMPT
            + "\n\n=== ФРАГМЕНТЫ ИЗ АКТУАЛЬНЫХ ИСТОЧНИКОВ ===\n"
            + context
            + "\n\n=== ОПИСАНИЕ ФОТО ===\n"
            + photo_description
            + "\n\n=== ПОДПИСЬ ПОЛЬЗОВАТЕЛЯ ===\n"
            + caption
        )

        response = model.generate_content(full_query)
        answer = clean_answer(response.text)

        bot.delete_message(message.chat.id, wait_msg.message_id)
        bot.send_message(message.chat.id, "На фото: " + photo_description)
        send_long_message(message.chat.id, answer)

    except Exception as error:
        try:
            bot.edit_message_text("Ошибка: " + str(error), message.chat.id, wait_msg.message_id)
        except Exception:
            bot.send_message(message.chat.id, "Ошибка: " + str(error))

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    user_text = message.text or ""
    wait_msg = bot.send_message(message.chat.id, "Ищу экологические нормы в актуальных источниках...")

    try:
        if not is_ecology_query(user_text):
            bot.edit_message_text(
                "В текущей версии анализируются только экологические замечания по Экологическому кодексу РК и КоАП РК.",
                message.chat.id,
                wait_msg.message_id
            )
            return

        context = build_context(user_text)

        if not context:
            bot.edit_message_text(
                "Не удалось получить подходящие экологические нормы с adilet.zan.kz. Попробуйте описать экологическое замечание подробнее.",
                message.chat.id,
                wait_msg.message_id
            )
            return

        model = genai.GenerativeModel(SELECTED_MODEL)

        full_query = (
            SYSTEM_PROMPT
            + "\n\n=== ФРАГМЕНТЫ ИЗ АКТУАЛЬНЫХ ИСТОЧНИКОВ ===\n"
            + context
            + "\n\n=== ЗАПРОС ПОЛЬЗОВАТЕЛЯ ===\n"
            + user_text
        )

        response = model.generate_content(full_query)
        answer = clean_answer(response.text)

        bot.delete_message(message.chat.id, wait_msg.message_id)
        send_long_message(message.chat.id, answer)

    except Exception as error:
        try:
            bot.edit_message_text("Ошибка: " + str(error), message.chat.id, wait_msg.message_id)
        except Exception:
            bot.send_message(message.chat.id, "Ошибка: " + str(error))

print("БОТ ЗАПУЩЕН - Эко Помощник ПККР 1.0 - только Экологический кодекс и КоАП")

bot.polling(none_stop=True, interval=1)
