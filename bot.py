import telebot
from telebot import util
import anthropic
import requests
import base64
import os
import re

TELEGRAM_TOKEN = os.environ.get('TELEGRAM_TOKEN')
ANTHROPIC_KEY = os.environ.get('ANTHROPIC_KEY')

client = anthropic.Anthropic(api_key=ANTHROPIC_KEY, timeout=30.0)
bot = telebot.TeleBot(TELEGRAM_TOKEN)

# Загружаем файлы законов
LAW_FILES = {
    'atom': ('atom.txt', 'Закон РК об использовании атомной энергии № 442-V от 12.01.2016'),
    'ecocode': ('ecocode.txt', 'Экологический кодекс РК от 02.01.2021 № 400-VI'),
    'nedra': ('nedra.txt', 'Кодекс РК о недрах и недропользовании'),
    'sanpin1': ('sanpin1.txt', 'Санитарные правила по радиационной безопасности (Приказ № ҚР ДСМ-275/2020)'),
    'sanpin2': ('sanpin2.txt', 'Санитарные правила и нормы РК'),
}

def load_laws():
    laws = {}
    for key, (filename, title) in LAW_FILES.items():
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                laws[key] = {'text': f.read(), 'title': title}
        except:
            laws[key] = {'text': '', 'title': title}
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
        'скважин': ['ecocode', 'nedra'],
        'разлив': ['ecocode', 'nedra'],
        'розлив': ['ecocode', 'nedra'],
        'отход': ['ecocode', 'sanpin2'],
        'шлам': ['ecocode', 'nedra'],
        'замазучен': ['ecocode', 'nedra'],
        'загрязнен': ['ecocode'],
        'земл': ['ecocode'],
        'почв': ['ecocode'],
        'вод': ['ecocode'],
        'атмосфер': ['ecocode'],
        'выброс': ['ecocode'],
        'тбо': ['sanpin2', 'ecocode'],
        'мусор': ['sanpin2', 'ecocode'],
        'контейнер': ['sanpin2'],
        'недр': ['nedra'],
        'месторожден': ['nedra', 'ecocode'],
    }
    
    # Определяем какие файлы искать
    files_to_search = set()
    for word in words:
        for topic, files in TOPICS.items():
            if topic in word or word in topic:
                files_to_search.update(files)
    
    if not files_to_search:
        files_to_search = {'ecocode', 'atom', 'sanpin1'}
    
    # Ищем блоки по статьям
    results = []
    for key in files_to_search:
        if key not in laws or not laws[key]['text']:
            continue
        text = laws[key]['text']
        title = laws[key]['title']
        
        blocks = re.split(r'(?=Статья\s+\d+)', text)
        for block in blocks:
            if len(block.strip()) < 50:
                continue
            block_lower = block.lower()
            score = sum(1 for w in words if w in block_lower)
            if score > 0:
                results.append((score, title, block[:2000]))
    
    results.sort(key=lambda x: x[0], reverse=True)
    
    context = ""
    total = 0
    for score, title, block in results:
        chunk = f"\n=== {title} ===\n{block}\n"
        if total + len(chunk) > max_chars:
            break
        context += chunk
        total += len(chunk)
    
    return context

LAWS = load_laws()

SYSTEM_PROMPT = """Ты — нормативный ассистент инженера охраны окружающей среды АО «ПетроКазахстан Кумколь Ресорсиз», Казахстан. Месторождения КАМ — Кызылкия, Арыскум, Майбулак.

ТВОЯ ЗАДАЧА: найти в предоставленных фрагментах законов точные статьи применимые к нарушению.

ПРАВИЛА:
- Используй ТОЛЬКО статьи из предоставленных фрагментов
- Опечатки и ошибки в запросе — понимай по контексту
- Если статья есть в тексте — цитируй её точно
- Никогда не используй законы РФ
- Ссылки на adilet.zan.kz

ФОРМАТ ОТВЕТА:

НАРУШЕНИЕ: [одно предложение]

НОРМЫ:
1. [Название зак
