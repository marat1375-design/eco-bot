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

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')

genai.configure(api_key=GOOGLE_API_KEY)
SELECTED_MODEL = 'models/gemini-2.5-flash'

bot = telebot.TeleBot(TELEGRAM_TOKEN)

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
}

# Прямые ссылки на нужные законы РК
LAW_URLS = {
    'ecocode': 'https://adilet.zan.kz/rus/docs/K2100000400',
    'koap': 'https://adilet.zan.kz/rus/docs/K1400000235',
    'atom': 'https://adilet.zan.kz/rus/docs/Z1600000442',
    'nedra': 'https://adilet.zan.kz/rus/docs/K1700000125',
    'trud': 'https://adilet.zan.kz/rus/docs/K150000251_',
    'pozhar': 'https://adilet.zan.kz/rus/docs/Z2100000120',
}

# Определяем какие законы искать по ключевым словам
FILE_KEYWORDS = {
    'ecocode': [
        'нефт', 'разлив', 'розлив', 'загрязнен', 'отход', 'мусор', 'свалк',
        'замазучен', 'шлам', 'земл', 'почв', 'вод', 'сточн', 'выброс',
        'атмосфер', 'воздух', 'рекультив', 'ущерб', 'экологич', 'контейнер',
        'тбо', 'захоронен', 'размещен', 'утилизац', 'раздельн', 'сортировк',
        'урна', 'пластов', 'скважин', 'факел', 'эмисс', 'сброс',
    ],
    'koap': [
        'штраф', 'ответственност', 'нарушени', 'загрязнен', 'отход',
        'земл', 'атмосфер', 'вод', 'недр', 'радиац', 'нефт',
    ],
    'atom': [
        'радиац', 'излучен', 'ядерн', 'атомн', 'изотоп', 'дозиметр',
        'рао', 'нуклид', 'фон', 'доза', 'зиверт',
    ],
    'nedra': [
        'недр', 'скважин', 'месторожден', 'добыч', 'пластов', 'углеводород',
        'нефт', 'газ', 'недропользован',
    ],
    'trud': [
        'работник', 'труд', 'охран труда', 'несчастн', 'травм', 'рабочее',
        'спецодежд', 'сиз', 'инструктаж',
    ],
    'pozhar': [
        'пожар', 'огнетушит', 'эвакуац', 'возгоран', 'горюч', 'огонь',
        'пожароопасн',
    ],
}

def get_relevant_laws(query):
    query_lower = query.lower()
    words = set(w for w in re.findall(r'[а-яёА-ЯЁ]{4,}', query_lower))

    laws_to_check = set()
    for law_key, keywords in FILE_KEYWORDS.items():
        for kw in keywords:
            if any(kw in w or w in kw for w in words):
                laws_to_check.add(law_key)
                break

    laws_to_check.add('koap')
    if not laws_to_check - {'koap'}:
        laws_to_check.add('ecocode')

    return laws_to_check

def search_on_adilet(query, law_key=None):
    try:
        if law_key and law_key in LAW_URLS:
            # Ищем конкретную статью в конкретном законе
            search_url = f"https://adilet.zan.kz/rus/search/content?q={urllib.parse.quote(query)}&doc={LAW_URLS[law_key].split('/')[-1]}"
        else:
            search_url = f"https://adilet.zan.kz/rus/search/content?q={urllib.parse.quote(query)}"

        response = requests.get(search_url, headers=HEADERS, timeout=15, verify=False)
        soup = BeautifulSoup(response.text, 'html.parser')

        results = []
        items = soup.select('div.search-result-item')[:3]
        for item in items:
            link = item.select_one('a')
            snippet = item.select_one('div.snippet, p')
            if link:
                results.append({
                    'title': link.get_text(strip=True),
                    'url': 'https://adilet.zan.kz' + link.get('href', ''),
                    'snippet': snippet.get_text(strip=True)[:500] if snippet else ''
                })
        return results
    except Exception as e:
        print("Ошибка поиска на adilet: " + str(e))
        return []

def fetch_article_text(law_key, query):
    if law_key not in LAW_URLS:
        return ""
    try:
        url = LAW_URLS[law_key]
        response = requests.get(url, headers=HEADERS, timeout=20, verify=False)
        soup = BeautifulSoup(response.text, 'html.parser')

        content = soup.select_one('div.document-text, div.law-text, article')
        if not content:
            return ""

        full_text = content.get_text(separator='\n', strip=True)

        # Ищем релевантные статьи по ключевым словам
        query_lower = query.lower()
        words = set(w for w in re.findall(r'[а-яёА-ЯЁ]{4,}', query_lower))

        blocks = re.split(r'(?=Статья\s+\d+)', full_text)
        scored = []
        for block in blocks:
            if len(block.strip()) < 50:
                continue
            block_lower = block.lower()
            score = sum(2 for w in words if w in block_lower)
            if 'влечет штраф' in block_lower or 'влекут штраф' in block_lower:
                score += 4
            if any(x in block_lower for x in ['ущерб', 'загрязнен', 'запрещ', 'обязан']):
                score += 2
            if score > 0:
                scored.append((score, block[:1500]))

        scored.sort(key=lambda x: x[0], reverse=True)
        return '\n\n'.join(b for _, b in scored[:3])

    except Exception as e:
        print("Ошибка загрузки " + law_key + ": " + str(e))
        return ""

LAW_TITLES = {
    'ecocode': 'Экологический кодекс РК от 02.01.2021 N 400-VI',
    'koap': 'КоАП РК N 235-V от 05.07.2014',
    'atom': 'Закон РК об использовании атомной энергии N 442-V',
    'nedra': 'Кодекс РК о недрах и недропользовании N 125-VI',
    'trud': 'Трудовой кодекс РК N 251-V',
    'pozhar': 'Закон РК о гражданской защите N 120-VII',
}

SYSTEM_PROMPT = (
    "Ты - нормативный ассистент инженера ООС АО ПетроКазахстан Кумколь Ресорсиз, Казахстан.\n"
    "Я пишу предписания своим цехам и подрядчикам - не государственный инспектор.\n\n"
    "ЗАДАЧА: по описанию или фото нарушения найти применимые статьи законов РК.\n\n"
    "ПРАВИЛА:\n"
    "- Используй ТОЛЬКО статьи из предоставленных фрагментов законов\n"
    "- Опечатки и ошибки - понимай по контексту\n"
    "- Никогда не используй законы РФ\n"
    "- Максимум 3 статьи\n"
    "- Приведи точную цитату или суть статьи\n\n"
    "ФОРМАТ ОТВЕТА:\n\n"
    "НАРУШЕНИЕ: [что обнаружено - одно предложение]\n\n"
    "НАРУШЕНЫ ТРЕБОВАНИЯ:\n"
    "1. [Закон - Ст.XX - название статьи]\n"
    "   [суть требования 1-2 строки своими словами]\n"
    "   Ссылка: https://adilet.zan.kz/...\n\n"
    "2. [следующая статья если есть]\n\n"
    "ЧТО НЕОБХОДИМО УСТРАНИТЬ:\n"
    "- [конкретное действие 1]\n"
    "- [конкретное действие 2]\n"
    "- [конкретное действие 3]\n\n"
    "ПРИ ПРОВЕРКЕ ГОСОРГАНАМИ:\n"
    "[КоАП РК Ст.XXX - размер штрафа для юридических лиц в МРП и тенге]\n\n"
    "Если статей нет - напиши: В базе данных подходящих статей не найдено."
)

def build_context(query):
    laws_to_check = get_relevant_laws(query)
    context = ""

    for law_key in laws_to_check:
        title = LAW_TITLES.get(law_key, law_key)
        text = fetch_article_text(law_key, query)
        if text:
            context += "\n=== " + title + " ===\n" + text + "\n"

    return context

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.send_message(message.chat.id,
        "Нормативный ассистент ПККР\n\n"
        "Опиши нарушение или отправь фото\n\n"
        "Примеры:\n"
        "- Разлив нефти на скважине\n"
        "- Замазученность вокруг контейнеров\n"
        "- Несанкционированная свалка ТБО\n"
        "- Превышение радиационного фона\n"
        "- Нарушение охраны труда\n"
        "- Пожарная безопасность\n"
        "- Отправь фото нарушения")

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    wait_msg = bot.send_message(message.chat.id, "Ищу в актуальных законах РК...")
    try:
        context = build_context(message.text)
        if not context:
            bot.edit_message_text(
                "Не удалось получить данные с adilet.zan.kz. Попробуйте позже.",
                message.chat.id, wait_msg.message_id)
            return

        model = genai.GenerativeModel(SELECTED_MODEL)
        full_query = (
            SYSTEM_PROMPT + "\n\n"
            "=== ФРАГМЕНТЫ ИЗ АКТУАЛЬНЫХ ЗАКОНОВ РК (adilet.zan.kz) ===\n" +
            context +
            "\n=== НАРУШЕНИЕ ===\n" +
            message.text
        )
        response = model.generate_content(full_query)
        answer = response.text.strip()

        bot.delete_message(message.chat.id, wait_msg.message_id)
        for part in util.smart_split(answer, chars_per_string=3000):
            bot.send_message(message.chat.id, part)
    except Exception as e:
        bot.edit_message_text("Ошибка: " + str(e), message.chat.id, wait_msg.message_id)

@bot.message_handler(content_types=['photo'])
def handle_photo(message):
    wait_msg = bot.send_message(message.chat.id, "Анализирую фото...")
    try:
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        file_url = "https://api.telegram.org/file/bot" + TELEGRAM_TOKEN + "/" + file_info.file_path
        photo_bytes = requests.get(file_url).content
        photo_b64 = base64.b64encode(photo_bytes).decode('utf-8')
        caption = message.caption or ""

        model = genai.GenerativeModel(SELECTED_MODEL)

        photo_response = model.generate_content([
            "Ты помощник инженера ООС нефтегазового предприятия в Казахстане.\n"
            "Посмотри на фото и опиши кратко (1-2 предложения) какое экологическое нарушение видно.\n"
            "Если есть подпись пользователя - учти её: " + caption,
            {"mime_type": "image/jpeg", "data": photo_b64}
        ])
        violation_desc = photo_response.text.strip()

        context = build_context(violation_desc + " " + caption)

        full_query = (
            SYSTEM_PROMPT + "\n\n"
            "=== ФРАГМЕНТЫ ИЗ АКТУАЛЬНЫХ ЗАКОНОВ РК (adilet.zan.kz) ===\n" +
            context +
            "\n=== НАРУШЕНИЕ НА ФОТО ===\n" +
            violation_desc
        )
        response = model.generate_content(full_query)
        answer = response.text.strip()

        bot.delete_message(message.chat.id, wait_msg.message_id)
        bot.send_message(message.chat.id, "На фото: " + violation_desc)
        for part in util.smart_split(answer, chars_per_string=3000):
            bot.send_message(message.chat.id, part)
    except Exception as e:
        bot.edit_message_text("Ошибка: " + str(e), message.chat.id, wait_msg.message_id)

print("БОТ ЗАПУЩЕН - adilet.zan.kz + Gemini")
bot.polling(none_stop=True, interval=1)
