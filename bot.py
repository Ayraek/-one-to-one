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
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram import Router

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
router = Router()
dp.include_router(router)

LEVELS = ["Junior", "Middle", "Senior", "Head of Product", "CPO", "CEO"]

welcome_text = (
    "💡 Добро пожаловать в \"One to One Booster bot\" — вашего личного ассистента для прокачки навыков в продакт-менеджменте!\n\n"
    "Нажмите /start, чтобы начать 🔥"
)

# --- Работа с базой данных ---
def add_user_to_db(user_id, username, name, age):
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, username TEXT, name TEXT, age INTEGER, level TEXT, points INTEGER)''')
        cursor.execute('''INSERT OR IGNORE INTO users (id, username, name, age, level, points) VALUES (?, ?, ?, ?, ?, ?)''',
                       (user_id, username, name, age, "Junior", 0))
        conn.commit()

def get_user_from_db(user_id):
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        return cursor.fetchone()

# --- Состояния ---
class RegisterState(StatesGroup):
    name = State()
    age = State()

# --- Команды ---
@router.message(lambda message: message.text == "/start")
async def cmd_start(message: types.Message, state: FSMContext):
    user = get_user_from_db(message.from_user.id)
    if user is None:
        await message.answer("👋 Давай знакомиться! Как тебя зовут?")
        await state.set_state(RegisterState.name)
    else:
        _, username, name, age, level, points = user
        await message.answer(f"👋 Привет, {name}!")
        await message.answer(welcome_text)

@router.message(RegisterState.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Сколько тебе лет?")
    await state.set_state(RegisterState.age)

@router.message(RegisterState.age)
async def process_age(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введи возраст числом")
        return
    data = await state.get_data()
    name = data.get("name")
    add_user_to_db(message.from_user.id, message.from_user.username, name, int(message.text))
    await message.answer(f"✅ Готово, {name}! Добро пожаловать!\nНажми /start, чтобы начать")
    await state.clear()

@router.message(lambda message: message.text == "/ping")
async def cmd_ping(message: types.Message):
    await message.answer("🏓 Pong!")

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

# --- Запуск бота ---
if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot, skip_updates=True))
 