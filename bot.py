import os
import requests
import json
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ---------- 1. ПОИСК ЗАКОНА ЧЕРЕЗ API zan.gov.kz ----------
def search_law(query):
    search_url = "http://zan.gov.kz/api/documents/search"
    payload = {
        "text": query,
        "lang": "rus",
        "status": ["active"]
    }
    try:
        response = requests.post(search_url, json=payload, timeout=30)
        response.raise_for_status()
        results = response.json()
        if results and len(results) > 0:
            doc_id = results[0].get('id')
            if doc_id:
                doc_url = f"http://zan.gov.kz/api/documents/{doc_id}/rus?withHtml=false"
                doc_response = requests.get(doc_url, timeout=30)
                doc_response.raise_for_status()
                doc_data = doc_response.json()
                full_text = doc_data.get('content', 'Не удалось получить текст.')
                title = doc_data.get('title', 'Без названия')
                return {"success": True, "title": title, "text": full_text, "id": doc_id}
        return {"success": False, "error": "По вашему запросу ничего не найдено."}
    except Exception as e:
        return {"success": False, "error": f"Ошибка при поиске: {str(e)}"}

# ---------- 2. АНАЛИЗ ЧЕРЕЗ DeepSeek ----------
async def get_deepseek_response(question, law_text):
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return "Ошибка: не настроен API-ключ DeepSeek."
    
    url = "https://api.deepseek.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    system_prompt = (
        "Ты — юридический ассистент по законодательству Республики Казахстан. "
        "Отвечай на вопрос пользователя, используя ТОЛЬКО приведённый ниже текст закона. "
        "Если текст не содержит ответа, так и скажи. Не используй свои общие знания."
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

# ---------- 3. ОБРАБОТЧИК СООБЩЕНИЙ ----------
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_question = update.message.text
    await update.message.reply_text("🔍 Ищу ответ в законах Казахстана...")

    search_result = search_law(user_question)
    if not search_result["success"]:
        await update.message.reply_text(f"❌ {search_result['error']}")
        return

    await update.message.reply_text(f"📄 Нашёл: *{search_result['title']}*. Анализирую...", parse_mode='Markdown')
    ai_answer = await get_deepseek_response(user_question, search_result['text'])
    
    source_link = f"https://adilet.zan.kz/rus/docs/{search_result['id']}"
    final_response = f"{ai_answer}\n\n📎 *Источник:* [Ссылка на документ]({source_link})"
    await update.message.reply_text(final_response, parse_mode='Markdown', disable_web_page_preview=True)

# ---------- 4. КОМАНДА /start ----------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я — юридический помощник РК. Задай вопрос, и я найду ответ в актуальных законах.")

# ---------- 5. ЗАПУСК ----------
def main():
    token = os.getenv("TELEGRAM_TOKEN")
    if not token:
        print("Ошибка: переменная TELEGRAM_TOKEN не найдена!")
        return

    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен...")
    app.run_polling()

if __name__ == '__main__':
    main()
