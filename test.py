import os
import telebot
from telebot import types
import requests
from bs4 import BeautifulSoup
import io
import re

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
TOKEN = os.environ.get('BOT_TOKEN')

if not TOKEN:
    print("ОШИБКА: Не найден BOT_TOKEN")
    exit(1)

bot = telebot.TeleBot(TOKEN)

# ==========================================
# 2. ЖИВОЙ ПОИСК ЗВУКОВ (Парсер Myinstants)
# ==========================================
def search_and_download_sound(query):
    """Ищет звук на Myinstants и возвращает байты MP3"""
    # Кодируем запрос для URL
    encoded_query = requests.utils.quote(query)
    url = f"https://www.myinstants.com/en/search/?name={encoded_query}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        # 1. Загружаем страницу поиска
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 2. Ищем первую кнопку со звуком
        # На Myinstants кнопки обычно имеют класс 'small-button' и атрибут onclick
        button = soup.find("button", class_="small-button")
        if not button:
            return None, "Не найдено"
            
        onclick_text = button.get("onclick", "")
        
        # 3. Вытаскиваем путь к MP3 из onclick (формат: play('/media/sounds/...mp3'))
        match = re.search(r"play\('([^']+\.mp3)'\)", onclick_text)
        if not match:
            return None, "Ошибка парсинга ссылки"
            
        sound_path = match.group(1)
        # Собираем полную ссылку
        if sound_path.startswith("/"):
            sound_url = f"https://www.myinstants.com{sound_path}"
        else:
            sound_url = f"https://www.myinstants.com/{sound_path}"
            
        # 4. Скачиваем сам файл MP3
        audio_response = requests.get(sound_url, headers=headers, timeout=15)
        audio_response.raise_for_status()
        
        return audio_response.content, None
        
    except Exception as e:
        print(f"Ошибка поиска: {e}")
        return None, str(e)

# ==========================================
# 3. ЛОГИКА БОТА
# ==========================================
@bot.message_handler(commands=['start', 'help'])
def start_message(message):
    # Оставляем пару кнопок для быстрого доступа к самым хайповым мемам
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("Tung Tung Sahur"),
        types.KeyboardButton("Bombardiro Crocodilo"),
        types.KeyboardButton("MrBeast"),
        types.KeyboardButton("Mellstroy")
    )
    
    bot.send_message(
        message.chat.id,
        "👋 Привет! Я бот с живым поиском мемных звуков.\n\n"
        "Напиши мне **любое слово** (на английском или русском), и я поищу его в огромной базе Myinstants и пришлю тебе звук! 🔍\n\n"
        "Например: `litvin`, `rizz`, `bruh`, `tralalero` или `skibidi`.\n"
        "Или нажми на кнопку с горячим мемом ниже.",
        reply_markup=markup,
        parse_mode='Markdown'
    )

@bot.message_handler(content_types=['text'])
def handle_text(message):
    query = message.text.strip()
    
    # Игнорируем команды
    if query.startswith('/'):
        return

    # Показываем, что бот "печатает"
    bot.send_chat_action(message.chat.id, 'upload_voice')
    
    # Ищем и скачиваем звук
    audio_bytes, error = search_and_download_sound(query)
    
    if audio_bytes:
        try:
            # Отправляем как голосовое сообщение (кружок с волной)
            audio_file = io.BytesIO(audio_bytes)
            audio_file.name = f"{query}.mp3"
            
            bot.send_voice(
                message.chat.id, 
                audio_file, 
                caption=f"🔊 Найдено по запросу: *{query}*", 
                parse_mode='Markdown'
            )
        except Exception as e:
            print(f"Ошибка отправки: {e}")
            bot.send_message(message.chat.id, "❌ Звук найден, но не удалось отправить. Попробуй другой запрос.")
    else:
        # Если ничего не нашли или произошла ошибка
        if error == "Не найдено":
            bot.send_message(message.chat.id, f"🤷‍♂️ По запросу `{query}` ничего не найдено. Попробуй написать по-другому (лучше на английском).")
        else:
            bot.send_message(message.chat.id, "⚠️ Произошла ошибка при поиске. Попробуй позже или другой запрос.")

# ==========================================
# 4. ЗАПУСК
# ==========================================
if __name__ == '__main__':
    print("Бот с живым поиском мемов запущен!")
    bot.polling(none_stop=True)
