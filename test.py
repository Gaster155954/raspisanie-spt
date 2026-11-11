import os
import telebot
from telebot import types
import requests
from bs4 import BeautifulSoup
import threading
import time
import datetime

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
TOKEN = os.environ.get('BOT_TOKEN')

if not TOKEN:
    print("ОШИБКА: Не найден BOT_TOKEN")
    exit(1)

URL_DAY = "https://schedule.spt42.ru/2_korpus/hg.htm"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

UPDATE_INTERVAL = 1800  # Автообновление раз в 30 минут

# ==========================================
# 2. ПАРСЕР
# ==========================================
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
    return {"subject": subject, "room": room, "teacher": teacher}

def fetch_schedule():
    try:
        response = requests.get(URL_DAY, headers=HEADERS, timeout=10)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        return None

    groups_data = {}
    current_group = None
    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if not cells: continue
        texts = [c.get_text(separator=" ", strip=True) for c in cells]
        first_text = texts[0].upper()
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

def send_group_keyboard(chat_id, message_id=None, is_group_chat=False):
    if not DATA:
        bot.send_message(chat_id, "⏳ Данные еще загружаются...")
        return
    markup = types.InlineKeyboardMarkup(row_width=4)
    buttons = [types.InlineKeyboardButton(text=g, callback_data=f"g_{g}") for g in sorted(DATA.keys())]
    markup.add(*buttons)
    text = "Выбери группу:" if is_group_chat else "Выбери свою группу:"
    if message_id:
        try: bot.edit_message_text(text, chat_id, message_id, reply_markup=markup)
        except: bot.send_message(chat_id, text, reply_markup=markup)
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
        bot.send_message(message.chat.id, "👋 Привет всем! Я бот с расписанием.")
    send_group_keyboard(message.chat.id, is_group_chat=not is_private)

@bot.message_handler(commands=['schedule'])
def schedule_command(message):
    send_group_keyboard(message.chat.id, is_group_chat=(message.chat.type != 'private'))

# --- ОБРАБОТКА ТЕКСТОВЫХ КОМАНД ---
@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.chat.type != 'private':
        return 

    if message.text == "ℹ️ Помощь":
        bot.send_message(message.chat.id, "📌 *Команды:*\n/start - Меню\n📅 Моё расписание - Список групп\n⏰ Следующая пара - Что сейчас идет\n🔍 Поиск препода - Найти пары преподавателя")
    
    elif message.text == "📅 Моё расписание" or message.text == "🔄 Сменить группу":
        send_group_keyboard(message.chat.id)
        
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

        bot.send_message(message.chat.id, f"⏰ Сейчас примерно {pair_num}-я пара. Выбери свою группу, чтобы узнать подробности:")
        markup = types.InlineKeyboardMarkup(row_width=4)
        buttons = [types.InlineKeyboardButton(text=g, callback_data=f"g_{g}") for g in sorted(DATA.keys())]
        markup.add(*buttons)
        bot.send_message(message.chat.id, "Выбери группу:", reply_markup=markup)

    elif message.text == "🔍 Поиск препода":
        msg = bot.send_message(message.chat.id, "Введи фамилию преподавателя (например, *Тинькова*):", parse_mode='Markdown')
        bot.register_next_step_handler(msg, search_teacher)

def search_teacher(message):
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
        bot.send_message(message.chat.id, "Ничего не найдено. Возможно, сегодня у него нет пар или фамилия написана иначе.")
        return
        
    text = f"👨‍🏫 *Найдено расписание для '{message.text}':*\n\n"
    for group, pair_num, info in found_lessons:
        text += f"👥 *Группа {group}* ({pair_num} пара)\n"
        text += f"📚 {info['subject']}\n"
        text += f"🚪 Ауд: {info['room']}\n\n"
        
    bot.send_message(message.chat.id, text, parse_mode='Markdown')

# --- ОБРАБОТКА ИНЛАЙН-КНОПОК ---
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    data = call.data
    if data == "back":
        send_group_keyboard(call.message.chat.id, message_id=call.message.message_id, is_group_chat=(call.message.chat.type != 'private'))
        return

    action, group = data.split("_", 1)
    if action == "g":
        lessons = DATA.get(group, [])
        text = f"👥 *Группа: {group}*\n📅 *Расписание на сегодня*\n\n"
        
        if lessons:
            for pair_num, info in lessons:
                text += f"*{pair_num} пара* ──────────────\n"
                text += f"📚 {info['subject']}\n"
                text += f"👨‍🏫 {info['teacher']}\n"
                text += f"🚪 Ауд: `{info['room']}`\n\n"
        else:
            text += "🎉 Сегодня пар нет! Отдыхай."

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(text="🔄 Выбрать другую", callback_data="back"))
        
        try:
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)
        except:
            bot.send_message(call.message.chat.id, text, parse_mode='Markdown', reply_markup=markup)
    
    bot.answer_callback_query(call.id)

# ==========================================
# 5. ЗАПУСК
# ==========================================
if __name__ == '__main__':
    print("Первичная загрузка данных...")
    initial_data = fetch_schedule()
    if initial_data:
        DATA = initial_data
        update_thread = threading.Thread(target=auto_update_task)
        update_thread.daemon = True 
        update_thread.start()
        print("Бот запущен!")
        bot.polling(none_stop=True)
    else:
        print("Бот не запущен (нет данных).")
