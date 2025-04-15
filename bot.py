import os
import re
import logging
import asyncpg
import asyncio
from urllib.parse import urlparse

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import StatesGroup, State
from inactivity_middleware import InactivityMiddleware

# --------------------------
# Загрузка переменных окружения
# --------------------------

API_TOKEN = os.getenv("API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_IDS = os.getenv("ADMIN_IDS", "")
admin_ids = [int(x.strip()) for x in ADMIN_IDS.split(",")] if ADMIN_IDS else []

# --------------------------
# Инициализация бота и диспетчера
# --------------------------

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)
# Подключаем middleware для очистки истории (15 минут бездействия)
dp.message.middleware(InactivityMiddleware(timeout_seconds=900))
dp.callback_query.middleware(InactivityMiddleware(timeout_seconds=900))

# --------------------------
# Настройка OpenAI клиента и логирование
# --------------------------

client = OpenAI(api_key=OPENAI_API_KEY)
logging.basicConfig(level=logging.INFO)

# --------------------------
# Глобальные переменные
# --------------------------

LEVELS = ["Junior", "Middle", "Senior", "Head of Product", "CPO", "CEO"]

welcome_text = (
    "💡 Добро пожаловать в \"One to One Booster bot\" — вашего личного ассистента для прокачки навыков в продакт-менеджменте!"
)

TOPICS = [
    "Гипотезы",
    "Маркетинг",
    "Метрики",
    "Управление командой",
    "Soft skills",
    "Стратегия",
    "Требования к продукту"
]

# --------------------------
# Функции формирования меню
# --------------------------

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
    keyboard = [
        [InlineKeyboardButton(text="➡️ Следующий вопрос", callback_data="next_question")],
        [InlineKeyboardButton(text="🏠 Вернуться в главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_admin_menu():
    keyboard = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💬 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# --------------------------
# Состояния
# --------------------------

class RegisterState(StatesGroup):
    name = State()
    age = State()

class TaskState(StatesGroup):
    waiting_for_answer = State()
    waiting_for_clarification = State()
    waiting_for_voice = State()  # новое состояние для голосового ответа
# --------------------------
# Подключение к PostgreSQL
# --------------------------

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

# --------------------------
# Функции работы с базой данных
# --------------------------

async def add_user_to_db(user_id: int, username: str, name: str, age: int):
    async with db_pool.acquire() as conn:
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

# --------------------------
# Обработчики коллбэков и команд
# --------------------------

@router.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    user = await get_user_from_db(callback.from_user.id)
    if user:
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

@router.callback_query(F.data == "start_answering")
async def start_answering(callback: CallbackQuery):
    await callback.message.answer(
        "✏️ Напишите свой ответ сообщением.",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await callback.answer()

@router.message(lambda msg: msg.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    # Получаем данные состояния (если есть сохранённый список bot_messages)
    data = await state.get_data()
    bot_messages = data.get("bot_messages", [])
    
    # Пытаемся удалить каждое бот-сообщение из списка
    for msg_id in bot_messages:
        try:
            await bot.delete_message(chat_id=message.chat.id, message_id=msg_id)
        except Exception as e:
            logging.warning(f"Не удалось удалить сообщение {msg_id}: {e}")
    
    # Очищаем состояние полностью и инициализируем пустой список для bot_messages
    await state.clear()
    await state.update_data(bot_messages=[])
    
    # Отправляем «чистый экран» – одно сообщение с кнопкой "Начать обучение"
    start_keyboard = types.ReplyKeyboardMarkup(
        keyboard=[[types.KeyboardButton(text="Начать обучение")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer("Нажмите «Начать обучение», чтобы начать.", reply_markup=start_keyboard)

# Отдельный обработчик для кнопки "Начать обучение"
@router.message(lambda msg: msg.text == "Начать обучение")
async def start_training(message: Message, state: FSMContext):
    await state.clear()
    await state.update_data(bot_messages=[])
    user = await get_user_from_db(message.from_user.id)
    if user:
        await message.answer("Добро пожаловать! Выберите, что хотите сделать.", reply_markup=get_main_menu())
    else:
        await message.answer_photo(
            photo="https://i.imgur.com/zIPzQKF.jpeg",
            caption="Добро пожаловать в One to One IT Academy!"
        )
        await message.answer("👋 Как тебя зовут?")
        await state.set_state(RegisterState.name)

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

# --------------------------
# Админка
# --------------------------

@router.message(lambda message: message.text == "/admin")
async def admin_panel(message: Message, state: FSMContext):
    if message.from_user.id not in admin_ids:
        await message.answer("🚫 У вас нет прав администратора.")
        return
    await message.answer("👑 Добро пожаловать в админ-панель.", reply_markup=get_admin_menu())

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

@router.callback_query(F.data == "exam")
async def exam_callback(callback: CallbackQuery):
    text = (
        "📝 Раздел Экзамен появится в ближайшее время.\n\n"
        "Следите за обновлениями и нажмите кнопку ниже, чтобы вернуться в главное меню."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_exam_menu())
    await callback.answer()

# --------------------------
# Получение задания: выбор грейда и темы
# --------------------------

@router.callback_query(F.data == "task")
async def task_callback(callback: CallbackQuery):
    await callback.message.edit_text("Выберите грейд, для которого хотите получить задание:", reply_markup=get_grades_menu())
    await callback.answer()

@router.callback_query(F.data == "choose_grade")
async def back_to_grades(callback: CallbackQuery):
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

@router.callback_query(F.data.startswith("topic_"))
async def handle_topic_selection(callback: CallbackQuery, state: FSMContext):
    chosen_topic = callback.data.replace("topic_", "").strip()
    data = await state.get_data()
    selected_grade = data.get("selected_grade")
    user = await get_user_from_db(callback.from_user.id)

    if not selected_grade or not user:
        await callback.message.answer("⚠️ Ошибка: не найдены грейд или пользователь. Попробуйте выбрать заново.", reply_markup=get_grades_menu())
        await callback.answer()
        return

    question = await generate_question(selected_grade, chosen_topic, user["name"])
    if not question or "Ошибка" in question:
        await callback.message.answer(
            "❌ Не удалось сгенерировать вопрос. Попробуйте позже или выберите другую тему.",
            reply_markup=get_main_menu()
        )
        await state.clear()
        await callback.answer()
        return

    await state.set_state(TaskState.waiting_for_answer)
    await state.update_data(question=question, grade=selected_grade, selected_topic=chosen_topic, last_score=0.0)

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✍️ Ответить текстом"), KeyboardButton(text="🎤 Ответить голосом")],
            [KeyboardButton(text="❓ Уточнить по вопросу")],
            [KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await callback.message.answer(
        f"💬 Задание для уровня {selected_grade} по теме «{chosen_topic}»:\n\n{question}\n\nЧто хотите сделать?",
        reply_markup=keyboard
    )
    await callback.answer()

# --------------------------
# Поведение при уточнении
# --------------------------

@router.callback_query(F.data == "clarify_info")
async def clarify_info_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TaskState.waiting_for_clarification)
    await callback.message.answer("✏️ Напишите, что именно хотите уточнить по заданию:", reply_markup=types.ReplyKeyboardRemove())
    await callback.answer()

@router.message(TaskState.waiting_for_clarification)
async def process_clarification(message: Message, state: FSMContext):
    data = await state.get_data()
    question = data.get("question")
    user = await get_user_from_db(message.from_user.id)
    name = user["name"] if user else "кандидат"
    clarification_prompt = (
        f"Вопрос: {question}\n"
        f"Уточнение от кандидата {name}:\n{message.text.strip()}\n\n"
        "Ответ должен быть кратким, конкретным и направляющим. Если уточнение звучит как 'Мне описать все инструменты или только один?', "
        "то ответ: 'Чем больше инструментов вы опишете, тем лучше. Приведите примеры и раскройте каждый по отдельности'. "
        "Если уточнение звучит как 'Дай мне пример конкретного продукта', то ответ: 'Возьмите для примера продукт X, он отлично подходит для этого задания'. "
        "Если уточнение не по теме, напомните: 'Пожалуйста, спрашивайте только в рамках данного задания'. "
        "Дайте ответ строго по теме вопроса, без лишних вступлений."
    )
    try:
        clarification_response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты проводишь собеседование по продакт-менеджменту. Отвечай кратко, по сути и только по теме, без приветствий."
                    )
                },
                {"role": "user", "content": clarification_prompt}
            ],
            max_tokens=150,
            temperature=0.3
        )
        reply = clarification_response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Ошибка при уточнении: {e}")
        reply = "❌ Не удалось получить ответ на уточнение. Попробуйте снова."
    reply_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✍️ Ответить")],
            [KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer(f"📎 Уточнение:\n{reply}\n\nЧто делаем дальше?", reply_markup=reply_keyboard)
    await state.set_state(TaskState.waiting_for_answer)

# --------------------------
# Общий обработчик для TaskState.waiting_for_answer
# --------------------------

@router.message(TaskState.waiting_for_answer)
async def handle_task_answer(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state != TaskState.waiting_for_answer.state:
        await message.answer(
            "⚠️ Сейчас нет активного задания. Сначала получите задание и тему.",
            reply_markup=get_main_menu()
        )
        await state.clear()
        return

    text = message.text.strip()
    logging.info(f"[DEBUG] Received text: {repr(text)}")
    data = await state.get_data()

    if text == "✍️ Ответить":
        await message.answer("✏️ Напишите, пожалуйста, свой ответ.", reply_markup=types.ReplyKeyboardRemove())
        return
    # ✍️ Ответить текстом
    if text == "✍️ Ответить текстом":
        logging.info("[DEBUG] Пользователь выбрал '✍️ Ответить текстом'")
        await message.answer("✏️ Напишите, пожалуйста, свой ответ.", reply_markup=types.ReplyKeyboardRemove())
        return

    # 🎤 Ответить голосом
    if text == "🎤 Ответить голосом":
        logging.info("[DEBUG] Пользователь выбрал '🎤 Ответить голосом'")
        await state.set_state(TaskState.waiting_for_voice)
        await message.answer("🎤 Пожалуйста, отправьте голосовое сообщение с вашим ответом.", reply_markup=types.ReplyKeyboardRemove())
        return

    # ❓ Уточнить
    if text == "❓ Уточнить":
        logging.info("[DEBUG] Пользователь нажал '❓ Уточнить'")
        await state.set_state(TaskState.waiting_for_clarification)
        await message.answer("✏️ Напишите, что именно хотите уточнить по заданию:", reply_markup=types.ReplyKeyboardRemove())
        return

    # 🏠 Главное меню
    if text == "🏠 Главное меню":
        logging.info("[DEBUG] Пользователь нажал '🏠 Главное меню'")
        user = await get_user_from_db(message.from_user.id)
        if user:
            profile_text = (
                f"<b>👤 Имя:</b> {user['name']}\n"
                f"<b>🎂 Возраст:</b> {user['age']}\n"
                f"<b>🎯 Уровень:</b> {user['level']}\n"
                f"<b>⭐ Баллы:</b> {user['points']}\n\n"
                "Вы в главном меню:"
            )
        else:
            profile_text = "Пользователь не найден. Вы в главном меню."
        await message.answer(profile_text, parse_mode="HTML", reply_markup=get_main_menu())
        await state.clear()
        return

    # ✅ Показать правильный ответ
    if text == "✅ Показать правильный ответ":
        logging.info("[DEBUG] Пользователь нажал '✅ Показать правильный ответ'")
        last_question = data.get("last_question")
        last_grade = data.get("last_grade")

        if not last_question or not last_grade:
            await message.answer(
                "⚠️ Сейчас нет активного задания, для которого можно показать правильный ответ. "
                "Сначала пройдите задание.",
                reply_markup=get_main_menu()
            )
            await state.clear()
            return

        correct_answer = await generate_correct_answer(last_question, last_grade)
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="➡️ Следующий вопрос")],
                [KeyboardButton(text="🏠 Главное меню")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.answer(f"✅ Эталонный ответ уровня {last_grade}:\n\n{correct_answer}", parse_mode="HTML", reply_markup=kb)
        return

    # ➡️ Следующий вопрос
    if text == "➡️ Следующий вопрос":
        logging.info("[DEBUG] Пользователь нажал '➡️ Следующий вопрос'")
        grade = data.get("grade")
        topic = data.get("selected_topic")
        if not grade or not topic:
            await message.answer("⚠️ Ошибка: не найдены нужные данные.")
            return
        user = await get_user_from_db(message.from_user.id)
        if not user:
            await message.answer("⚠️ Пользователь не найден.")
            return
        name = user["name"]
        new_question = await generate_question(grade, topic, name)
        logging.info(f"[DEBUG] Сгенерирован новый вопрос: {new_question}")
        await state.update_data(question=new_question, last_score=0)
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✍️ Ответить текстом"), KeyboardButton(text="🎤 Ответить голосом")],
                [KeyboardButton(text="❓ Уточнить"), KeyboardButton(text="🏠 Главное меню")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.answer(f"Новый вопрос для уровня {grade} по теме «{topic}»:\n\n{new_question}", reply_markup=kb)
        return

    # 📝 Обработка текстового ответа
    grade = data.get("grade")
    question = data.get("question")
    last_score = data.get("last_score", 0.0)
    if not grade or not question:
        await message.answer("⚠️ Не найдены данные задания. Попробуйте снова.")
        return

    user = await get_user_from_db(message.from_user.id)
    if not user:
        await message.answer("⚠️ Пользователь не найден.")
        return

    student_name = user["name"]
    logging.info(f"[DEBUG] Оцениваем ответ для вопроса: {repr(question)} пользователя: {student_name}")
    feedback_raw = await evaluate_answer(question, message.text, student_name)
    logging.info(f"[DEBUG] RAW FEEDBACK:\n{feedback_raw}")

    if not feedback_raw or "Ошибка" in feedback_raw:
        await message.answer(
            "❌ Произошла ошибка при оценке ответа. Попробуйте снова или вернитесь в главное меню.",
            reply_markup=get_main_menu()
        )
        await state.clear()
        return

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

    result_msg = ""
    if criteria_block:
        result_msg += f"<b>Критерии:</b>\n{criteria_block}\n\n"
    result_msg += f"<b>Оценка (Score):</b> {new_score}\n\n"
    result_msg += f"<b>Обратная связь (Feedback):</b>\n{feedback_text}"

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➡️ Следующий вопрос")],
            [KeyboardButton(text="✅ Показать правильный ответ")],
            [KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await message.answer(result_msg, parse_mode="HTML", reply_markup=kb)
    await state.update_data(last_question=question, last_grade=grade)

@router.message(TaskState.waiting_for_voice)
async def process_voice_message(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""

    # --- Главное меню ---
    if text == "🏠 Главное меню":
        logging.info("[DEBUG] Пользователь нажал '🏠 Главное меню' в голосовом режиме")
        user = await get_user_from_db(message.from_user.id)
        if user:
            profile_text = (
                f"<b>👤 Имя:</b> {user['name']}\n"
                f"<b>🎂 Возраст:</b> {user['age']}\n"
                f"<b>🎯 Уровень:</b> {user['level']}\n"
                f"<b>⭐ Баллы:</b> {user['points']}\n\n"
                "Вы в главном меню:"
            )
        else:
            profile_text = "Пользователь не найден. Вы в главном меню."
        await message.answer(profile_text, parse_mode="HTML", reply_markup=get_main_menu())
        await state.clear()
        return

    # --- Следующий вопрос ---
    if text == "➡️ Следующий вопрос":
        logging.info("[DEBUG] Пользователь нажал '➡️ Следующий вопрос' в голосовом режиме")
        data = await state.get_data()
        grade = data.get("grade")
        topic = data.get("selected_topic")
        if not grade or not topic:
            await message.answer("⚠️ Ошибка: не найдены нужные данные.", reply_markup=get_main_menu())
            return
        user = await get_user_from_db(message.from_user.id)
        if not user:
            await message.answer("⚠️ Пользователь не найден.", reply_markup=get_main_menu())
            return
        name = user["name"]
        new_question = await generate_question(grade, topic, name)
        await state.set_state(TaskState.waiting_for_answer)
        await state.update_data(question=new_question, last_score=0)

        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✍️ Ответить текстом"), KeyboardButton(text="🎤 Ответить голосом")],
                [KeyboardButton(text="❓ Уточнить"), KeyboardButton(text="🏠 Главное меню")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.answer(f"Новый вопрос для уровня {grade} по теме «{topic}»:\n\n{new_question}", reply_markup=kb)
        return

    # --- Показать правильный ответ ---
    if text == "✅ Показать правильный ответ":
        logging.info("[DEBUG] Пользователь нажал '✅ Показать правильный ответ' в голосовом режиме")
        data = await state.get_data()
        last_question = data.get("last_question")
        last_grade = data.get("last_grade")

        if not last_question or not last_grade:
            await message.answer(
                "⚠️ Сейчас нет активного задания, для которого можно показать правильный ответ.",
                reply_markup=get_main_menu()
            )
            await state.clear()
            return

        correct_answer = await generate_correct_answer(last_question, last_grade)
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="➡️ Следующий вопрос")],
                [KeyboardButton(text="🏠 Главное меню")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.answer(f"✅ Эталонный ответ уровня {last_grade}:\n\n{correct_answer}", parse_mode="HTML", reply_markup=kb)
        return

    # --- Если пользователь не отправил голос ---
    if not message.voice:
        await message.answer("⚠️ Пожалуйста, отправьте именно голосовое сообщение.")
        return

    # --- Обработка голосового файла ---
    voice = message.voice
    file = await bot.get_file(voice.file_id)
    file_path = file.file_path
    file_url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file_path}"
    save_path = f"temp_{message.from_user.id}.ogg"

    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(file_url) as resp:
            with open(save_path, "wb") as f:
                f.write(await resp.read())

    text = await transcribe_audio(save_path)
    os.remove(save_path)
    await message.answer(f"📝 Расшифровка: «{text}»\nОцениваю...")

    # --- Оценка ответа ---
    data = await state.get_data()
    question = data.get("question")
    grade = data.get("grade")
    last_score = data.get("last_score", 0.0)
    user = await get_user_from_db(message.from_user.id)

    if not user or not grade or not question:
        await message.answer("⚠️ Не найдены данные для оценки.")
        return

    feedback_raw = await evaluate_answer(question, text, user["name"])
    logging.info(f"[DEBUG] RAW FEEDBACK (voice):\n{feedback_raw}")

    if not feedback_raw or "Ошибка" in feedback_raw:
        await message.answer(
            "❌ Произошла ошибка при оценке голосового ответа. Попробуйте снова или воспользуйтесь текстом.",
            reply_markup=get_main_menu()
        )
        await state.clear()
        return

    import re
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
        await update_user_points(message.from_user.id, new_score - last_score)
        await update_level(message.from_user.id)
        await state.update_data(last_score=new_score)

    # --- Формирование результата ---
    result_msg = ""
    if criteria_block:
        result_msg += f"<b>Критерии:</b>\n{criteria_block}\n\n"
    result_msg += f"<b>Оценка (Score):</b> {new_score}\n\n"
    result_msg += f"<b>Обратная связь (Feedback):</b>\n{feedback_text}"

    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➡️ Следующий вопрос")],
            [KeyboardButton(text="✅ Показать правильный ответ")],
            [KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await message.answer(result_msg, parse_mode="HTML", reply_markup=kb)
    await state.update_data(last_question=question, last_grade=grade)

# --------------------------
# Дополнительный callback для "next_question"
# --------------------------

@router.callback_query(F.data == "next_question")
async def next_question_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Выберите грейд, для которого хотите получить задание:", reply_markup=get_grades_menu())
    await callback.answer()

# --------------------------
# Функции для работы с OpenAI
# --------------------------

async def generate_question(grade: str, topic: str, name: str) -> str:
    prompt = (
        f"Ты опытный интервьюер по найму продакт-менеджеров. "
        f"Не здоровайся, не используй приветственные фразы. Задай реалистичный, живой кейсовый вопрос кандидату уровня {grade} по теме «{topic}». "
        f"Обращайся к кандидату по имени {name}. Максимум 800 символов. Не используй символ * (звёздочку)."
    )
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты интервьюер по продукту. Генерируй короткие, реалистичные и живые кейс-вопросы. Не пиши шаблонно и не здоровайся."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=300,
            temperature=0.7
        )
        question_text = response.choices[0].message.content.strip()
        return question_text[:797] + "..." if len(question_text) > 800 else question_text
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
        "Определи итоговую оценку (Score) от 0.0 до 1.0.\n"
        "Выведи результат строго в формате:\n\n"
        "Критерии:\n"
        "🔹 Соответствие вопросу: <эмоджи>\n"
        "🔹 Полнота: <эмоджи>\n"
        "🔹 Аргументация: <эмоджи>\n"
        "🔹 Структура: <эмоджи>\n"
        "🔹 Примеры: <эмоджи>\n\n"
        "Score: <число>\n"
        "Feedback: Ваш ответ... (обратись к студенту на «Вы», но не здоровайся)"
    )
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты строгий преподаватель. Не здоровайся, сразу давай оценку без лишних слов."},
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
        f"Приведи полностью развернутый правильный ответ для уровня {grade} на следующий вопрос:\n\n"
        f"{question}\n\n"
        "Отвечай строго по делу, без оценочных комментариев, приветствий или лишних пояснений. Дай только эталонное решение."
    )
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "Ты опытный преподаватель продакт-менеджмента. Твой ответ должен содержать только правильное, структурированное и подробное решение, без оценок, приветствий и лишних комментариев."
                },
                {"role": "user", "content": prompt}
            ],
            max_tokens=1000,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Ошибка генерации эталонного ответа: {e}")
        return "❌ Ошибка генерации эталонного ответа."

async def transcribe_audio(file_path: str) -> str:
    with open(file_path, "rb") as audio_file:
        response = await asyncio.to_thread(
            client.audio.transcriptions.create,
            model="whisper-1",
            file=audio_file
            language="ru"
        )
    return response.text

# --------------------------
# Запуск бота
# --------------------------

async def on_startup():
    await create_db_pool()
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(on_startup())
