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

########################
# Инициализация бота/диспетчера
########################

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)
dp.message.middleware(InactivityMiddleware(timeout_seconds=900))
dp.callback_query.middleware(InactivityMiddleware(timeout_seconds=900))

########################
# Загрузка переменных окружения
########################

API_TOKEN = os.getenv("API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_IDS = os.getenv("ADMIN_IDS", "")
admin_ids = [int(x.strip()) for x in ADMIN_IDS.split(",")] if ADMIN_IDS else []

########################
# Настройка OpenAI клиента
########################

client = OpenAI(api_key=OPENAI_API_KEY)

########################
# Настройка логирования
########################

logging.basicConfig(level=logging.INFO)

########################
# Глобальные переменные
########################

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

def get_admin_menu():
    keyboard = [
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💬 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

########################
# Состояния
########################

class RegisterState(StatesGroup):
    name = State()
    age = State()

class TaskState(StatesGroup):
    waiting_for_answer = State()
    waiting_for_clarification = State()

########################
# Подключение к PostgreSQL
########################

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

########################
# Функции работы с базой данных
########################

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

########################
# Обработчики коллбэков и команд
########################

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

@router.callback_query(F.data == "start_answering")
async def start_answering(callback: CallbackQuery):
    await callback.message.answer(
        "✏️ Напишите свой ответ сообщением.",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await callback.answer()

@router.message(lambda msg: msg.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    # При запуске /start очищаем предыдущее состояние,
    # чтобы диалог начинался заново.
    await state.clear()
    # Обнуляем список id сообщений бота
    await state.update_data(bot_messages=[])
    
    # Проверяем, зарегистрирован ли пользователь
    user = await get_user_from_db(message.from_user.id)
    
    if user is None:
        # Если пользователь не зарегистрирован – сначала показываем логотип с фото.
        logo_msg = await message.answer_photo(
            photo="https://i.imgur.com/zIPzQKF.jpeg",
            caption="Добро пожаловать в One to One IT Academy!"
        )
        # Сохраняем id сообщения логотипа в состоянии (список bot_messages)
        data = await state.get_data()
        bot_messages = data.get("bot_messages", [])
        bot_messages.append(logo_msg.message_id)
        await state.update_data(bot_messages=bot_messages)
        
        # Затем отправляем сообщение с кнопкой "Начать обучение"
        start_keyboard = types.ReplyKeyboardMarkup(
            keyboard=[[types.KeyboardButton(text="Начать обучение")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        start_msg = await message.answer("Нажмите «Начать обучение», чтобы начать.", reply_markup=start_keyboard)
        # Сохраняем id этого сообщения
        data = await state.get_data()
        bot_messages = data.get("bot_messages", [])
        bot_messages.append(start_msg.message_id)
        await state.update_data(bot_messages=bot_messages)
        
    else:
        # Если пользователь зарегистрирован – показываем приветственное сообщение и главное меню
        username, name, age, level, points = (
            user["username"],
            user["name"],
            user["age"],
            user["level"],
            user["points"]
        )
        # Округляем баллы до 2-х знаков после запятой (если нужно)
        points_str = f"{points:.2f}"
        welcome = f"👋 Привет, {name}!\n{welcome_text}\n<b>⭐ Баллы:</b> {points_str}"
        main_menu_msg = await message.answer(welcome, reply_markup=get_main_menu(), parse_mode="HTML")
        # Сохраняем id сообщения
        data = await state.get_data()
        bot_messages = data.get("bot_messages", [])
        bot_messages.append(main_menu_msg.message_id)
        await state.update_data(bot_messages=bot_messages)

@router.message(lambda msg: msg.text == "Начать обучение")
async def start_training(message: Message, state: FSMContext):
    # Очищаем состояние, чтобы начать диалог с чистого листа
    await state.clear()
    # Инициализируем список идентификаторов сообщений бота (если используете middleware для удаления сообщений)
    await state.update_data(bot_messages=[])

    # Далее проверяем, зарегистрирован ли пользователь
    user = await get_user_from_db(message.from_user.id)
    if user:
        # Если пользователь зарегистрирован – выводим главное меню
        await message.answer("Добро пожаловать! Выберите, что хотите сделать.", reply_markup=get_main_menu())
    else:
        # Если пользователь не зарегистрирован – отправляем логотип и начинаем регистрацию
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

########################
# Админка
########################

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

@router.callback_query(F.data == "exam")
async def exam_callback(callback: CallbackQuery):
    text = (
        "📝 Раздел Экзамен появится в ближайшее время.\n\n"
        "Следите за обновлениями и нажмите кнопку ниже, чтобы вернуться в главное меню."
    )
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_exam_menu())
    await callback.answer()

########################
# Получение задания: выбор грейда и темы
########################

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
    await state.set_state(TaskState.waiting_for_answer)
    await state.update_data(question=question, grade=selected_grade, selected_topic=chosen_topic, last_score=0.0)

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Ответить", callback_data="start_answering")],
        [InlineKeyboardButton(text="❓ Уточнить информацию", callback_data="clarify_info")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])

    await callback.message.answer(
        f"💬 Задание для уровня {selected_grade} по теме «{chosen_topic}»:\n\n"
        f"{question}\n\n"
        "Что хотите сделать?",
        reply_markup=keyboard
    )
    await callback.answer()

########################
# Поведение при уточнении
########################

@router.callback_query(F.data == "clarify_info")
async def clarify_info_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TaskState.waiting_for_clarification)
    await callback.message.answer(
        "✏️ Напишите, что именно хотите уточнить по заданию:",
        reply_markup=types.ReplyKeyboardRemove()
    )
    await callback.answer()

@router.message(TaskState.waiting_for_clarification)
async def process_clarification(message: Message, state: FSMContext):
    data = await state.get_data()
    question = data.get("question")
    user = await get_user_from_db(message.from_user.id)
    name = user["name"] if user else "кандидат"

    # Формируем новый prompt для генерации краткого и направляющего ответа по уточнению.
    # В данном промпте мы просим ответить только по теме задания.
    clarification_prompt = (
        f"Вопрос: {question}\n"
        f"Уточнение от кандидата {name}:\n{message.text.strip()}\n\n"
        "Ответ должен быть кратким, конкретным и направляющим. "
        "Если уточнение звучит, например, как 'Мне описать все инструменты или только один?', "
        "то ответ должен быть: 'Чем больше инструментов вы опишете, тем лучше. Приведите примеры и раскройте каждый по отдельности'. "
        "Если уточнение звучит как 'Дай мне пример конкретного продукта', то ответ должен быть: 'Возьмите для примера продукт X, он отлично подходит для этого задания'. "
        "Если уточнение не по теме, кратко напомните: 'Пожалуйста, спрашивайте только в рамках данного задания'. "
        "Дайте ответ строго по теме вопроса, без лишних вступлений и приветствий."
    )

    try:
        clarification_response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты проводишь собеседование по продакт-менеджменту. "
                        "Отвечай кратко, по существу и только по теме вопроса, без приветствий и лишних слов. "
                        "Если уточнение относится к заданию, направь кандидата, как ему лучше ответить."
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

    # Формируем клавиатуру: предлагаем вернуться к ответу или в главное меню.
    reply_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✍️ Ответить")],
            [KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await message.answer(
        f"📎 Уточнение:\n{reply}\n\nЧто делаем дальше?",
        reply_markup=reply_keyboard
    )
    # Переводим пользователя обратно в состояние ожидания ответа
    await state.set_state(TaskState.waiting_for_answer)

########################
# Поведение при ответе на задание
########################

@router.message(F.text == "✍️ Ответить")
async def ask_for_answer(message: Message, state: FSMContext):
    await message.answer("✏️ Напишите свой ответ сообщением.")
    await state.set_state(TaskState.waiting_for_answer)

@router.message(TaskState.waiting_for_answer)
async def handle_task_answer(message: Message, state: FSMContext):
    # Берём текст сообщения и удаляем лишние пробелы
    text = message.text.strip()
    logging.info(f"[DEBUG] Received text: {repr(text)}")
    # Загружаем данные из состояния
    data = await state.get_data()
    
    # -------------------------------
    # Обработка сервисных команд:
    # -------------------------------
    
    # Если нажата кнопка "❓ Уточнить по вопросу"
    if text == "❓ Уточнить по вопросу":
        logging.info("[DEBUG] Пользователь нажал '❓ Уточнить по вопросу'")
        await state.set_state(TaskState.waiting_for_clarification)
        await message.answer(
            "✏️ Напишите, что именно хотите уточнить по заданию:",
            reply_markup=types.ReplyKeyboardRemove()
        )
        return  # Выходим, чтобы не оценивать этот ответ
    
    # Если нажата кнопка "🏠 Главное меню"
    if text == "🏠 Главное меню":
        logging.info("[DEBUG] Пользователь нажал '🏠 Главное меню'")
        user = await get_user_from_db(message.from_user.id)
        if user:
            name = user["name"]
            age = user["age"]
            level = user["level"]
            points = user["points"]
            profile_text = (
                f"<b>👤 Имя:</b> {name}\n"
                f"<b>🎂 Возраст:</b> {age}\n"
                f"<b>🎯 Уровень:</b> {level}\n"
                f"<b>⭐ Баллы:</b> {points}\n\n"
                "Вы в главном меню:"
            )
        else:
            profile_text = "Пользователь не найден. Вы в главном меню."
        await message.answer(profile_text, parse_mode="HTML", reply_markup=get_main_menu())
        return
    
    # Если нажата кнопка "✅ Показать правильный ответ"
    if text == "✅ Показать правильный ответ":
        logging.info("[DEBUG] Пользователь нажал '✅ Показать правильный ответ'")
        last_question = data.get("last_question")
        last_grade = data.get("last_grade")
        if not last_question or not last_grade:
            await message.answer("⚠️ Ошибка: не найден текущий вопрос или грейд.")
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
        await message.answer(
            f"✅ Эталонный ответ уровня {last_grade}:\n\n{correct_answer}",
            parse_mode="HTML",
            reply_markup=kb
        )
        return
    
    # Если нажата кнопка "➡️ Следующий вопрос"
    if text == "➡️ Следующий вопрос":
        logging.info("[DEBUG] Пользователь нажал '➡️ Следующий вопрос'")
        grade = data.get("grade")
        topic = data.get("selected_topic")  # Убедитесь, что вы сохраняете выбранную тему ранее
        user = await get_user_from_db(message.from_user.id)
        if not user or not grade or not topic:
            await message.answer("⚠️ Ошибка: не найдены нужные данные.")
            return
        name = user["name"]
        new_question = await generate_question(grade, topic, name)
        # Сбрасываем баллы для нового вопроса — last_score становится 0
        await state.update_data(question=new_question, last_score=0)
        kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✍️ Ответить")],
                [KeyboardButton(text="❓ Уточнить по вопросу")],
                [KeyboardButton(text="🏠 Главное меню")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await message.answer(
            f"Новый вопрос для уровня {grade} по теме «{topic}»:\n\n{new_question}",
            reply_markup=kb
        )
        return

    # -------------------------------
    # Если ни одна "служебная" кнопка не нажата,
    # обрабатываем это как обычный ответ и оцениваем его.
    # -------------------------------
    
    # Берём данные: вопрос, уровень и предыдущую оценку (last_score)
    grade = data.get("grade")
    question = data.get("question")
    last_score = data.get("last_score", 0.0)
    user = await get_user_from_db(message.from_user.id)
    if not grade or not question or not user:
        await message.answer("⚠️ Не найдены данные задания. Попробуйте снова.")
        return

    student_name = user["name"]
    logging.info(f"[DEBUG] Оцениваем ответ для вопроса: {repr(question)} пользователя: {student_name}")
    
    # Оцениваем ответ через функцию evaluate_answer (она возвращает текст с оценкой)
    feedback_raw = await evaluate_answer(question, message.text, student_name)
    logging.info(f"[DEBUG] RAW FEEDBACK:\n{feedback_raw}")
    
    # Извлекаем оценку (Score), критерии и обратную связь из feedback_raw с помощью регулярного выражения
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
    
    # Если новая оценка выше предыдущей, добавляем разницу баллов
    if new_score > last_score:
        diff = new_score - last_score
        logging.info(f"[DEBUG] Новый балл diff = {diff}")
        await update_user_points(message.from_user.id, diff)
        await update_level(message.from_user.id)
        await state.update_data(last_score=new_score)
    
    # Формируем итоговое сообщение с оценкой и обратной связью
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
    # Сохраняем данные для возможности показать эталонный ответ
    await state.update_data(last_question=question, last_grade=grade)

########################
# Кнопка "следующий вопрос" и показ правильного ответа
########################

@router.message(F.text == "➡️ Следующий вопрос")
async def ask_next_question(message: Message, state: FSMContext):
    data = await state.get_data()
    grade = data.get("grade")
    topic = data.get("selected_topic")
    user = await get_user_from_db(message.from_user.id)
    name = user["name"] if user else "кандидат"

    if not grade or not topic:
        await message.answer("⚠️ Ошибка: не найдены тема или грейд.")
        return

    question = await generate_question(grade, topic, name)
    await state.update_data(question=question)
    await message.answer(
        f"💬 Новый вопрос для {grade} по теме «{topic}»:\n\n"
        f"{question}\n\n"
        "Выберите, что хотите сделать:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="✍️ Ответить")],
                [KeyboardButton(text="❓ Уточнить по вопросу")],
                [KeyboardButton(text="🏠 Главное меню")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
    )

@router.message(F.text == "❓ Уточнить по вопросу")
async def clarify_after_answer(message: Message, state: FSMContext):
    # Те же действия, что и при clarify_info_callback
    await state.set_state(TaskState.waiting_for_clarification)
    await message.answer("✏️ Напишите, что именно хотите уточнить по заданию:", reply_markup=types.ReplyKeyboardRemove())

@router.message(F.text == "✅ Показать правильный ответ")
async def show_correct_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    last_question = data.get("last_question")
    last_grade = data.get("last_grade")
    
    if not last_question or not last_grade:
        await message.answer("⚠️ Ошибка: не найден текущий вопрос или грейд.")
        return

    correct_answer = await generate_correct_answer(last_question, last_grade)
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="➡️ Следующий вопрос")],
            [KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await message.answer(
        f"✅ Эталонный ответ уровня {last_grade}:\n\n{correct_answer}",
        parse_mode="HTML",
        reply_markup=keyboard
    )

########################
# Дополнительные callback
########################

@router.callback_query(F.data == "next_question")
async def next_question_handler(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "Выберите грейд, для которого хотите получить задание:",
        reply_markup=get_grades_menu()
    )
    await callback.answer()

########################
# Функции для работы с OpenAI
########################

async def generate_question(grade: str, topic: str, name: str) -> str:
    # <-- Изменено! Добавлена инструкция "не здоровайся"
    prompt = (
        f"Ты опытный интервьюер по найму продакт-менеджеров. "
        f"Не здоровайся, не используй приветственные фразы. Задай реалистичный, живой кейсовый вопрос "
        f"кандидату уровня {grade} по теме «{topic}». "
        f"Обращайся к кандидату по имени {name}. Максимум 800 символов. "
        f"Не используй символ * (звёздочку). "
    )
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "Ты интервьюер по продукту. Генерируй короткие, реалистичные и живые кейс-вопросы. Не пиши шаблонно и не здоровайся."
                },
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
    # <-- Изменено! Добавлена инструкция "не здоровайся" 
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
                {
                    "role": "system",
                    "content": "Ты строгий преподаватель. Не здоровайся, сразу давай оценку без лишних слов."
                },
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
        "Отвечай строго по делу, без оценочных комментариев, приветствий или лишних пояснений. "
        "Дай только эталонное решение."
    )
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты опытный преподаватель продакт-менеджмента. Твой ответ должен содержать только правильное, "
                        "структурированное и подробное решение, без оценок, приветствий и дополнительных комментариев."
                    )
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

########################
# Запуск бота
########################

async def on_startup():
    await create_db_pool()
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    asyncio.run(on_startup())