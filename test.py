import os
import telebot
from telebot import types
import requests
from bs4 import BeautifulSoup

# ==========================================
# 1. НАСТРОЙКИ
# ==========================================
# Railway (и другие серверы) будут брать токен из настроек переменных окружения
TOKEN = os.environ.get('BOT_TOKEN')

if not TOKEN:
    print("ОШИБКА: Не найден BOT_TOKEN в переменных окружения!")
    exit(1)

URL = "https://schedule.spt42.ru/2_korpus/hg.htm"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ==========================================
# 2. ПАРСЕР РАСПИСАНИЯ (Твой рабочий код)
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
    print("Загрузка данных с сайта...")
    try:
        response = requests.get(URL, headers=HEADERS, timeout=10)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, "html.parser")
    except Exception as e:
        print(f"Ошибка подключения к сайту: {e}")
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

    print("Данные успешно загружены!")
    return groups_data

# ==========================================
# 3. ЛОГИКА БОТА
# ==========================================
bot = telebot.TeleBot(TOKEN)
DATA = fetch_schedule()

@bot.message_handler(commands=['start', 'help'])
def start_message(message):
    if not DATA:
        bot.send_message(message.chat.id, "❌ Ошибка: не удалось загрузить расписание.")
        return

    # Создаем кнопки с группами
    markup = types.InlineKeyboardMarkup(row_width=4)
    buttons = []
    for group in sorted(DATA.keys()):
        buttons.append(types.InlineKeyboardButton(text=group, callback_data=group))
    markup.add(*buttons)
    
    bot.send_message(
        message.chat.id, 
        f"👋 Привет, {message.from_user.first_name}!\nВыбери свою группу, чтобы узнать расписание на сегодня:", 
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    group = call.data
    
    if group == "back":
        # Возвращаем меню с группами
        markup = types.InlineKeyboardMarkup(row_width=4)
        buttons = [types.InlineKeyboardButton(text=g, callback_data=g) for g in sorted(DATA.keys())]
        markup.add(*buttons)
        bot.edit_message_text(
            "Выбери свою группу:", 
            call.message.chat.id, 
            call.message.message_id, 
            reply_markup=markup
        )
        return

    if group in DATA:
        lessons = DATA[group]
        text = f"📅 *Расписание на сегодня*\n👥 *Группа: {group}*\n\n"
        
        if lessons:
            for pair_num, info in lessons:
                text += f"🔔 *Пара {pair_num}*\n"
                text += f"📚 {info['subject']}\n"
                text += f"👨‍🏫 {info['teacher']}\n"
                text += f"🚪 Ауд: {info['room']}\n\n"
        else:
            text += "Сегодня пар нет (свободный день) 🎉"
        
        # Кнопка "Назад"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(text="🔄 Выбрать другую группу", callback_data="back"))
        
        bot.send_message(call.message.chat.id, text, parse_mode='Markdown', reply_markup=markup)
    
    bot.answer_callback_query(call.id)

# ==========================================
# 4. ЗАПУСК
# ==========================================
if __name__ == '__main__':
    if DATA:
        print("Бот запущен и готов к работе! Ждем сообщений...")
        bot.polling(none_stop=True)
    else:
        print("Бот не запущен, так как не удалось спарсить расписание.")