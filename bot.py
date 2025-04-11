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

# Определения уровней
LEVELS = ["Junior", "Middle", "Senior", "Head of Product", "CPO", "CEO"]

welcome_text = (
    "💡 Добро пожаловать в \"One to One Booster bot\" — вашего личного ассистента для прокачки навыков в продакт-менеджменте!\n\n"
    "Нажмите /start, чтобы начать 🔥"
)

# --- Главное меню и меню выбора ---
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

def get_topics_menu():
    keyboard = [
        [InlineKeyboardButton(text="Гипотезы", callback_data="topic_Гипотезы")],
        [InlineKeyboardButton(text="Маркетинг", callback_data="topic_Маркетинг")],
        [InlineKeyboardButton(text="Метрики", callback_data="topic_Метрики")],
        [InlineKeyboardButton(text="Управление командой", callback_data="topic_Управление командой")],
        [InlineKeyboardButton(text="Soft skills", callback_data="topic_Soft skills")],
        [InlineKeyboardButton(text="Стратегия", callback_data="topic_Стратегия")],
        [InlineKeyboardButton(text="Требования к продукту", callback_data="topic_Требования к продукту")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_grades")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# --- Работа с базой данных (таблица пользователей) ---
def add_user_to_db(user_id, username, name, age):
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY, 
                username TEXT, 
                name TEXT, 
                age INTEGER, 
                level TEXT, 
                points REAL
            )
        ''')
        cursor.execute('''
            INSERT OR IGNORE INTO users (id, username, name, age, level, points) 
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, username, name, age, "Junior", 0.0))
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
    """
    Логика перехода на следующий уровень:
    Требуемые баллы = 50 * (индекс уровня + 1).
    """
    user = get_user_from_db(user_id)
    if not user:
        return
    # user = (id, username, name, age, level, points)
    _, username, name, age, current_level, points = user
    cur_index = LEVELS.index(current_level)
    required_points = 50 * (cur_index + 1)
    if points >= required_points and cur_index < len(LEVELS) - 1:
        new_level = LEVELS[cur_index + 1]
        with sqlite3.connect('users.db') as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET level = ? WHERE id = ?', (new_level, user[0]))
            conn.commit()
        logging.info(f"Пользователь {user[0]} повышен с {current_level} до {new_level}.")

# --- Работа с таблицей заданий (tasks) ---
def create_tasks_table():
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                question TEXT,
                best_score REAL
            )
        ''')
        conn.commit()

def add_task_for_user(user_id, question):
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO tasks (user_id, question, best_score)
            VALUES (?, ?, ?)
        ''', (user_id, question, 0.0))
        conn.commit()

def get_task_score(user_id, question):
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT best_score FROM tasks
            WHERE user_id = ? AND question = ?
        ''', (user_id, question))
        row = cursor.fetchone()
        return row[0] if row else 0.0

def update_task_score(user_id, question, new_score):
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE tasks SET best_score = ?
            WHERE user_id = ? AND question = ?
        ''', (new_score, user_id, question))
        conn.commit()

# Создаем таблицу заданий при запуске
create_tasks_table()

# --- Состояния FSM ---
class RegisterState(StatesGroup):
    name = State()
    age = State()

class TaskState(StatesGroup):
    waiting_for_answer = State()

# --- Команды и обработчики ---

# /start — регистрация
@router.message(lambda message: message.text == "/start")
async def cmd_start(message: types.Message, state: FSMContext):
    user = get_user_from_db(message.from_user.id)
    if user is None:
        # Новый пользователь: показываем логотип и приветственное сообщение
        await message.answer_photo(
            photo="https://i.imgur.com/zIPzQKF.jpeg",
            caption="Добро пожаловать в One to One IT Academy!"
        )
        await message.answer("👋 Давай знакомимся! Как тебя зовут?")
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
        await message.answer("Пожалуйста, введите возраст числом.")
        return
    data = await state.get_data()
    name = data.get("name")
    add_user_to_db(message.from_user.id, message.from_user.username, name, int(message.text))
    await message.answer(f"✅ Готово, {name}! Добро пожаловать!", reply_markup=get_main_menu())
    await state.clear()

@router.message(lambda msg: msg.text == "/ping")
async def cmd_ping(message: types.Message):
    await message.answer("🏓 Pong!")

# Профиль (без логотипа)
@router.callback_query(F.data == "profile")
async def profile_callback(callback: types.CallbackQuery):
    user = get_user_from_db(callback.from_user.id)
    if not user:
        await callback.message.edit_text("🚫 Пользователь не найден. Попробуйте /start.", reply_markup=get_main_menu())
        await callback.answer()
        return
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
    await callback.message.answer(text, parse_mode="HTML", reply_markup=get_main_menu())
    await callback.answer()

@router.callback_query(F.data == "help")
async def help_callback(callback: types.CallbackQuery):
    text = "ℹ️ Помощь:\n/start — начать\n📚 Получить задание — выбрать уровень и тему."
    await callback.message.edit_text(text, reply_markup=get_main_menu())
    await callback.answer()

@router.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: types.CallbackQuery):
    await profile_callback(callback)

# При выборе задания: сначала меню грейдов
@router.callback_query(F.data == "task")
async def task_callback(callback: types.CallbackQuery):
    await callback.message.edit_text("Выберите грейд для задания:", reply_markup=get_grades_menu())
    await callback.answer()

# Обработка выбора грейда – сохраняем выбранный грейд и показываем меню тем
@router.callback_query(F.data.startswith("grade_"))
async def grade_selection_callback(callback: types.CallbackQuery, state: FSMContext):
    selected_grade = callback.data.replace("grade_", "").strip()
    user = get_user_from_db(callback.from_user.id)
    if not user:
        await callback.message.answer("🚫 Пользователь не найден. Попробуйте /start", reply_markup=get_main_menu())
        await callback.answer()
        return
    current_grade = user[4]  # уровень из БД
    if LEVELS.index(selected_grade) != LEVELS.index(current_grade):
        await callback.message.answer(
            f"🚫 Доступ запрещён! Вам доступны задания только для уровня: {current_grade}.",
            reply_markup=get_main_menu()
        )
        await callback.answer()
        return
    # Сохраняем выбранный грейд в состоянии и показываем меню тем
    await state.update_data(selected_grade=selected_grade)
    await callback.message.edit_text("Выберите тему задания:", reply_markup=get_topics_menu())
    await callback.answer()

# Обработка выбора темы: callback data начинается с "topic_"
@router.callback_query(F.data.startswith("topic_"))
async def topic_selection_callback(callback: types.CallbackQuery, state: FSMContext):
    # Извлекаем тему
    topic = callback.data.replace("topic_", "").strip()
    # Получаем выбранный ранее грейд из состояния
    data = await state.get_data()
    selected_grade = data.get("selected_grade")
    if not selected_grade:
        await callback.message.answer("🚫 Ошибка: не выбран грейд. Попробуйте снова.", reply_markup=get_grades_menu())
        await callback.answer()
        return
    # Генерируем задание по выбранной теме
    question = await generate_question(selected_grade, topic)
    # Сохраняем задание в таблице tasks с best_score = 0.0
    add_task_for_user(callback.from_user.id, question)
    # Обновляем состояние для текущего задания
    await state.update_data(question=question, grade=selected_grade)
    await callback.message.edit_text(
        f"💬 Задание для уровня {selected_grade} по теме «{topic}»:\n\n{question}\n\n✍️ Напишите свой ответ сообщением."
    )
    await callback.answer()

# Кнопка "назад" в меню тем – возвращаемся в меню грейдов
@router.callback_query(F.data == "back_to_grades")
async def back_to_grades_callback(callback: types.CallbackQuery):
    await callback.message.edit_text("Выберите грейд для задания:", reply_markup=get_grades_menu())
    await callback.answer()

# Обработка ответа студента
@router.message(TaskState.waiting_for_answer)
async def handle_task_answer(message: types.Message, state: FSMContext):
    data = await state.get_data()
    if not data:
        await message.answer("⚠️ Не найдены данные задания. Попробуйте снова.")
        return
    grade = data.get("grade")
    question = data.get("question")
    if not question:
        await message.answer("⚠️ Ошибка: не найдено задание. Попробуйте получить новое.", reply_markup=get_main_menu())
        return
    user = get_user_from_db(message.from_user.id)
    if not user:
        await message.answer("🚫 Пользователь не найден. Повторите /start.")
        return
    student_name = user[2]

    feedback_raw = await evaluate_answer(question, message.text, student_name)
    logging.info(f"RAW FEEDBACK:\n{feedback_raw}")

    # Пытаемся извлечь критерии, Score и Feedback
    match = re.search(
        r"Критерии:\s*([\s\S]+?)Score:\s*([\d.]+)\s*[\r\n]+Feedback:\s*(.+)",
        feedback_raw
    )
    if match:
        criteria_block = match.group(1).strip()
        try:
            new_score = float(match.group(2))
        except ValueError:
            new_score = 0.0
        feedback_text = match.group(3).strip()
    else:
        criteria_block = ""
        new_score = 0.0
        feedback_text = feedback_raw.strip()

    # Получаем сохранённый лучший результат для данного задания из таблицы tasks
    current_best = get_task_score(message.from_user.id, question)
    diff = new_score - current_best
    if diff > 0:
        update_task_score(message.from_user.id, question, new_score)
        update_user_points(message.from_user.id, diff)
    # Формируем сообщение-результат
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔁 Попробовать снова", callback_data="retry"),
            InlineKeyboardButton(text="✅ Показать правильный ответ", callback_data="show_answer")
        ],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    result_msg = ""
    if criteria_block:
        result_msg += f"<b>Критерии:</b>\n{criteria_block}\n\n"
    result_msg += f"<b>Оценка (Score):</b> {new_score}\n\n"
    result_msg += f"<b>Обратная связь (Feedback):</b>\n{feedback_text}"
    if len(result_msg) > 4000:
        for i in range(0, len(result_msg), 4000):
            await message.answer(result_msg[i:i+4000], parse_mode="HTML", reply_markup=keyboard)
    else:
        await message.answer(result_msg, parse_mode="HTML", reply_markup=keyboard)
    await state.update_data(last_question=question, last_grade=grade)

@router.callback_query(F.data == "show_answer")
async def show_correct_answer(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    question = data.get("last_question")
    grade = data.get("last_grade")
    if not question or not grade:
        await callback.message.answer("⚠️ Ошибка: не найден вопрос для показа ответа.", reply_markup=get_main_menu())
        await callback.answer()
        return
    correct = await generate_correct_answer(question, grade)
    await callback.message.answer(
        f"✅ Эталонный ответ уровня {grade}:\n\n{correct}",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )
    await callback.answer()

@router.callback_query(F.data == "retry")
async def retry_question(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    question = data.get("last_question")
    grade = data.get("last_grade")
    if not question or not grade:
        await callback.message.answer("⚠️ Ошибка: нет сохранённого задания.", reply_markup=get_main_menu())
        await callback.answer()
        return
    await state.set_state(TaskState.waiting_for_answer)
    await state.update_data(question=question, grade=grade)
    await callback.message.answer(f"✍️ Повторите, пожалуйста, ответ на вопрос уровня {grade}:\n\n{question}")
    await callback.answer()

# --- OpenAI функции ---

async def generate_question(grade: str, topic: str) -> str:
    """
    Генерирует краткий, ёмкий вопрос для продакт-менеджера уровня {grade} по теме {topic}.
    Вопрос должен быть не длиннее 350 символов и включать только ключевые аспекты.
    """
    prompt = (
        f"Ты опытный продакт-менеджер. Сформулируй короткий и точный вопрос для продакт-менеджера уровня {grade} "
        f"по теме «{topic}». Вопрос должен быть не длиннее 350 символов, содержать только самое важное и быть понятным."
    )
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты генерируешь краткие и ёмкие вопросы для продакт-менеджеров. Не используй лишние детали и звездочки, используй эмодзи для выделения, если необходимо."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=150,
            temperature=0.6
        )
        question_text = response.choices[0].message.content.strip()
        # Если вдруг вопрос окажется слишком длинным, обрезаем до 350 символов
        if len(question_text) > 350:
            question_text = question_text[:347] + "..."
        return question_text
    except Exception as e:
        logging.error(f"Ошибка генерации вопроса: {e}")
        return "❌ Ошибка генерации вопроса."

async def evaluate_answer(question: str, student_answer: str, student_name: str) -> str:
    prompt = (
        f"Вопрос: {question}\n"
        f"Ответ студента: {student_answer}\n\n"
        "Анализируй ответ по 5 критериям:\n"
        "1. Соответствие вопросу\n"
        "2. Полнота\n"
        "3. Аргументация\n"
        "4. Структура\n"
        "5. Примеры\n\n"
        "Для каждого критерия выбери один из вариантов: ✅, ⚠️ или ❌.\n"
        "Определи итоговую оценку (Score) от 0.0 до 1.0. Если ответ частично верный, используй дробное число (например, 0.5).\n\n"
        "Выведи результат строго в формате:\n\n"
        "Критерии:\n"
        "🔹 Соответствие вопросу: <эмоджи>\n"
        "🔹 Полнота: <эмоджи>\n"
        "🔹 Аргументация: <эмоджи>\n"
        "🔹 Структура: <эмоджи>\n"
        "🔹 Примеры: <эмоджи>\n\n"
        "Score: <число>\n"
        "Feedback: Ваш ответ... (обратись к студенту от первого лица)\n"
    )
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": (
                    "Ты преподаватель, строго оценивающий ответы студентов по заданному шаблону. Не добавляй лишних слов."
                )},
                {"role": "user", "content": prompt}
            ],
            max_tokens=450,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Ошибка оценки ответа: {e}")
        return "❌ Ошибка оценки ответа."

async def generate_correct_answer(question: str, grade: str) -> str:
    prompt = (
        f"Ты опытный преподаватель продакт-менеджмента. Дай подробный правильный ответ на вопрос для уровня {grade}.\n\n"
        f"Вопрос: {question}\n\n"
        "Объясни ключевые моменты и приведи примеры, почему ответ правильный. "
        "Отвечай от первого лица, обращаясь к студенту как 'Ваш ответ...'. "
        "Не используй символ * – вместо него эмодзи или обычный текст."
    )
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты генерируешь подробные правильные ответы для студентов. Не используй символ *."},
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
