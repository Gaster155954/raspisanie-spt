import os
import telebot
from telebot import types
import requests
import io
import time

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
TOKEN = os.environ.get('BOT_TOKEN')

if not TOKEN:
    print("ОШИБКА: Не найден BOT_TOKEN в переменных окружения!")
    exit(1)

bot = telebot.TeleBot(TOKEN)

# ==========================================
# 2. БАЗА МЕМОВ (Прямые ссылки на MP3)
# ==========================================
# Я подобрал рабочие ссылки на популярные звуки
MEMES = {
    "litvin": {
        "name": "Литвин (Делай!)",
        "url": "https://www.myinstants.com/media/sounds/litvin-delai.mp3" 
    },
    "mellstroy": {
        "name": "Меллстрой (Бурмалда)",
        "url": "https://www.myinstants.com/media/sounds/mellstroy-burmaldа.mp3"
    },
    "mrbeast": {
        "name": "MrBeast (Rizz)",
        "url": "https://www.myinstants.com/media/sounds/mrbeast-rizz.mp3"
    },
    "vineboom": {
        "name": "Vine Boom",
        "url": "https://www.myinstants.com/media/sounds/vine-boom.mp3"
    },
    "bruh": {
        "name": "Bruh",
        "url": "https://www.myinstants.com/media/sounds/bruh-sound-effect.mp3"
    },
    "fart": {
        "name": "Пукан",
        "url": "https://www.myinstants.com/media/sounds/fart-with-reverb.mp3"
    },
    "windows": {
        "name": "Windows XP",
        "url": "https://www.myinstants.com/media/sounds/windows-xp-startup.mp3"
    }
}

# ==========================================
# 3. ЛОГИКА БОТА
# ==========================================

# Главное меню (Reply-кнопки)
def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    # Берем первые 6 мемов для кнопок
    keys = list(MEMES.keys())[:6]
    for key in keys:
        markup.add(types.KeyboardButton(MEMES[key]["name"]))
    return markup

# Отправка звука
def send_meme_sound(chat_id, meme_key, message_id=None):
    meme = MEMES.get(meme_key)
    if not meme:
        bot.send_message(chat_id, "❌ Звук не найден.")
        return

    # Отправляем сообщение "печатает" (загружает голосовое)
    bot.send_chat_action(chat_id, 'record_voice')
    
    try:
        # 1. Скачиваем MP3
        response = requests.get(meme["url"], headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        response.raise_for_status()
        
        # 2. Сохраняем в память
        audio_file = io.BytesIO(response.content)
        audio_file.name = f"{meme_key}.mp3"
        
        # 3. Отправляем как голосовое сообщение (voice)
        # В Telegram это выглядит как кружок с волной
        sent_msg = bot.send_voice(
            chat_id, 
            audio_file, 
            caption=f"🔊 *{meme['name']}*", 
            parse_mode='Markdown'
        )
        
        # 4. Добавляем кнопки "Ещё мемы" под сообщением (Inline)
        markup = types.InlineKeyboardMarkup(row_width=3)
        inline_buttons = []
        for k, v in MEMES.items():
            inline_buttons.append(types.InlineKeyboardButton(text=v["name"], callback_data=f"play_{k}"))
        markup.add(*inline_buttons)
        
        bot.edit_message_reply_markup(chat_id, sent_msg.message_id, reply_markup=markup)
        
    except Exception as e:
        print(f"Ошибка при отправке: {e}")
        bot.send_message(chat_id, "⚠️ Не удалось скачать звук. Возможно, ссылка устарела.")

# ==========================================
# 4. ОБРАБОТЧИКИ
# ==========================================

@bot.message_handler(commands=['start', 'help'])
def start_message(message):
    bot.send_message(
        message.chat.id,
        "👋 Привет! Я бот с мемными звуками.\n"
        "Выбери мем на клавиатуре снизу или нажми на кнопку в сообщении, "
        "чтобы я прислал тебе звук! 🔊",
        reply_markup=get_main_menu()
    )

@bot.message_handler(content_types=['text'])
def handle_text(message):
    # Ищем, к какому мему относится текст
    selected_key = None
    for key, value in MEMES.items():
        if message.text == value["name"]:
            selected_key = key
            break
            
    if selected_key:
        send_meme_sound(message.chat.id, selected_key)
    else:
        bot.send_message(message.chat.id, "🤷‍♂️ Я знаю только мемы с кнопок. Выбери один из них!")

@bot.callback_query_handler(func=lambda call: True)
def handle_callback(call):
    # Обработка нажатий на Inline-кнопки (play_xxx)
    if call.data.startswith("play_"):
        meme_key = call.data.replace("play_", "")
        send_meme_sound(call.message.chat.id, meme_key)
        
    bot.answer_callback_query(call.id)

# ==========================================
# 5. ЗАПУСК
# ==========================================
if __name__ == '__main__':
    print("Бот с мемами запущен!")
    bot.polling(none_stop=True)
