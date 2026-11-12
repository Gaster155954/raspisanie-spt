import os
import telebot
from telebot import types
import requests
from bs4 import BeautifulSoup
import threading
import time
import datetime
import re

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
TOKEN = os.environ.get('BOT_TOKEN')

if not TOKEN:
    print("ОШИБКА: Не найден BOT_TOKEN в переменных окружения!")
    exit(1)

URL_DAY = "https://schedule.spt42.ru/2_korpus/hg.htm"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

UPDATE_INTERVAL = 1800  # Автообновление раз в 30 минут

# ИСПРАВЛЕННОЕ ВРЕМЯ ЗВОНКОВ (по твоим данным)
BELL_TIMES = {
    "1": "08:30 - 09:50",
    "2": "10:00 - 11:20",
    "3": "11:40 - 13:00",
    "4": "13:20 - 14:40",
    "5": "14:50 - 16:10",
    "6": "16:15 - 17:35",
    "7": "17:40 - 19:00",
    "8": "19:00 - 20:20" # На случай 8-й пары, если она будет
}

# ==========================================
# 2. ПАРСЕР И ОБРАБОТКА ДАННЫХ
# ==========================================
def shorten_teacher(name):
    """Сокращает 'Тунгусов Сергей Владимирович' до 'Тунгусов С.В.'"""
    parts = name.strip().split()
    if len(parts) >= 3:
        return f"{parts[0]} {parts[1][0]}.{parts[2][0]}."
    return name

def shorten_subject(subject):
    """Убирает лишние префиксы из названия предмета"""
    cleaned = re.sub(r'^(МДК|УП|ПМ|ОП)\.?\s*[\d\.]*\s*', '', subject, flags=re.IGNORECASE)
    return cleaned.strip()

def parse_cell_text(cell):
    text = cell.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    if not lines: return None
    subject = lines[0]
    room = "Не указана"
    teacher = "Не указан"
    def is_room(word):
        clean_word = word.strip(',.')
        return clean_word.isdigit() or clean_word.startswith("с/п")
    words0 = subject.split()
    if words0 and is_room(words0[-1]):
        room = words0[-1]
        subject = " ".join(words0[:-1])
    if len(lines) >= 2:
        teacher_parts = []
        for line in lines[1:]:
            words = line.split()
            if room == "Не указана" and words and is_room(words[0]):
                room = words[0]
                teacher_parts.append(" ".join(words[1:]))
            else:
                teacher_parts.append(line)
        teacher = " ".join(teacher_parts).strip()
        if not teacher: teacher = "Не указан"
        
    return {
        "subject": shorten_subject(subject), 
        "room": room, 
        "teacher": shorten_teacher(teacher)
    }

def fetch_schedule():
    try:
        response = requests.get(URL_DAY, headers=HEADERS, timeout=10)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        print(f"Ошибка подключения: {e}")
        return None

    groups_data = {}
    current_group = None
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if not cells: continue
        texts = [c.get_text(separator=" ", strip=True) for c in cells]
        first_text = texts[0].upper()
        
        if not first_text: continue

        if "-" in first_text and len(first_text) < 10 and " " not in first_text:
            current_group = first_text
            if current_group not in groups_data: groups_data[current_group] = []
            if len(texts) >= 3:
                if len(texts) > 3:
                    for i in range(1, len(texts), 2):
                        if texts[i].isdigit() and i+1 < len(texts):
                            parsed = parse_cell_text(cells[i+1])
                            if parsed: groups_data[current_group].append((texts[i], parsed))
                else:
                    if texts[1].isdigit():
                        parsed = parse_cell_text(cells[2])
                        if parsed: groups_data[current_group].append((texts[1], parsed))
        elif current_group and texts and texts[0].isdigit():
            if len(texts) >= 2:
                if len(texts) > 2:
                    for i in range(0, len(texts), 2):
                        if texts[i].isdigit() and i+1 < len(texts):
                            parsed = parse_cell_text(cells[i+1])
                            if parsed: groups_data[current_group].append((texts[i], parsed))
                else:
                    parsed = parse_cell_text(cells[1])
                    if parsed: groups_data[current_group].append((texts[0], parsed))
    return groups_data

# ==========================================
# 3. АВТООБНОВЛЕНИЕ
# ==========================================
DATA = {}

def auto_update_task():
    global DATA
    while True:
        print("Фоновое обновление расписания...")
        new_data = fetch_schedule()
        if new_data: 
            DATA = new_data
            print(f"Расписание обновлено! Групп: {len(DATA)}")
        time.sleep(UPDATE_INTERVAL)

# ==========================================
# 4. ЛОГИКА БОТА
# ==========================================
bot = telebot.TeleBot(TOKEN)

def safe_edit_message(chat_id, message_id, text, parse_mode=None, reply_markup=None):
    try:
        bot.edit_message_text(text, chat_id, message_id, parse_mode=parse_mode, reply_markup=reply_markup)
    except Exception:
        try: bot.delete_message(chat_id, message_id)
        except: pass
        bot.send_message(chat_id, text, parse_mode=parse_mode, reply_markup=reply_markup)

def send_main_keyboard(chat_id, message_id=None, is_group_chat=False):
    if not DATA:
        bot.send_message(chat_id, "⏳ Данные еще загружаются...")
        return
        
    markup = types.InlineKeyboardMarkup(row_width=4)
    buttons = [types.InlineKeyboardButton(text=g, callback_data=f"g_{g}") for g in sorted(DATA.keys())]
    markup.add(*buttons)
    markup.add(types.InlineKeyboardButton(text="🔍 Найти преподавателя", callback_data="search_teacher"))

    text = "Выбери группу или нажми поиск препода:" if is_group_chat else "Выбери свою группу:"
    
    if message_id:
        safe_edit_message(chat_id, message_id, text, reply_markup=markup)
    else:
        bot.send_message(chat_id, text, reply_markup=markup)

@bot.message_handler(commands=['start', 'help'])
def start_message(message):
    is_private = message.chat.type == 'private'
    if is_private:
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
        markup.add(
            types.KeyboardButton("📅 Моё расписание"),
            types.KeyboardButton("⏰ Следующая пара"),
            types.KeyboardButton("🔍 Поиск препода"),
            types.KeyboardButton("ℹ️ Помощь")
        )
        bot.send_message(message.chat.id, f"👋 Привет, {message.from_user.first_name}!\nЯ бот с расписанием.", reply_markup=markup)
    else:
        bot.send_message(message.chat.id, "👋 Привет всем! Я бот с расписанием. Выбери группу ниже:")
    
    send_main_keyboard(message.chat.id, is_group_chat=not is_private)

@bot.message_handler(commands=['schedule'])
def schedule_command(message):
    send_main_keyboard(message.chat.id, is_group_chat=(message.chat.type != 'private'))

@bot.message_handler(commands=['search'])
def search_command(message):
    msg = bot.send_message(message.chat.id, "Введи фамилию преподавателя (например, *Тинькова*):", parse_mode='Markdown')
    bot.register_next_step_handler(msg, search_teacher_text)

@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.chat.type != 'private':
        return 

    if message.text == "ℹ️ Помощь":
        bot.send_message(message.chat.id, "📌 *Команды:*\n/start - Меню\n/schedule - Список групп\n/search - Поиск препода")
    
    elif message.text == "📅 Моё расписание" or message.text == "🔄 Сменить группу":
        send_main_keyboard(message.chat.id)
        
    elif message.text == "⏰ Следующая пара":
        hour = datetime.datetime.now().hour
        pair_num = ""
        if 8 <= hour < 10: pair_num = "1"
        elif 10 <= hour < 12: pair_num = "2"
        elif 12 <= hour < 14: pair_num = "3"
        elif 14 <= hour < 16: pair_num = "4"
        elif 16 <= hour < 18: pair_num = "5"
        elif 18 <= hour < 20: pair_num = "6"
        
        if not pair_num:
            bot.send_message(message.chat.id, "Сейчас не учебное время. Отдыхай! 🎉")
            return

        markup = types.InlineKeyboardMarkup(row_width=4)
        buttons = [types.InlineKeyboardButton(text=g, callback_data=f"g_{g}") for g in sorted(DATA.keys())]
        markup.add(*buttons)
        bot.send_message(message.chat.id, f"⏰ Сейчас примерно {pair_num}-я пара. Выбери группу:", reply_markup=markup)

    elif message.text == "🔍 Поиск препода":
        msg = bot.send_message(message.chat.id, "Введи фамилию преподавателя (например, *Тинькова*):", parse_mode='Markdown')
        bot.register_next_step_handler(msg, search_teacher_text)

def search_teacher_text(message):
    teacher_query = message.text.strip().lower()
    if not teacher_query or len(teacher_query) < 2:
        bot.send_message(message.chat.id, "Слишком короткий запрос. Попробуй снова.")
        return

    bot.send_message(message.chat.id, f"🔎 Ищу пары преподавателя: *{message.text}*...", parse_mode='Markdown')
    
    found_lessons = []
    for group, lessons in DATA.items():
        for pair_num, info in lessons:
            if teacher_query in info['teacher'].lower():
                found_lessons.append((group, pair_num, info))
    
    if not found_lessons:
        bot.send_message(message.chat.id, "Ничего не найдено. Возможно, сегодня у него нет пар.")
        return
        
    text = f"👨‍🏫 *Найдено расписание для '{message.text}':*\n\n"
    for group, pair_num, info in found_lessons:
        time_str = BELL_TIMES.get(pair_num, "")
        text += f"👥 *{group}* | {pair_num} пара ({time_str})\n"
        text += f"📚 {info['subject']} (ауд. {info['room']})\n\n"
        
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    data = call.data
    
    if data == "back":
        send_main_keyboard(call.message.chat.id, message_id=call.message.message_id, is_group_chat=(call.message.chat.type != 'private'))
        return

    if data == "search_teacher":
        bot.answer_callback_query(call.id)
        msg = bot.send_message(call.message.chat.id, "Введи фамилию преподавателя (например, *Тинькова*):", parse_mode='Markdown')
        bot.register_next_step_handler(msg, search_teacher_text)
        return

    action, group = data.split("_", 1)
    if action == "g":
        lessons = DATA.get(group, [])
        text = f"👥 *Группа: {group}*\n📅 *Расписание на сегодня*\n\n"
        
        if lessons:
            for pair_num, info in lessons:
                time_str = BELL_TIMES.get(pair_num, "")
                text += f"⏰ *{pair_num} пара* ({time_str})\n"
                text += f"📚 {info['subject']} | ауд. `{info['room']}`\n"
                text += f"👨‍🏫 {info['teacher']}\n\n"
        else:
            text += "🎉 Сегодня пар нет! Отдыхай."

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(text="🔄 Назад", callback_data="back"))
        
        safe_edit_message(call.message.chat.id, call.message.message_id, text, parse_mode='Markdown', reply_markup=markup)
    
    bot.answer_callback_query(call.id)

def set_bot_commands():
    commands = [
        types.BotCommand("start", "Главное меню"),
        types.BotCommand("schedule", "Список групп"),
        types.BotCommand("search", "Поиск преподавателя"),
        types.BotCommand("help", "Помощь")
    ]
    try:
        bot.set_my_commands(commands)
    except Exception as e:
        print(f"Ошибка меню: {e}")

if __name__ == '__main__':
    print("Первичная загрузка данных...")
    initial_data = fetch_schedule()
    if initial_data:
        DATA = initial_data
        set_bot_commands()
        
        update_thread = threading.Thread(target=auto_update_task)
        update_thread.daemon = True 
        update_thread.start()
        print("Бот запущен!")
        bot.polling(none_stop=True)
    else:
        print("Бот не запущен (нет данных).")
