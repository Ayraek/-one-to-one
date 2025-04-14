import os
import re
import logging
import asyncpg
from urllib.parse import urlparse
import asyncio
from dotenv import load_dotenv

from openai import OpenAI

from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import StatesGroup, State

########################
# Загрузка переменных окружения
########################

load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
# Добавьте в Railway переменную ADMIN_IDS, например "12345678,87654321"
ADMIN_IDS = os.getenv("ADMIN_IDS", "")
admin_ids = [int(x.strip()) for x in ADMIN_IDS.split(",")] if ADMIN_IDS else []
# Подключение к PostgreSQL
db_pool = None

async def create_db_pool():
    global db_pool
    url = os.getenv("DATABASE_URL")
    parsed = urlparse(url)
    db_pool = await asyncpg.create_pool(
        user=parsed.username,
        password=parsed.password,
        database=parsed.path.lstrip("/"),
        host=parsed.hostname,
        port=parsed.port or 5432
    )

    # Автоматически создаём таблицу users при старте
    async with db_pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username TEXT,
                name TEXT,
                age INTEGER,
                level TEXT,
                points REAL
            )
        ''')


########################
# Настройка OpenAI клиента
########################

client = OpenAI(api_key=OPENAI_API_KEY)

########################
# Настройка логирования
########################

logging.basicConfig(level=logging.INFO)

########################
# Инициализация бота/диспетчера
########################

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

########################
# Глобальные переменные
########################

LEVELS = ["Junior", "Middle", "Senior", "Head of Product", "CPO", "CEO"]

welcome_text = (
    "💡 Добро пожаловать в \"One to One Booster bot\" — вашего личного ассистента для прокачки навыков в продакт-менеджменте!"
)

# Темы для заданий
TOPICS = [
    "Гипотезы",
    "Маркетинг",
    "Метрики",
    "Управление командой",
    "Soft skills",
    "Стратегия",
    "Требования к продукту"
]

########################
# Функции формирования меню
########################

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="📚 Получить задание", callback_data="task")],
        [InlineKeyboardButton(text="📝 Экзамен", callback_data="exam")],
        [InlineKeyboardButton(text="📰 Новости", callback_data="news")]
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
    buttons = []
    for topic in TOPICS:
        buttons.append([InlineKeyboardButton(text=topic, callback_data=f"topic_{topic}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="choose_grade")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_exam_menu():
    keyboard = [[InlineKeyboardButton(text="Вернуться в главное меню", callback_data="main_menu")]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_news_menu():
    keyboard = [[InlineKeyboardButton(text="Вернуться в главное меню", callback_data="main_menu")]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_show_answer_menu():
    """Формирует меню для показа эталонного ответа с двумя кнопками."""
    keyboard = [
        [InlineKeyboardButton(text="➡️ Следующий вопрос", callback_data="next_question")],
        [InlineKeyboardButton(text="🏠 Вернуться в главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)
@router.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    user = await get_user_from_db(callback.from_user.id)
    if user:
        username = user["username"]
        name = user["name"]
        age = user["age"]
        level = user["level"]
        points = user["points"]
        text = (
            f"<b>👤 Имя:</b> {name}\n"
            f"<b>🎂 Возраст:</b> {age}\n"
            f"<b>🎯 Уровень:</b> {level}\n"
            f"<b>⭐ Баллы:</b> {points}\n"
        )
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_main_menu())
    else:
        await callback.message.edit_text(welcome_text, reply_markup=get_main_menu())
    await callback.answer()

########################
# Функции работы с базой данных
########################

async def add_user_to_db(user_id: int, username: str, name: str, age: int):
    async with db_pool.acquire() as conn:
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id BIGINT PRIMARY KEY,
                username TEXT,
                name TEXT,
                age INTEGER,
                level TEXT,
                points REAL
            )
        ''')
        await conn.execute('''
            INSERT INTO users (id, username, name, age, level, points)
            VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (id) DO NOTHING
        ''', user_id, username, name, age, "Junior", 0.0)

async def get_user_from_db(user_id: int):
    async with db_pool.acquire() as conn:
        return await conn.fetchrow('SELECT * FROM users WHERE id = $1', user_id)

async def update_user_points(user_id: int, additional_points: float):
    async with db_pool.acquire() as conn:
        await conn.execute(
            'UPDATE users SET points = points + $1 WHERE id = $2',
            additional_points, user_id
        )

async def update_level(user_id: int):
    user = await get_user_from_db(user_id)
    if not user:
        return
    current_level = user["level"]
    points = user["points"]
    cur_index = LEVELS.index(current_level)
    required_points = 50 * (cur_index + 1)
    if points >= required_points and cur_index < len(LEVELS) - 1:
        new_level = LEVELS[cur_index + 1]
        async with db_pool.acquire() as conn:
            await conn.execute(
                'UPDATE users SET level = $1 WHERE id = $2',
                new_level, user_id
            )
        logging.info(f"Пользователь {user_id} повышен с {current_level} до {new_level}.")

########################
# Состояния
########################

class RegisterState(StatesGroup):
    name = State()
    age = State()

class TaskState(StatesGroup):
    waiting_for_answer = State()

########################
# Основные команды и обработчики
########################

@router.message(lambda msg: msg.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    user = await get_user_from_db(message.from_user.id)
    if user is None:
        # Новый пользователь: показываем логотип и начинаем регистрацию
        await message.answer_photo(
            photo="https://i.imgur.com/zIPzQKF.jpeg",
            caption="Добро пожаловать в One to One IT Academy!"
        )
        await message.answer("👋 Как тебя зовут?")
        await state.set_state(RegisterState.name)
    else:
        # Зарегистрированному сразу показываем приветствие и главное меню
        username, name, age, level, points = user["username"], user["name"], user["age"], user["level"], user["points"]
        await message.answer(f"👋 Привет, {name}!\n{welcome_text}", reply_markup=get_main_menu())

@router.message(RegisterState.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Сколько тебе лет?")
    await state.set_state(RegisterState.age)

@router.message(RegisterState.age)
async def process_age(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите возраст цифрами.")
        return
    data = await state.get_data()
    name = data.get("name")
    await add_user_to_db(message.from_user.id, message.from_user.username or "", name, int(message.text))
    await message.answer(f"✅ Готово, {name}! Добро пожаловать!", reply_markup=get_main_menu())
    await state.clear()

@router.message(lambda msg: msg.text == "/ping")
async def cmd_ping(message: Message):
    await message.answer("🏓 Pong!")

########################
# Админка
########################

@router.message(lambda message: message.text == "/admin")
async def admin_panel(message: Message, state: FSMContext):
    if message.from_user.id not in admin_ids:
        await message.answer("🚫 У вас нет прав администратора.")
        return
    await message.answer("👑 Добро пожаловать в админ-панель.", reply_markup=get_admin_menu())

def get_admin_menu():
    keyboard = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💬 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@router.callback_query(F.data == "admin_stats")
async def admin_stats_handler(callback: CallbackQuery):
    try:
        async with db_pool.acquire() as conn:
            row = await conn.fetchrow("SELECT COUNT(*) FROM users")
            count = row[0]
    except Exception as e:
        logging.error(f"Ошибка получения статистики: {e}")
        count = "не удалось получить статистику"
    
    text = f"📊 Статистика:\nОбщее количество пользователей: {count}"
    await callback.message.edit_text(text, reply_markup=get_admin_menu())
    await callback.answer()

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Функция рассылки скоро будет доступна.", reply_markup=get_admin_menu())
    await callback.answer()

@router.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    user = await get_user_from_db(callback.from_user.id)
    if user:
        username, name, age, level, points = user["username"], user["name"], user["age"], user["level"], user["points"]
        text = (
            f"<b>👤 Имя:</b> {name}\n"
            f"<b>🎂 Возраст:</b> {age}\n"
            f"<b>🎯 Уровень:</b> {level}\n"
            f"<b>⭐ Баллы:</b> {points}\n"
        )
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_main_menu())
    else:
        await callback.message.edit_text(welcome_text, reply_markup=get_main_menu())
    await callback.answer()

########################
# Обработка разделов "Новости" и "Экзамен"
########################

@router.callback_query(F.data == "news")
async def news_callback(callback: CallbackQuery):
    text = (
        "📰 Новости:\n\n"
        "Бот сейчас умеет генерировать задания по продакт-менеджменту, оценивать ответы и выдавать фидбэк.\n\n"
        "В ближайшее время ожидается:\n"
        "• Раздел экзамен по каждому грейду\n"
        "• Выгрузка файла со слабыми местами\n"
        "• Анализ знаний и исследование уровня зарплат по рынку\n"
        "• Улучшенный рейтинг пользователей\n"
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_news_menu())
    await callback.answer()

def get_news_menu():
    keyboard = [[InlineKeyboardButton(text="Вернуться в главное меню", callback_data="main_menu")]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

@router.callback_query(F.data == "exam")
async def exam_callback(callback: CallbackQuery):
    text = (
        "📝 Раздел Экзамен появится в ближайшее время.\n\n"
        "Следите за обновлениями и нажмите кнопку ниже, чтобы вернуться в главное меню."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_exam_menu())
    await callback.answer()

def get_exam_menu():
    keyboard = [[InlineKeyboardButton(text="Вернуться в главное меню", callback_data="main_menu")]]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

########################
# Получение задания: выбор грейда и темы
########################

@router.callback_query(F.data == "task")
async def task_callback(callback: CallbackQuery):
    await callback.message.edit_text("Выберите грейд, для которого хотите получить задание:", reply_markup=get_grades_menu())
    await callback.answer()

@router.callback_query(F.data.startswith("grade_"))
async def handle_grade_selection(callback: CallbackQuery, state: FSMContext):
    selected_grade = callback.data.replace("grade_", "").strip()
    user = await get_user_from_db(callback.from_user.id)
    if not user:
        await callback.message.answer("🚫 Пользователь не найден. Попробуйте /start", reply_markup=get_main_menu())
        await callback.answer()
        return
    current_level = user["level"]
    if selected_grade != current_level:
        await callback.message.answer(
            f"🚫 Доступ запрещён! Ваш текущий уровень: {current_level}.",
            reply_markup=get_main_menu()
        )
        await callback.answer()
        return
    await state.update_data(selected_grade=selected_grade)
    await callback.message.edit_text("Выберите тему для задания:", reply_markup=get_topics_menu())
    await callback.answer()

@router.callback_query(F.data == "choose_grade")
async def back_to_grades(callback: CallbackQuery):
    await callback.message.edit_text("Выберите грейд, для которого хотите получить задание:", reply_markup=get_grades_menu())
    await callback.answer()

@router.callback_query(F.data.startswith("topic_"))
async def handle_topic_selection(callback: CallbackQuery, state: FSMContext):
    chosen_topic = callback.data.replace("topic_", "").strip()
    data = await state.get_data()
    selected_grade = data.get("selected_grade")
    if not selected_grade:
        await callback.message.answer("⚠️ Ошибка: не найден грейд. Попробуйте выбрать заново.", reply_markup=get_grades_menu())
        await callback.answer()
        return
    question = await generate_question(selected_grade, chosen_topic)
    await state.set_state(TaskState.waiting_for_answer)
    await state.update_data(question=question, grade=selected_grade, last_score=0.0)
    await callback.message.edit_text(
        f"💬 Задание для уровня {selected_grade} по теме «{chosen_topic}»:\n\n"
        f"{question}\n\n"
        "✍️ Напишите свой ответ сообщением."
    )
    await callback.answer()

########################
# Обработка ответа пользователя
########################

@router.message(TaskState.waiting_for_answer)
async def handle_task_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data:
        await message.answer("⚠️ Не найдены данные задания. Попробуйте снова.")
        return
    grade = data.get("grade")
    question = data.get("question")
    last_score = data.get("last_score", 0.0)
    user = await get_user_from_db(message.from_user.id)
    if not user:
        await message.answer("🚫 Пользователь не найден. Повторите /start.")
        return
    student_name = user["name"]
    feedback_raw = await evaluate_answer(question, message.text, student_name)
    logging.info(f"RAW FEEDBACK:\n{feedback_raw}")
    pattern = r"Критерии:\s*(.*?)Score:\s*([\d.]+)\s*Feedback:\s*(.*)"
    match = re.search(pattern, feedback_raw, re.DOTALL)
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
    if new_score > last_score:
        diff = new_score - last_score
        await update_user_points(message.from_user.id, diff)
        await update_level(message.from_user.id)
        await state.update_data(last_score=new_score)
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔁 Попробовать снова", callback_data="retry"),
         InlineKeyboardButton(text="✅ Показать правильный ответ", callback_data="show_answer")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    result_msg = ""
    if criteria_block:
        result_msg += f"<b>Критерии:</b>\n{criteria_block}\n\n"
    result_msg += f"<b>Оценка (Score):</b> {new_score}\n\n"
    result_msg += f"<b>Обратная связь (Feedback):</b>\n{feedback_text}"
    if len(result_msg) > 4000:
        chunks = [result_msg[i:i+4000] for i in range(0, len(result_msg), 4000)]
        for i, chunk in enumerate(chunks):
            if i == len(chunks) - 1:
                await message.answer(chunk, parse_mode="HTML", reply_markup=keyboard)
            else:
                await message.answer(chunk, parse_mode="HTML")
    else:
        await message.answer(result_msg, parse_mode="HTML", reply_markup=keyboard)
    await state.update_data(last_question=question, last_grade=grade)

########################
# Обработка кнопки "Показать правильный ответ"
########################

@router.callback_query(F.data == "show_answer")
async def show_correct_answer(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    question = data.get("last_question")
    grade = data.get("last_grade")
    if not question or not grade:
        await callback.message.answer("⚠️ Ошибка: не найден вопрос для показа ответа.", reply_markup=get_main_menu())
        await callback.answer()
        return
    correct = await generate_correct_answer(question, grade)
    # Используем обновлённое меню с кнопками "Следующий вопрос" и "Вернуться в главное меню"
    await callback.message.answer(
        f"✅ Эталонный ответ уровня {grade}:\n\n{correct}",
        parse_mode="HTML",
        reply_markup=get_show_answer_menu()
    )
    await callback.answer()

# Обработчик кнопки "Следующий вопрос"
@router.callback_query(F.data == "next_question")
async def next_question_handler(callback: CallbackQuery, state: FSMContext):
    # Очищаем состояние, переходим к выбору задания (грейда)
    await state.clear()
    await callback.message.edit_text("Выберите грейд, для которого хотите получить задание:", reply_markup=get_grades_menu())
    await callback.answer()

# Обработчик кнопки "Попробовать снова" (retry)
@router.callback_query(F.data.startswith("topic_"))
async def handle_topic_selection(callback: CallbackQuery, state: FSMContext):
    chosen_topic = callback.data.replace("topic_", "").strip()
    data = await state.get_data()
    selected_grade = data.get("selected_grade")
    if not selected_grade:
        await callback.message.answer("⚠️ Ошибка: не найден грейд. Попробуйте выбрать заново.", reply_markup=get_grades_menu())
        await callback.answer()
        return

    user = await get_user_from_db(callback.from_user.id)
    name = user["name"] if user else "кандидат"
    question = await generate_question(selected_grade, chosen_topic, name)

    await state.set_state(TaskState.waiting_for_answer)
    await state.update_data(question=question, grade=selected_grade, last_score=0.0)
    await callback.message.edit_text(
        f"💬 Задание для уровня {selected_grade} по теме «{chosen_topic}»:\n\n"
        f"{question}\n\n"
        "✍️ Напишите свой ответ сообщением."
    )
    await callback.answer()

########################
# Функции для работы с OpenAI
########################

async def generate_question(grade: str, topic: str, name: str) -> str:
    """
    Генерирует прикладной, реалистичный вопрос с цифрами, обращением по имени и контекстом.
    """
    prompt = (
        f"Ты — опытный интервьюер по найму продакт-менеджеров в топовых ИТ-компаниях России "
        f"(Яндекс, VK, Ozon, Тинькофф, Сбер). Сейчас ты проводишь онлайн-собеседование с кандидатом по имени {name}.\n\n"
        f"Позиция: Product Manager уровня {grade} в B2C-компании. Тема собеседования: {topic}.\n\n"
        f"Сформулируй один прикладной вопрос, основанный на кейсе, с цифрами, контекстом и задачей. "
        f"Формат — реалистичный, не сухой. Как будто ты прямо сейчас задаёшь вопрос в Zoom.\n\n"
        f"💬 Пример:\n"
        f"«{name}, в продукте Х мы видим рост churn на 30% и падение Retention D7 с 40% до 25%. Как бы ты подошёл к этой ситуации?»\n\n"
        f"📌 Требования:\n"
        f"- Обратись к кандидату по имени: {name}\n"
        f"- Не пиши слово 'Вопрос:'\n"
        f"- Не давай пояснений, только сам вопрос\n"
        f"- Можно использовать эмодзи (если уместно)\n"
        f"- Без Markdown и *звёздочек*\n"
    )

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты живой и вежливый интервьюер, собеседуешь кандидата на продакт-менеджера. Задаёшь вопросы с цифрами, с обращением по имени, прикладно и по делу."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.8
        )
        question_text = response.choices[0].message.content.strip()
        if len(question_text) > 800:
            question_text = question_text[:797] + "..."
        return question_text
    except Exception as e:
        logging.error(f"Ошибка генерации вопроса: {e}")
        return "❌ Ошибка генерации вопроса."

async def evaluate_answer(question: str, student_answer: str, student_name: str) -> str:
    prompt = (
        f"Вопрос: {question}\n"
        f"Ответ студента: {student_answer}\n\n"
        "Проанализируй ответ по 5 критериям:\n"
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
                {"role": "system", "content": "Ты преподаватель, строго оценивающий ответы по заданному шаблону. Не добавляй лишних слов."},
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
        "Не используй звездочки (*)."
    )
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты генерируешь подробные правильные ответы для студентов. Не используй звездочки."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Ошибка генерации эталонного ответа: {e}")
        return "❌ Ошибка генерации эталонного ответа."

########################
# Запуск бота
########################

async def on_startup():
    await create_db_pool()
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(on_startup())
