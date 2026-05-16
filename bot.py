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

DIRECT_ARTICLES = {
    'разлив_нефть': {
        'ecocode': ['Статья 135', 'Статья 136', 'Статья 137', 'Статья 145'],
        'koap': ['Статья 328', 'Статья 337', 'Статья 356'],
    },
    'разлив_вода': {
        'ecocode': ['Статья 135', 'Статья 136', 'Статья 137'],
        'koap': ['Статья 328', 'Статья 336'],
    },
    'отход': {
        'ecocode': ['Статья 321', 'Статья 322', 'Статья 339'],
        'koap': ['Статья 338'],
    },
    'свалка': {
        'ecocode': ['Статья 321', 'Статья 339', 'Статья 351'],
        'koap': ['Статья 338'],
    },
    'замазучен': {
        'ecocode': ['Статья 135', 'Статья 136', 'Статья 321'],
        'koap': ['Статья 337', 'Статья 338'],
    },
    'атмосфер': {
        'ecocode': ['Статья 188', 'Статья 189'],
        'koap': ['Статья 315', 'Статья 316'],
    },
    'радиац': {
        'atom': ['Статья 17', 'Статья 24'],
        'sanpin1': ['5', '10', '18'],
        'koap': ['Статья 297'],
    },
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

    violation_type = None
    if any(w in query_lower for w in ['нефт', 'углеводород']):
        if any(w in query_lower for w in ['разлив', 'розлив', 'утечк', 'авари']):
            violation_type = 'разлив_нефть'
        else:
            violation_type = 'отход'
    elif any(w in query_lower for w in ['пластов']):
        if any(w in query_lower for w in ['разлив', 'розлив', 'утечк', 'сброс']):
            violation_type = 'разлив_вода'
        else:
            violation_type = 'разлив_нефть'
    elif any(w in query_lower for w in ['сточн', 'вод']) and any(w in query_lower for w in ['разлив', 'розлив', 'сброс']):
        violation_type = 'разлив_вода'
    elif any(w in query_lower for w in ['замазучен', 'замазал', 'шлам', 'нефтяное']):
        violation_type = 'замазучен'
    elif any(w in query_lower for w in ['мусор', 'тбо', 'свалк', 'контейнер']):
        violation_type = 'свалка'
    elif any(w in query_lower for w in ['отход', 'размещен', 'захоронен']):
        violation_type = 'отход'
    elif any(w in query_lower for w in ['выброс', 'атмосфер', 'воздух', 'факел']):
        violation_type = 'атмосфер'
    elif any(w in query_lower for w in ['радиац', 'излучен', 'ядерн', 'атомн']):
        violation_type = 'радиац'

    context = ""
    total = 0

    if violation_type and violation_type in DIRECT_ARTICLES:
        articles_map = DIRECT_ARTICLES[violation_type]
        for law_key, article_list in articles_map.items():
            if law_key not in laws or not laws[law_key]['text']:
                continue
            title = laws[law_key]['title']
            for article in article_list:
                block = get_article_block(laws[law_key]['text'], article)
                if block:
                    chunk = "\n=== " + title + " ===\n" + block + "\n"
                    if total + len(chunk) <= max_chars:
                        context += chunk
                        total += len(chunk)
        print("Прямой поиск: " + str(violation_type) + " | символов: " + str(total))

    if total < 1000:
        words = set(w for w in re.findall(r'[а-яёА-ЯЁ]{4,}', query_lower))
        TOPICS = {
            'радиац': ['atom', 'sanpin1', 'sanpin2'],
            'нефт': ['ecocode', 'nedra', 'koap'],
            'разлив': ['ecocode', 'koap'],
            'розлив': ['ecocode', 'koap'],
            'пластов': ['ecocode', 'nedra'],
            'сточн': ['ecocode', 'koap'],
            'отход': ['ecocode', 'koap'],
            'шлам': ['ecocode', 'nedra'],
            'замазучен': ['ecocode', 'koap'],
            'загрязнен': ['ecocode', 'koap'],
            'мусор': ['sanpin2', 'ecocode', 'koap'],
            'свалк': ['ecocode', 'koap'],
            'выброс': ['ecocode', 'koap'],
            'недр': ['nedra', 'koap'],
            'штраф': ['koap'],
        }

        files_to_search = set()
        for word in words:
            for topic, files in TOPICS.items():
                if topic in word or word in topic:
                    files_to_search.update(files)

        if not files_to_search:
            files_to_search = {'ecocode', 'koap'}

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
                if 'термин' in block_lower and len(block) < 500:
                    continue
                score = sum(2 if w in block_lower else 0 for w in words)
                if 'влечет штраф' in block_lower or 'влекут штраф' in block_lower:
                    score += 3
                if any(x in block_lower for x in ['ущерб', 'загрязнен', 'рекультив', 'ликвидац']):
                    score += 2
                if score > 0:
                    results.append((score, title, block[:2000]))

        results.sort(key=lambda x: x[0], reverse=True)
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

    print("Итого символов: " + str(total))
    return context

LAWS = load_laws()

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

print("БОТ ЗАПУЩЕН - Gemini + RAG v7")
bot.polling(none_stop=True, interval=1)
