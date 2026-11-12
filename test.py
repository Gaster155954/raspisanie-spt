import os
import telebot
from telebot import types
import requests
from bs4 import BeautifulSoup
from urllib.parse import quote

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
TOKEN = os.environ.get('BOT_TOKEN')

if not TOKEN:
    print("ОШИБКА: Не найден BOT_TOKEN")
    exit(1)

bot = telebot.TeleBot(TOKEN)

# Словарь с актуальными мемами 2026 года
# Ключ - то, что видит пользователь. Значение - запрос для поиска.
HOT_MEMES = {
    "Литвин (Делай!)": "litvin delai",
    "MrBeast (Rizz)": "mrbeast rizz",
    "MrBeast (Рис)": "mrbeast rice",
    "Mellstroy (Бурмалда)": "mellstroy burmaldа",
    "Mellstroy (Мама птица)": "mellstroy mama ptitsa",
    "6-7 (Сикс-севен)": "six seven meme",
    "Черемша": "cheremsha",
    "Воздухан": "vozduhan"
}

# ==========================================
# 2. ПАРСЕР ЗВУКОВ
# ==========================================
def search_sound(query):
    encoded_query = quote(query)
    url = f"https://www.myinstants.com/en/search/?name={encoded_query}"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Ищем все кнопки со звуками
        sound_buttons = soup.find_all("button", class_="small-button")
        
        for button in sound_buttons:
            onclick_text = button.get("onclick", "")
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
    # Создаем кнопки с горячими мемами
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    for meme_name in HOT_MEMES.keys():
        markup.add(types.KeyboardButton(meme_name))
    
    bot.send_message(
        message.chat.id,
        "👋 Привет! Я бот для поиска звуков мемов.\n"
        "Напиши мне слово (например, 'vine boom' или 'bruh'), "
        "или нажми на кнопку с актуальным мемом ниже! 🔊",
        reply_markup=markup
    )

@bot.message_handler(content_types=['text'])
def handle_text(message):
    query = message.text.strip()
    
    if query.startswith('/'):
        return
    
    # Проверяем, не нажал ли пользователь на кнопку с горячим мемом
    if query in HOT_MEMES:
        search_query = HOT_MEMES[query]
        bot.send_message(message.chat.id, f"🔎 Ищу звук: {query}...")
    else:
        search_query = query
        
    bot.send_chat_action(message.chat.id, 'upload_voice')
    
    sound_url = search_sound(search_query)
    
    if sound_url:
        try:
            # Скачиваем файл и отправляем как файл, чтобы Telegram не блокировал
            audio_response = requests.get(sound_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            audio_response.raise_for_status()
            
            import io
            audio_file = io.BytesIO(audio_response.content)
            audio_file.name = 'sound.mp3'
            
            bot.send_audio(message.chat.id, audio_file, caption=f"🔊 {query}")
            
        except Exception as e:
            print(f"Ошибка отправки: {e}")
            bot.send_message(message.chat.id, "❌ Нашёл звук, но не смог его отправить. Попробуй другой запрос.")
    else:
        bot.send_message(message.chat.id, f"❌ Звук по запросу '*{query}*' не найден. Попробуй другое слово или нажми на кнопку.", parse_mode='Markdown')

# ==========================================
# 4. ЗАПУСК
# ==========================================
if __name__ == '__main__':
    print("Бот для звуков запущен!")
    bot.polling(none_stop=True)
