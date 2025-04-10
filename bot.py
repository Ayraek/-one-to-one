import os
from dotenv import load_dotenv
import sqlite3
import logging
import asyncio
import re
from openai import OpenAI

from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

# Загрузка переменных окружения
load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Настройка OpenAI клиента
client = OpenAI(api_key=OPENAI_API_KEY)

logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

LEVELS = ["Junior", "Middle", "Senior", "Head of Product", "CPO", "CEO"]

welcome_text = (
    "💡 **Добро пожаловать в \"One to One Booster bot\"** – вашего личного ассистента для прокачки навыков в продакт-менеджменте!..."
)

# --- Работа с базой данных ---
def add_user_to_db(user_id, username, name, age):
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''INSERT INTO users (id, username, name, age, level, points) VALUES (?, ?, ?, ?, ?, ?)''',
                       (user_id, username, name, age, "Junior", 0))
        conn.commit()

def get_user_from_db(user_id):
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        return cursor.fetchone()

def update_user_points(user_id, additional_points):
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET points = points + ? WHERE id = ?', (additional_points, user_id))
        conn.commit()

def update_level(user_id):
    user = get_user_from_db(user_id)
    if not user:
        return
    _, username, name, age, current_level, points = user
    index = LEVELS.index(current_level) if current_level in LEVELS else 0
    if points >= 50 and index < len(LEVELS) - 1:
        new_level = LEVELS[index + 1]
        with sqlite3.connect('users.db') as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET level = ? WHERE id = ?', (new_level, user[0]))
            conn.commit()
        logging.info(f"Пользователь {user[0]} повышен с уровня {current_level} до {new_level}.")

# --- Состояния ---
class RegisterState(StatesGroup):
    name = State()
    age = State()

class TaskState(StatesGroup):
    waiting_for_answer = State()

# --- Меню ---
def get_main_menu():
    keyboard = [
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="📚 Получить задание", callback_data="task")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_grades_menu():
    keyboard = [
        [InlineKeyboardButton(text="👶 Junior", callback_data="grade_junior")],
        [InlineKeyboardButton(text="🧑 Middle", callback_data="grade_middle")],
        [InlineKeyboardButton(text="👨‍💼 Senior", callback_data="grade_senior")],
        [InlineKeyboardButton(text="💼 Head of Product", callback_data="grade_head")],
        [InlineKeyboardButton(text="📊 CPO", callback_data="grade_cpo")],
        [InlineKeyboardButton(text="🚀 CEO", callback_data="grade_ceo")],
        [InlineKeyboardButton(text="🔙 Назад в главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# --- OpenAI функции ---
async def generate_question(grade: str) -> str:
    prompt = f"Сгенерируй реалистичный вопрос для продакт-менеджера уровня {grade}. Вопрос должен быть понятным, конкретным и проверять базовые знания."
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты помогаешь генерировать вопросы для продакт-менеджеров."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Ошибка генерации вопроса: {e}")
        return "❌ Ошибка генерации вопроса."

async def evaluate_answer(question: str, student_answer: str, student_name: str) -> str:
    prompt = (
        f"Вопрос: {question}\nОтвет студента: {student_answer}\n\n"
        f"Ты обращаешься к студенту по имени {student_name} от первого лица. Оцени ответ по следующим критериям:\n"
        "1. Если ответ совсем не соответствует вопросу – оцени как 0.\n"
        "2. Если ответ очень краткий и не раскрывает тему – оцени в диапазоне 0.1-0.4.\n"
        "3. Если ответ частично раскрывает тему – оцени 0.5-0.8.\n"
        "4. Если ответ полностью и детально раскрывает тему – оцени как 1.\n\n"
        "Формат:\nScore: <число>\nFeedback: <комментарий>.\n"
        f"{student_name}, я оцениваю твой ответ так..."
    )
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты преподаватель, оценивающий ответы студентов строго по заданным критериям."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Ошибка оценки ответа: {e}")
        return "❌ Ошибка оценки ответа."

async def generate_correct_answer(question: str, grade: str) -> str:
    prompt = (
        f"Ты опытный преподаватель продакт-менеджмента. Дай подробный правильный ответ на вопрос для уровня {grade}.\n\n"
        f"Вопрос: {question}\n\n"
        "Объясни ключевые моменты, приведи примеры, почему это правильно. Ответ от первого лица, к студенту."
    )
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты генерируешь подробные правильные ответы для студентов."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Ошибка генерации правильного ответа: {e}")
        return "❌ Ошибка генерации правильного ответа."

# Запуск бота
if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot, skip_updates=True))
