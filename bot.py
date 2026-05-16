import os
import requests
import json
import urllib.parse
from bs4 import BeautifulSoup
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import certifi
import ssl

# ---------- 1. ПОИСК ЗАКОНА через ПАРСИНГ adilet.zan.kz ----------
def search_law(query):
    search_url = f"https://adilet.zan.kz/rus/search?q={urllib.parse.quote(query)}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    try:
        # 1. Выполняем поисковой запрос с проверкой сертификатов через certifi
        response = requests.get(search_url, headers=headers, timeout=30, verify=certifi.where())
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        first_link = soup.select_one('div.search-result-item a')
        if not first_link:
            return {"success": False, "error": "По вашему запросу ничего не найдено."}
        
        doc_url = 'https://adilet.zan.kz' + first_link.get('href')
        doc_title = first_link.get_text(strip=True)
        
        # 2. Открываем страницу документа
        doc_response = requests.get(doc_url, headers=headers, timeout=30, verify=certifi.where())
        doc_response.raise_for_status()
        doc_soup = BeautifulSoup(doc_response.text, 'html.parser')
        
        content_div = doc_soup.select_one('div.document-text div.text-justify')
        if not content_div:
            content_div = doc_soup.select_one('div.document-text')
            
        if content_div:
            full_text = ' '.join(content_div.stripped_strings)
        else:
            full_text = "Не удалось получить текст документа."

        return {"success": True, "title": doc_title, "text": full_text, "url": doc_url}
        
    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Ошибка соединения: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Неизвестная ошибка: {str(e)}"}
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    system_prompt = (
        "Ты — юридический ассистент по законодательству Республики Казахстан. "
        "Отвечай на вопрос пользователя, используя ТОЛЬКО приведённый ниже текст закона. "
        "Если текст не содержит ответа, так и скажи. Не используй свои общие знания. "
        "Отвечай на том же языке, на котором задан вопрос."
    )
    
    data = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Текст закона:\n---\n{law_text}\n---\n\nВопрос: {question}"}
        ],
        "temperature": 0.3
    }

    try:
        response = requests.post(url, headers=headers, json=data, timeout=60)
        response.raise_for_status()
        reply = response.json()["choices"][0]["message"]["content"]
        return reply
    except Exception as e:
        return f"Ошибка при обращении к DeepSeek: {str(e)}"


# ---------- 3. ОБРАБОТЧИК СООБЩЕНИЙ (без изменений) ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_question = update.message.text
    await update.message.reply_text("🔍 Ищу ответ в законах Казахстана, подождите немного...")

    search_result = search_law(user_question)
    if not search_result["success"]:
        await update.message.reply_text(f"❌ {search_result['error']}")
        return

    await update.message.reply_text(f"📄 Нашёл документ: *{search_result['title']}*.\n🧠 Анализирую текст, еще секунду...", parse_mode='Markdown')
    ai_answer = await get_deepseek_response(user_question, search_result['text'])
    
    final_response = f"{ai_answer}\n\n📎 *Источник:* [Ссылка на документ]({search_result['url']})"
    await update.message.reply_text(final_response, parse_mode='Markdown', disable_web_page_preview=True)


# ---------- 4. КОМАНДА /start (без изменений) ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я — юридический помощник РК. Задай мне вопрос, и я найду ответ в актуальных законах.")


# ---------- 5. ЗАПУСК (без изменений) ----------
def main():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("Ошибка: переменная TELEGRAM_TOKEN не найдена!")
        return

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен и готов к работе...")
    app.run_polling()

if __name__ == '__main__':
    main()
