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

def search_relevant_chunks(laws, query, max_chars=12000):
    query_lower = query.lower()
    words = set(w for w in re.findall(r'[а-яёА-ЯЁ]{4,}', query_lower))

    TOPICS = {
        'радиац': ['atom', 'sanpin1', 'sanpin2'],
        'излучени': ['atom', 'sanpin1', 'sanpin2'],
        'атомн': ['atom'],
        'ядерн': ['atom'],
        'нефт': ['ecocode', 'nedra'],
        'скважин': ['ecocode'],
        'разлив': ['ecocode'],
        'розлив': ['ecocode'],
        'сточн': ['ecocode'],
        'отход': ['ecocode', 'sanpin2'],
        'шлам': ['ecocode'],
        'замазучен': ['ecocode'],
        'загрязнен': ['ecocode'],
        'земл': ['ecocode'],
        'почв': ['ecocode'],
        'атмосфер': ['ecocode'],
        'выброс': ['ecocode'],
        'тбо': ['sanpin2', 'ecocode'],
        'мусор': ['sanpin2', 'ecocode'],
        'контейнер': ['sanpin2'],
        'свалк': ['ecocode', 'sanpin2'],
        'недр': ['nedra'],
    }

    files_to_search = set()
    for word in words:
        for topic, files in TOPICS.items():
            if topic in word or word in topic:
                files_to_search.update(files)

    if not files_to_search:
        files_to_search = {'ecocode'}

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
            score = sum(2 if w in block_lower else 0 for w in words)
            if score > 0:
                results.append((score, title, block[:2000]))

    results.sort(key=lambda x: x[0], reverse=True)

    context = ""
    total = 0
    seen = set()
    for score, title, block in results:
        key = block[:100]
        if key in seen:
            continue
        seen.add(key)
        chunk = "\n=== " + title + " ===\n" + block + "\n"
        if total + len(chunk) > max_chars:
            break
        context += chunk
        total += len(chunk)

    print("Найдено символов для запроса: " + str(total))
    return context

LAWS = load_laws()

SYSTEM_PROMPT = (
    "Ты - нормативный ассистент инженера охраны окружающей среды "
    "АО ПетроКазахстан Кумколь Ресорсиз, Казахстан. "
    "Месторождения КАМ - Кызылкия, Арыскум, Майбулак.\n\n"
    "ТВОЯ ЗАДАЧА: найти в предоставленных фрагментах законов РК точные статьи применимые к нарушению.\n\n"
    "ПРАВИЛА:\n"
    "- Используй ТОЛЬКО статьи из предоставленных фрагментов законов\n"
    "- Опечатки и ошибки в запросе - понимай по контексту\n"
    "- Цитируй статьи точно как написано в тексте\n"
    "- Никогда не используй законы РФ\n"
    "- Максимум 3 нормы\n"
    "- Ссылки на adilet.zan.kz\n\n"
    "ФОРМАТ ОТВЕТА:\n\n"
    "НАРУШЕНИЕ: [одно предложение]\n\n"
    "НОРМЫ:\n"
    "1. [Название закона - Ст.XX - название статьи]\n"
    "   [Точная цитата из предоставленного текста]\n"
    "   https://adilet.zan.kz/...\n\n"
    "ШТРАФ: [если есть в тексте]\n\n"
    "Если подходящих статей нет в предоставленных фрагментах - напиши: "
    "В базе данных подходящих статей не найдено."
)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.send_message(message.chat.id,
        "Нормативный ассистент ПККР\n\n"
        "Опиши нарушение или отправь фото\n"
        "Пример: Разлив нефти на скважине")

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
            "\n=== НАРУШЕНИЕ ОТ ПОЛЬЗОВАТЕЛЯ ===\n" +
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
    wait_msg = bot.send_message(message.chat.id, "Анализирую фото и ищу нормы...")
    try:
        file_id = message.photo[-1].file_id
        file_info = bot.get_file(file_id)
        file_url = "https://api.telegram.org/file/bot" + TELEGRAM_TOKEN + "/" + file_info.file_path
        photo_bytes = requests.get(file_url).content
        photo_b64 = base64.b64encode(photo_bytes).decode('utf-8')
        caption = message.caption or "Определи нарушения на фото"

        model = genai.GenerativeModel(SELECTED_MODEL)

        photo_response = model.generate_content([
            "Опиши кратко (1-2 предложения) что нарушено на этом фото "
            "с точки зрения экологии на нефтегазовом объекте в Казахстане. "
            "Только описание нарушения, без лишних слов.",
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
        for part in util.smart_split(answer, chars_per_string=3000):
            bot.send_message(message.chat.id, part)
    except Exception as e:
        bot.edit_message_text("Ошибка: " + str(e), message.chat.id, wait_msg.message_id)

print("БОТ ЗАПУЩЕН - Gemini + RAG")
bot.polling(none_stop=True, interval=1)
