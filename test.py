import os
import telebot
from telebot import types
import requests
from bs4 import BeautifulSoup

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

# ==========================================
# 2. ПАРСЕР (Оставляем без изменений)
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

print("Загрузка данных...")
DATA = fetch_schedule()
bot = telebot.TeleBot(TOKEN)

# ==========================================
# 3. ЛОГИКА И ИНТЕРФЕЙС
# ==========================================

# Команда /start
@bot.message_handler(commands=['start', 'help'])
def start_message(message):
    if not DATA:
        bot.send_message(message.chat.id, "❌ Ошибка: не удалось загрузить расписание.")
        return

    # Создаем Reply-кнопки (появляются внизу)
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_help = types.KeyboardButton("ℹ️ Помощь")
    btn_change = types.KeyboardButton("🔄 Сменить группу")
    btn_schedule = types.KeyboardButton("📅 Моё расписание")
    markup.add(btn_schedule, btn_change, btn_help)

    bot.send_message(
        message.chat.id, 
        f"👋 Привет, {message.from_user.first_name}!\nЯ бот с расписанием.\nВыбери свою группу, чтобы начать:",
        reply_markup=markup
    )
    send_group_keyboard(message.chat.id)

# Отправка списка групп (Inline)
def send_group_keyboard(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=4)
    buttons = [types.InlineKeyboardButton(text=g, callback_data=f"g_{g}") for g in sorted(DATA.keys())]
    markup.add(*buttons)
    bot.send_message(chat_id, "Выбери группу:", reply_markup=markup)

# Обработка текстовых кнопок (снизу)
@bot.message_handler(content_types=['text'])
def handle_text(message):
    if message.text == "ℹ️ Помощь":
        bot.send_message(message.chat.id, "📌 *Как пользоваться:*\n1. Выбери группу.\n2. Наслаждайся расписанием.\n\nДля добавления бота в беседу: просто добавь его как участника и напиши `/start`.")
    elif message.text == "🔄 Сменить группу":
        send_group_keyboard(message.chat.id)
    elif message.text == "📅 Моё расписание":
        bot.send_message(message.chat.id, "Пока не могу сохранить твою группу навсегда (напиши в поддержку 😉). Но ты можешь выбрать группу заново.")

# Обработка Inline-кнопок (выбор группы)
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    data = call.data
    if data == "back":
        send_group_keyboard(call.message.chat.id)
        return

    action, group = data.split("_", 1)
    if action == "g":
        lessons = DATA.get(group, [])
        
        # Красивое форматирование
        text = f"👥 *Группа: {group}*\n"
        text += f"📅 *Дата: Сегодня* (Обновлено с сайта)\n\n"
        
        if lessons:
            for pair_num, info in lessons:
                text += f"*{pair_num} пара* ──────────────\n"
                text += f"📚 {info['subject']}\n"
                text += f"👨‍🏫 {info['teacher']}\n"
                text += f"🚪 Ауд: `{info['room']}`\n\n"
        else:
            text += "🎉 Сегодня пар нет! Отдыхай."

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(text="🔄 Выбрать другую группу", callback_data="back"))
        
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode='Markdown', reply_markup=markup)
    
    bot.answer_callback_query(call.id)

# ==========================================
# 4. ЗАПУСК
# ==========================================
if __name__ == '__main__':
    if DATA:
        print("Бот запущен!")
        bot.polling(none_stop=True)
