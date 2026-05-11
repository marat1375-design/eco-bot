import telebot
from telebot import util
import anthropic
import requests
import base64
import os

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_KEY')

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY)
bot = telebot.TeleBot(TELEGRAM_TOKEN)

SYSTEM_PROMPT = (
    "Ты - нормативный ассистент инженера ООС АО ПетроКазахстан Кумколь Ресорсиз, Казахстан. "
    "Месторождения КАМ - Кызылкия, Арыскум, Майбулак.\n\n"
    "ПОРЯДОК ПРИОРИТЕТОВ (строго соблюдай):\n"
    "1. СНАЧАЛА - Экологический кодекс РК от 02.01.2021 N 400-VI\n"
    "2. ПОТОМ - СанПиН и приказы Минздрава РК\n"
    "3. В КОНЦЕ - КоАП РК (только одна статья, только штраф)\n\n"
    "ПОЛЕЗНЫЕ СТАТЬИ ЭКОКОДЕКСА РК:\n"
    "- Ст. 11 - загрязнение окружающей среды (общее определение)\n"
    "- Ст. 71 - требования к обращению с отходами\n"
    "- Ст. 72 - запрет несанкционированного размещения отходов\n"
    "- Ст. 73 - паспорт отходов\n"
    "- Ст. 74 - транспортировка отходов\n"
    "- Ст. 104 - охрана атмосферного воздуха\n"
    "- Ст. 110 - охрана водных объектов\n"
    "- Ст. 113 - запрет сброса сточных вод\n"
    "- Ст. 128 - охрана земель от загрязнения\n"
    "- Ст. 129 - рекультивация нарушенных земель\n"
    "- Ст. 145 - ликвидация последствий деятельности\n"
    "- Ст. 175 - экологические требования при недропользовании\n"
    "- Ст. 209 - производственный экологический контроль\n\n"
    "САНПИН И ПРИКАЗЫ:\n"
    "- Приказ N КР ДСМ-275/2020 - радиационная безопасность\n"
    "- Приказ N КР ДСМ-90 от 25.08.2022 - радиационно-опасные объекты\n"
    "- Закон РК N 442-V от 12.01.2016 - атомная энергия\n"
    "- СанПиН по ТБО - требования к площадкам, контейнерам, вывозу\n\n"
    "СТАТЬИ КоАП РК ПО ЭКОЛОГИИ (только для штрафа, одна статья):\n"
    "- Ст. 297 - радиоактивные и экологически опасные вещества\n"
    "- Ст. 315 - атмосферный воздух\n"
    "- Ст. 316 - выброс без разрешения\n"
    "- Ст. 324 - загрязнение окружающей среды\n"
    "- Ст. 326 - невыполнение условий экологического разрешения\n"
    "- Ст. 328 - нарушение охраны земель\n"
    "- Ст. 338 - нарушение правил обращения с отходами\n"
    "- Ст. 353 - нарушение правил недропользования\n\n"
    "ПРАВИЛА:\n"
    "- Только законы РК, никогда не используй законы РФ\n"
    "- Опечатки - понимай по контексту\n"
    "- Ровно 3 нормы: 2 из Экокодекса или СанПиН + 1 из КоАП\n"
    "- Ссылки только на adilet.zan.kz\n\n"
    "ФОРМАТ ОТВЕТА:\n\n"
    "НАРУШЕНИЕ: [одно предложение]\n\n"
    "НОРМЫ:\n"
    "1. [Экокодекс РК - Ст.XX - название]\n"
    "   [суть одной строкой]\n"
    "   https://adilet.zan.kz/rus/docs/K2100000400\n\n"
    "2. [Экокодекс РК или СанПиН - Ст.XX - название]\n"
    "   [суть одной строкой]\n"
    "   https://adilet.zan.kz/...\n\n"
    "3. [КоАП РК - Ст.XX - название]\n"
    "   [размер штрафа]\n"
    "   https://adilet.zan.kz/rus/docs/K1400000235"
)

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.send_message(message.chat.id,
        "Нормативный ассистент ПККР\n\n"
        "Опиши нарушение или отправь фото\n"
        "Пример: Разлив нефти на скважине")

@bot.message_handler(func=lambda message: True)
def handle_text(message):
    wait_msg = bot.send_message(message.chat.id, "Ищу нормы...")
    try:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=800,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": message.text}]
        )
        answer = response.content[0].text.strip()
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
        caption = message.caption or "Определи нарушения на фото и укажи нормы законодательства РК"
        response = client.messages.create(
            model="claude-sonnet-4-5",
            max_tokens=800,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": [
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": photo_b64}},
                {"type": "text", "text": caption}
            ]}]
        )
        answer = response.content[0].text.strip()
        bot.delete_message(message.chat.id, wait_msg.message_id)
        for part in util.smart_split(answer, chars_per_string=3000):
            bot.send_message(message.chat.id, part)
    except Exception as e:
        bot.edit_message_text("Ошибка: " + str(e), message.chat.id, wait_msg.message_id)

print("БОТ ЗАПУЩЕН")
bot.polling(none_stop=True, interval=1)
