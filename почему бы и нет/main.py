import telebot
import requests
import json
import schedule
import time
from threading import Thread
import sqlite3
from datetime import datetime

bot = telebot.TeleBot('6156011452:AAF8eAq5HLxzDDF-gFYEgSXYMpiN-00JV-I')
API_KEY = "8418ca95623f7fb933727b8e367e8361"

# Подключение к базе данных
conn = sqlite3.connect('schedule.db', check_same_thread=False)
cursor = conn.cursor()

# Создание таблиц, если их нет
cursor.execute('''CREATE TABLE IF NOT EXISTS tasks (
                  user_id INTEGER,
                  day TEXT,
                  time TEXT,
                  task TEXT,
                  done INTEGER DEFAULT 0)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                  user_id INTEGER PRIMARY KEY,
                  name TEXT,
                  surname TEXT,
                  city TEXT)''')

conn.commit()

# Основная клавиатура
def main_menu():
    keyboard = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(telebot.types.KeyboardButton('/register'))
    keyboard.add(telebot.types.KeyboardButton('/set_schedule'))
    keyboard.add(telebot.types.KeyboardButton('/view_schedule'))
    keyboard.add(telebot.types.KeyboardButton('/weather'))
    return keyboard

# Регистрация пользователя
@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(message.chat.id, 'Hello! Please choose an option:', reply_markup=main_menu())

@bot.message_handler(commands=['register'])
def register(message):
    bot.send_message(message.chat.id, 'Please enter your first and last name in the format: Firstname Lastname.')
    bot.register_next_step_handler(message, save_user_data)

def save_user_data(message):
    try:
        name, surname = message.text.split()
        user_id = message.chat.id
        # Сохраняем данные пользователя в базе данных
        cursor.execute("INSERT OR REPLACE INTO users (user_id, name, surname) VALUES (?, ?, ?)", (user_id, name, surname))
        conn.commit()
        bot.send_message(message.chat.id, f'You are registered! Name: {name}, Surname: {surname}. Now you can set your weekly schedule or get weather updates.', reply_markup=main_menu())
    except ValueError:
        bot.send_message(message.chat.id, 'Please enter both first and last name. Try again with the format: Firstname Lastname.')
        bot.register_next_step_handler(message, save_user_data)

# Установка расписания
@bot.message_handler(commands=['set_schedule'])
def set_schedule(message):
    bot.send_message(message.chat.id, 'Enter the schedule for a specific day in the format: Day HH:MM Task (e.g., Monday 10:20 Have breakfast).')
    bot.register_next_step_handler(message, save_task)

def save_task(message):
    try:
        day, time, task = message.text.split(maxsplit=2)
        user_id = message.chat.id
        # Сохраняем задание в базе данных
        cursor.execute("INSERT INTO tasks (user_id, day, time, task) VALUES (?, ?, ?, ?)", (user_id, day.capitalize(), time, task))
        conn.commit()
        bot.send_message(message.chat.id, f'Task "{task}" for {day} at {time} has been added.', reply_markup=main_menu())
    except ValueError:
        bot.send_message(message.chat.id, 'Invalid format. Please use: Day HH:MM Task (e.g., Monday 10:20 Have breakfast).')
        bot.register_next_step_handler(message, save_task)

# Просмотр всех задач на неделю
@bot.message_handler(commands=['view_schedule'])
def view_schedule(message):
    user_id = message.chat.id
    cursor.execute("SELECT day, time, task, done FROM tasks WHERE user_id = ? ORDER BY day, time", (user_id,))
    tasks = cursor.fetchall()
    
    if tasks:
        schedule_msg = "Your tasks for the week:\n"
        for task in tasks:
            status = "✅" if task[3] == 1 else "❌"
            schedule_msg += f"{task[0]} {task[1]} - {task[2]} {status}\n"
        bot.send_message(user_id, schedule_msg, reply_markup=main_menu())
    else:
        bot.send_message(user_id, "You have no tasks scheduled.", reply_markup=main_menu())

# Получение погоды
@bot.message_handler(commands=['weather'])
def weather(message):
    bot.send_message(message.chat.id, 'Please enter your city for weather updates.')
    bot.register_next_step_handler(message, get_weather)

def get_weather(message):
    city = message.text.strip().lower()
    res = requests.get(f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric")
    
    if res.status_code != 200:
        bot.send_message(message.chat.id, 'Could not retrieve weather data. Please check the city name.', reply_markup=main_menu())
        return
    
    data = json.loads(res.text)
    temp = data["main"]["temp"]
    bot.send_message(message.chat.id, f'The weather in {city.title()} is now: {temp}°C.', reply_markup=main_menu())

    # Добавляем логику для изображений на основе температуры
    image_path = "images/cool.png" if temp < 15 else "images/warm.png"
    
    try:
        with open(image_path, 'rb') as photo:
            bot.send_photo(message.chat.id, photo)
    except FileNotFoundError:
        bot.send_message(message.chat.id, 'Image not found.', reply_markup=main_menu())

# Отправка задачи по расписанию
def send_scheduled_tasks():
    current_time = datetime.now().strftime("%H:%M")
    current_day = datetime.now().strftime("%A")

    cursor.execute("SELECT user_id, task FROM tasks WHERE day = ? AND time = ? AND done = 0", (current_day, current_time))
    tasks = cursor.fetchall()

    for task in tasks:
        user_id, task_name = task
        bot.send_message(user_id, f"Reminder: {task_name} at {current_time}! Did you complete it? Reply with Yes or No.")
        bot.register_next_step_handler_by_chat_id(user_id, check_task_completion, current_day, task_name)

# Проверка выполнения задачи
def check_task_completion(message, day, task_name):
    if message.text.lower() == "yes":
        cursor.execute("UPDATE tasks SET done = 1 WHERE user_id = ? AND day = ? AND task = ?", (message.chat.id, day, task_name))
        conn.commit()
        bot.send_message(message.chat.id, f"Great! You have completed: {task_name}", reply_markup=main_menu())
    elif message.text.lower() == "no":
        bot.send_message(message.chat.id, f"Don't forget to complete: {task_name} later!", reply_markup=main_menu())

# Настраиваем расписание напоминаний
def schedule_jobs():
    schedule.every().minute.do(send_scheduled_tasks)  # Проверка каждую минуту

    while True:
        schedule.run_pending()
        time.sleep(1)

# Запуск планировщика в отдельном потоке
def run_scheduler():
    task_thread = Thread(target=schedule_jobs)
    task_thread.start()

run_scheduler()
bot.polling(none_stop=True)