import os
import telebot
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
# Токен берется из переменных окружения (Railway)
TOKEN = os.environ.get('BOT_TOKEN')

if not TOKEN:
    print("ОШИБКА: Не найден BOT_TOKEN в переменных окружения!")
    exit(1)

bot = telebot.TeleBot(TOKEN)

# ==========================================
# 2. ПАРСЕР ЗВУКОВ
# ==========================================
def search_sound(query):
    """Ищет звук на Myinstants и возвращает ссылку на MP3"""
    encoded_query = quote(query)
    url = f"https://www.myinstants.com/en/search/?name={encoded_query}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        
        sound_button = soup.find("button", class_="small-button")
        
        if sound_button:
            onclick_text = sound_button.get("onclick", "")
            if "play('" in onclick_text:
                start = onclick_text.find("play('") + 6
                end = onclick_text.find("')", start)
                sound_path = onclick_text[start:end]
                
                full_url = f"https://www.myinstants.com{sound_path}"
                return full_url
                
        return None
    except Exception as e:
        print(f"Ошибка парсинга: {e}")
        return None

# ==========================================
# 3. ЛОГИКА БОТА
# ==========================================
@bot.message_handler(commands=['start', 'help'])
def start_message(message):
    bot.send_message(
        message.chat.id,
        "👋 Привет! Я бот для поиска звуков мемов.\n"
        "Напиши мне слово (например, 'vine boom', 'bruh', 'sad trombone' — лучше на английском), "
        "и я пришлю тебе звук! 🔊"
    )

@bot.message_handler(content_types=['text'])
def handle_text(message):
    query = message.text.strip()
    
    if query.startswith('/'):
        return
        
    bot.send_chat_action(message.chat.id, 'upload_voice')
    
    sound_url = search_sound(query)
    
    if sound_url:
        bot.send_audio(message.chat.id, sound_url, caption=f"🔊 Звук по запросу: {query}")
    else:
        bot.send_message(message.chat.id, f"❌ Звук по запросу '*{query}*' не найден. Попробуй другое слово.", parse_mode='Markdown')

# ==========================================
# 4. ЗАПУСК
# ==========================================
if __name__ == '__main__':
    print("Бот для звуков запущен!")
    bot.polling(none_stop=True)
