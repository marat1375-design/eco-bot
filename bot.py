import telebot
from telebot import util
import google.generativeai as genai
import requests
import base64
import os
import re

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')

genai.configure(api_key=GOOGLE_API_KEY)
SELECTED_MODEL = 'models/gemini-2.5-flash'

bot = telebot.TeleBot(TELEGRAM_TOKEN)

LAW_FILES = {
    'atom': ('atom.txt', 'Закон РК об использовании атомной энергии N 442-V от 12.01.2016'),
    'ecocode': ('ecocode.txt', 'Экологический кодекс РК от 02.01.2021 N 400-VI'),
    'nedra': ('nedra.txt', 'Кодекс РК о недрах и недропользовании'),
    'sanpin1': ('sanpin1.txt', 'Санитарные правила по радиационной безопасности Приказ N КР ДСМ-275/2020'),
    'sanpin2': ('sanpin2.txt', 'Санитарные правила и нормы РК'),
    'koap': ('koap_final.txt', 'КоАП РК - Кодекс об административных правонарушениях N 235-V'),
}

# Ключевые слова для определения файлов поиска
FILE_KEYWORDS = {
    'ecocode': [
        'нефт', 'разлив', 'розлив', 'загрязнен', 'отход', 'мусор', 'свалк',
        'замазучен', 'шлам', 'земл', 'почв', 'вод', 'сточн', 'выброс',
        'атмосфер', 'воздух', 'рекультив', 'ущерб', 'экологич', 'контейнер',
        'тбо', 'захоронен', 'размещен', 'утилизац', 'раздельн', 'сортировк',
        'урна', 'пластов', 'скважин', 'факел', 'эмисс', 'сброс',
    ],
    'koap': [
        'штраф', 'ответственност', 'нарушени', 'санкци', 'загрязнен',
        'отход', 'земл', 'атмосфер', 'вод', 'недр', 'радиац',
        'нефт', 'выброс', 'сброс', 'свалк', 'мусор',
    ],
    'atom': [
        'радиац', 'излучен', 'ядерн', 'атомн', 'изотоп', 'дозиметр',
        'рао', 'нуклид', 'фон', 'доза', 'беккерел', 'зиверт',
    ],
    'sanpin1': [
        'радиац', 'излучен', 'доза', 'фон', 'дозиметр', 'ионизир',
        'радиационн', 'нуклид', 'зиверт', 'беккерел',
    ],
    'sanpin2': [
        'санитарн', 'тбо', 'мусор', 'контейнер', 'свалк', 'отход',
        'гигиен', 'норматив', 'сбор', 'вывоз',
    ],
    'nedra': [
        'недр', 'скважин', 'месторожден', 'добыч', 'пластов', 'углеводород',
        'нефт', 'газ', 'недропользован',
    ],
}

def load_laws():
    laws = {}
    for key, (filename, title) in LAW_FILES.items():
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                laws[key] = {'text': f.read(), 'title': title}
            print("Загружен: " + filename)
        except Exception as e:
            laws[key] = {'text': '', 'title': title}
            print("Не найден: " + filename + " - " + str(e))
    return laws

def get_article_block(text, article_name):
    lines = text.split('\n')
    for i, line in enumerate(lines):
        clean_line = line.strip().replace('**', '').replace('*', '')
        if article_name in clean_line:
            block_lines = lines[i:i+40]
            return '\n'.join(block_lines)[:2000]
    return None

def search_relevant_chunks(laws, query, max_chars=12000):
    query_lower = query.lower()
    words = set(w for w in re.findall(r'[а-яёА-ЯЁ]{4,}', query_lower))

    # Определяем файлы для поиска по ключевым словам
    files_to_search = set()
    for file_key, keywords in FILE_KEYWORDS.items():
        for kw in keywords:
            if any(kw in w or w in kw for w in words):
                files_to_search.add(file_key)
                break

    # КоАП всегда включаем для штрафов
    files_to_search.add('koap')

    # Если ничего не нашли — ищем в Экокодексе
    if len(files_to_search) <= 1:
        files_to_search.add('ecocode')

    print("Файлы для поиска: " + str(files_to_search))

    # Ищем релевантные блоки во всех выбранных файлах
    results = []
    for key in files_to_search:
        if key not in laws or not laws[key]['text']:
            continue
        text = laws[key]['text']
        title = laws[key]['title']

        blocks = re.split(r'(?=Статья\s+\d+)', text)
        for block in blocks:
            if len(block.strip()) < 100:
                continue
            block_lower = block.lower()

            # Пропускаем блоки с только определениями
            if 'термин' in block_lower and len(block) < 300:
                continue

            # Считаем релевантность
            score = 0
            for w in words:
                if w in block_lower:
                    score += 2

            # Бонус за штрафные нормы
            if 'влечет штраф' in block_lower or 'влекут штраф' in block_lower:
                score += 4

            # Бонус за нормы про ущерб и загрязнение
            if any(x in block_lower for x in ['ущерб', 'загрязнен', 'рекультив', 'ликвидац', 'запрещает', 'обязан']):
                score += 2

            # Бонус за статьи про отходы
            if any(x in block_lower for x in ['управлени отходами', 'сбор отходов', 'обращени с отходами']):
                score += 3

            if score > 0:
                results.append((score, key, title, block[:2000]))

    # Сортируем по релевантности
    results.sort(key=lambda x: x[0], reverse=True)

    # Берём топ блоки — не более 2 из каждого файла чтобы было разнообразие
    context = ""
    total = 0
    file_counts = {}
    seen = set()

    for score, file_key, title, block in results:
        key = block[:100]
        if key in seen:
            continue

        # Не более 2 блоков из одного файла (кроме КоАП — 1 блок)
        limit = 1 if file_key == 'koap' else 2
        if file_counts.get(file_key, 0) >= limit:
            continue

        chunk = "\n=== " + title + " ===\n" + block + "\n"
        if total + len(chunk) > max_chars:
            break

        seen.add(key)
        context += chunk
        total += len(chunk)
        file_counts[file_key] = file_counts.get(file_key, 0) + 1

    print("Итого символов: " + str(total) + " из файлов: " + str(file_counts))
    return context

LAWS = load_laws()

SYSTEM_PROMPT = (
    "Ты - нормативный ассистент инженера ООС АО ПетропКазахстан Кумколь Ресорсиз, Казахстан.\n"
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
    "   [суть требования 1-2 строки своими словами]\n\n"
    "2. [следующая статья если есть]\n\n"
    "ЧТО НЕОБХОДИМО УСТРАНИТЬ:\n"
    "- [конкретное действие 1]\n"
    "- [конкретное действие 2]\n"
    "- [конкретное действие 3]\n\n"
    "ПРИ ПРОВЕРКЕ ГОСОРГАНАМИ:\n"
    "[КоАП РК Ст.XXX - размер штрафа для юридических лиц в МРП и тенге]\n\n"
    "Если статей нет - напиши: В базе данных подходящих статей не найдено."
)

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
        "- Отправь фото нарушения")

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    wait_msg = bot.send_message(message.chat.id, "Ищу в базе законов...")
    try:
        context = search_relevant_chunks(LAWS, message.text)
        if not context:
            bot.edit_message_text(
                "В базе данных подходящих статей не найдено. Уточните запрос.",
                message.chat.id, wait_msg.message_id)
            return

        model = genai.GenerativeModel(SELECTED_MODEL)
        full_query = (
            SYSTEM_PROMPT + "\n\n"
            "=== ФРАГМЕНТЫ ИЗ БАЗЫ ЗАКОНОВ ===\n" +
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

        context = search_relevant_chunks(LAWS, violation_desc + " " + caption)

        full_query = (
            SYSTEM_PROMPT + "\n\n"
            "=== ФРАГМЕНТЫ ИЗ БАЗЫ ЗАКОНОВ ===\n" +
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

print("БОТ ЗАПУЩЕН - Gemini + RAG v10")
bot.polling(none_stop=True, interval=1)
