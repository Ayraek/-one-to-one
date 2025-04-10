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
from aiogram import Router, F

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

# --- Главное меню ---
def get_main_menu():
    keyboard = [
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="📚 Получить задание", callback_data="task")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_grades_menu():
    keyboard = [
        [InlineKeyboardButton(text="👶 Junior", callback_data="grade_Junior")],
        [InlineKeyboardButton(text="🧑 Middle", callback_data="grade_Middle")],
        [InlineKeyboardButton(text="👨‍💼 Senior", callback_data="grade_Senior")],
        [InlineKeyboardButton(text="💼 Head of Product", callback_data="grade_Head of Product")],
        [InlineKeyboardButton(text="📊 CPO", callback_data="grade_CPO")],
        [InlineKeyboardButton(text="🚀 CEO", callback_data="grade_CEO")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

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
        logging.info(f"Пользователь {user[0]} повышен с {current_level} до {new_level}.")

# --- Состояния ---
class RegisterState(StatesGroup):
    name = State()
    age = State()

class TaskState(StatesGroup):
    waiting_for_answer = State()

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
        await message.answer(welcome_text, reply_markup=get_main_menu())

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
    await message.answer(f"✅ Готово, {name}! Добро пожаловать!", reply_markup=get_main_menu())
    await state.clear()

@router.message(lambda message: message.text == "/ping")
async def cmd_ping(message: types.Message):
    await message.answer("🏓 Pong!")

# --- Callback-хендлеры меню ---
@router.callback_query(F.data == "profile")
async def profile_callback(callback: types.CallbackQuery):
    user = get_user_from_db(callback.from_user.id)
    if user:
        _, username, name, age, level, points = user
        with sqlite3.connect('users.db') as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM users ORDER BY points DESC')
            all_ids = [row[0] for row in cursor.fetchall()]
            rank = all_ids.index(callback.from_user.id) + 1 if callback.from_user.id in all_ids else '—'

        text = (
            f"<b>👤 Имя:</b> {name}\n"
            f"<b>🎂 Возраст:</b> {age}\n"
            f"<b>🎯 Уровень:</b> {level}\n"
            f"<b>⭐ Баллы:</b> {points}\n"
            f"<b>🏆 Место в рейтинге:</b> {rank}"
        )
        await callback.message.answer_photo(
    photo="https://i.imgur.com/zIPzQKF.jpeg",
    caption="Добро пожаловать в One to One IT Academy!"
)
        await callback.message.answer(text, parse_mode="HTML", reply_markup=get_main_menu())
    else:
        await callback.message.edit_text("🚫 Пользователь не найден.", reply_markup=get_main_menu())
    await callback.answer()

@router.callback_query(F.data == "help")
async def help_callback(callback: types.CallbackQuery):
    text = "ℹ️ Помощь:\n/start — начать\n📚 Получить задание — выбрать уровень и решить кейс."
    await callback.message.edit_text(text, reply_markup=get_main_menu())
    await callback.answer()

@router.callback_query(F.data == "task")
async def task_callback(callback: types.CallbackQuery):
    await callback.message.edit_text("Выберите грейд, для которого хотите получить задание:", reply_markup=get_grades_menu())
    await callback.answer()

@router.callback_query(F.data.startswith("grade_"))
async def handle_grade_selection(callback: types.CallbackQuery, state: FSMContext):
    grade = callback.data.replace("grade_", "")
    question = await generate_question(grade)
    await state.set_state(TaskState.waiting_for_answer)
    await state.update_data(question=question, grade=grade, last_score=0.0)
    await callback.message.edit_text(f"💬 Задание для уровня {grade}:\n\n{question}\n\n✍️ Напиши свой ответ сообщением.")
    await callback.answer()

@router.message(TaskState.waiting_for_answer)
async def handle_task_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    grade = data.get("grade")
    question = data.get("question")
    last_score = data.get("last_score", 0.0)

    user = get_user_from_db(message.from_user.id)
    student_name = user[2] if user else "студент"

    feedback = await evaluate_answer(question, message.text, student_name)

    match = re.search(r"Score:\s*([0-9.]+)", feedback)
    new_score = float(match.group(1)) if match else 0.0

    if new_score > last_score:
        diff = new_score - last_score
        update_user_points(message.from_user.id, diff)
        update_level(message.from_user.id)
        await state.update_data(last_score=new_score)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Попробовать снова", callback_data="retry")],
        [InlineKeyboardButton(text="✅ Показать правильный ответ", callback_data="show_answer")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])

    await message.answer(f"📊 Оценка ответа:\n{feedback}", reply_markup=keyboard)
    await state.update_data(last_question=question, last_grade=grade)

@router.callback_query(F.data == "show_answer")
async def show_correct_answer(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    question = data.get("last_question")
    grade = data.get("last_grade")

    if not question or not grade:
        await callback.message.answer("❌ Нет сохранённого вопроса.", reply_markup=get_main_menu())
        await callback.answer()
        return

    correct = await generate_correct_answer(question, grade)
    await callback.message.answer(f"✅ Эталонный ответ:\n\n{correct}", reply_markup=get_main_menu())
    await callback.answer()

@router.callback_query(F.data == "retry")
async def retry_question(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    question = data.get("last_question")
    grade = data.get("last_grade")

    if not question or not grade:
        await callback.message.answer("❌ Нет сохранённого вопроса.", reply_markup=get_main_menu())
        await callback.answer()
        return

    await state.set_state(TaskState.waiting_for_answer)
    await callback.message.answer(f"✍️ Повтори, пожалуйста, ответ на вопрос:\n\n{question}")
    await callback.answer()

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
        f"Ты обращаешься к студенту по имени {student_name}. Оцени ответ по шкале от 0 до 1."
        " Формат:\nScore: <число>\nFeedback: <комментарий>."
    )
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты преподаватель, оценивающий ответы студентов строго по критериям."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Ошибка оценки ответа: {e}")
        return "❌ Ошибка оценки ответа."

async def generate_correct_answer(question: str, grade: str) -> str:
    prompt = (
        f"Ты опытный преподаватель. Дай подробный правильный ответ на вопрос для уровня {grade}.\n\n"
        f"Вопрос: {question}\n\n"
        "Ответ должен быть структурированным, понятным и полезным для обучения."
    )
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты генерируешь обучающие ответы для студентов по продакт-менеджменту."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Ошибка генерации эталонного ответа: {e}")
        return "❌ Ошибка генерации эталонного ответа."

# --- Запуск бота ---
if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot, skip_updates=True))