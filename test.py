import os
import telebot
from telebot import types
import requests
from bs4 import BeautifulSoup
import datetime

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
TOKEN = os.environ.get('BOT_TOKEN')

if not TOKEN:
    print("ОШИБКА: Не найден BOT_TOKEN в переменных окружения!")
    exit(1)

# Ссылки на страницы сайта
URL_DAY = "https://schedule.spt42.ru/2_korpus/hg.htm"      # На день
URL_WEEK = "https://schedule.spt42.ru/2_korpus/hg_week.htm" # На неделю (предполагаемый адрес)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ==========================================
# 2. ПАРСЕР РАСПИСАНИЯ (Универсальный)
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

def fetch_schedule(url):
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        print(f"Ошибка подключения к {url}: {e}")
        return {}

    groups_data = {}
    current_group = None

    for row in soup.find_all("tr"):
        cells = row.find_all("td")
        if not cells: continue
        
        texts = [c.get_text(separator=" ", strip=True) for c in cells]
        first_text = texts[0].upper()
        
        if "-" in first_text and len(first_text) < 10 and " " not in first_text:
            current_group = first_text
            if current_group not in groups_data:
                groups_data[current_group] = []
            
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

# Загружаем оба расписания при старте
print("Загрузка расписания на день...")
DATA_DAY = fetch_schedule(URL_DAY)
print("Загрузка расписания на неделю...")
DATA_WEEK = fetch_schedule(URL_WEEK)

bot = telebot.TeleBot(TOKEN)

# Хранилище для выбранных групп (чтобы знать, какую группу показывать)
user_groups = {}

# ==========================================
# 3. ЛОГИКА БОТА
# ==========================================
@bot.message_handler(commands=['start', 'help'])
def start_message(message):
    if not DATA_DAY:
        bot.send_message(message.chat.id, "❌ Ошибка: не удалось загрузить расписание.")
        return

    markup = types.InlineKeyboardMarkup(row_width=4)
    buttons = [types.InlineKeyboardButton(text=g, callback_data=f"g_{g}") for g in sorted(DATA_DAY.keys())]
    markup.add(*buttons)
    
    bot.send_message(
        message.chat.id, 
        f"👋 Привет, {message.from_user.first_name}!\nВыбери свою группу:", 
        reply_markup=markup
    )

# --- Функция для генерации текста расписания ---
def generate_schedule_text(group, mode):
    if mode == "day":
        lessons = DATA_DAY.get(group, [])
        title = f"📅 *Расписание на сегодня*\n👥 *Группа: {group}*\n\n"
        empty_msg = "Сегодня пар нет (свободный день) 🎉"
        # Кнопка переключения на неделю
        switch_btn = types.InlineKeyboardButton(text="📅 На всю неделю", callback_data=f"w_{group}")
    else:
        lessons = DATA_WEEK.get(group, [])
        title = f"🗓 *Расписание на неделю*\n👥 *Группа: {group}*\n\n"
        empty_msg = "На неделю пар нет 🎉"
        # Кнопка переключения на день
        switch_btn = types.InlineKeyboardButton(text="📅 На сегодня", callback_data=f"d_{group}")

    text = title
    if lessons:
        for pair_num, info in lessons:
            text += f"🔔 *Пара {pair_num}*\n"
            text += f"📚 {info['subject']}\n"
            text += f"👨‍🏫 {info['teacher']}\n"
            text += f"🚪 Ауд: {info['room']}\n\n"
    else:
        text += empty_msg

    # Формируем кнопки
    markup = types.InlineKeyboardMarkup()
    markup.add(switch_btn)
    markup.add(types.InlineKeyboardButton(text="🔄 Выбрать другую группу", callback_data="back"))
    
    return text, markup

# --- Обработчик кнопок ---
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    data = call.data

    # Если нажали "Назад" к списку групп
    if data == "back":
        markup = types.InlineKeyboardMarkup(row_width=4)
        buttons = [types.InlineKeyboardButton(text=g, callback_data=f"g_{g}") for g in sorted(DATA_DAY.keys())]
        markup.add(*buttons)
        bot.edit_message_text("Выбери свою группу:", call.message.chat.id, call.message.message_id, reply_markup=markup)
        return

    # Обработка выбора группы, дня или недели
    action, group = data.split("_", 1)
    
    if action == "g":
        # По умолчанию показываем день
        text, markup = generate_schedule_text(group, "day")
        user_groups[call.message.chat.id] = group # Запоминаем выбор
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)
    elif action == "w":
        text, markup = generate_schedule_text(group, "week")
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)
    elif action == "d":
        text, markup = generate_schedule_text(group, "day")
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)

    bot.answer_callback_query(call.id)

# ==========================================
# 4. ЗАПУСК
# ==========================================
if __name__ == '__main__':
    if DATA_DAY or DATA_WEEK:
        print("Бот запущен!")
        bot.polling(none_stop=True)
    else:
        print("Бот не запущен (нет данных).")
