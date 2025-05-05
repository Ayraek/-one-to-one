print("=== Бот стартует ===")
import os
import re
import logging
logging.basicConfig(level=logging.DEBUG)
import asyncpg
import asyncio
from urllib.parse import urlparse

from dotenv import load_dotenv
load_dotenv()

from openai import OpenAI

from aiogram import Bot, Dispatcher, Router, F, types
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import StatesGroup, State
from inactivity_middleware import InactivityMiddleware
from aiogram.filters import StateFilter
print("=== Все импорты прошли успешно ===")

# --------------------------
# Загрузка переменных окружения
# --------------------------

API_TOKEN = os.getenv("API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ADMIN_IDS = os.getenv("ADMIN_IDS", "")
admin_ids = [int(x.strip()) for x in ADMIN_IDS.split(",")] if ADMIN_IDS else []

# ────────────────────────────────────────────────────
# inline-клавиатуры для навигации
# После генерации нового вопроса (есть кнопка «Уточнить»)
NAV_KB_QUESTION = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="➡️ Следующий вопрос",        callback_data="nav_next")],
    [InlineKeyboardButton(text="✅ Показать правильный ответ", callback_data="nav_show")],
    [InlineKeyboardButton(text="❓ Уточнить вопрос",           callback_data="clarify_info")],
    [InlineKeyboardButton(text="🏠 Главное меню",             callback_data="nav_main")]
])

# После оценки ответа (без кнопки «Уточнить»)
NAV_KB_AFTER_ANSWER = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="➡️ Следующий вопрос",        callback_data="nav_next")],
    [InlineKeyboardButton(text="✅ Показать правильный ответ", callback_data="nav_show")],
    [InlineKeyboardButton(text="🏠 Главное меню",             callback_data="nav_main")]
])

# ────────────────────────────────────────────────────
# После того, как показали правильный ответ — только Next и Main
NAV_KB_AFTER_SHOW = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="➡️ Следующий вопрос", callback_data="nav_next")],
    [InlineKeyboardButton(text="🏠 Главное меню",        callback_data="nav_main")]
])
# ────────────────────────────────────────────────────

# ────────────────────────────────────────────────────
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

ACADEMY_TOPICS = [
    ("research", "📚 Исследования"),
    ("mvp", "🛠 Продукт и MVP"),
    ("marketing", "📈 Маркетинг IT продуктов"),
    ("team", "👨‍💻 Управление командой"),
    ("analytics", "📊 Продуктовая аналитика"),
    ("strategy", "🏹 Стратегия"),
    ("softskills", "🤝 Soft Skills")
]

welcome_text = (
    "💡 Добро пожаловать в \"One to One Booster bot\" — вашего личного ассистента для прокачки навыков в продакт-менеджменте!"
)
ACADEMY_SUBTOPICS = {
    "research": [
        ("interview", "📋 Интервью"),
        ("usability", "🖥 Юзабилити тестирование"),
        ("cjm", "🗺 CJM"),
        ("quantitative", "📊 Количественные исследования"),
    ],
    "mvp": [
        ("problem_research", "🔍 Исследование проблемы"),
        ("prototype_testing", "🛠 Тестирование прототипа"),
        ("value_proposition", "💎 Ценность продукта"),
    ],
    # И так далее для других тем
}

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
        [InlineKeyboardButton(text="👨‍🎓 Ученикам Академии", callback_data="learning")],
        [InlineKeyboardButton(text="📰 Новости", callback_data="news")],
        [InlineKeyboardButton(text="📊 Аналитика прогресса", callback_data="progress")]
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

def get_admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📈 Метрики продукта", callback_data="admin_metrics")],
        [InlineKeyboardButton(text="📨 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🎓 Добавить ученика Академии", callback_data="admin_add_academy")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# -------------------
# Состояния
# --------------------------

class RegisterState(StatesGroup):
    name = State()
    age = State()

class TaskState(StatesGroup):
    waiting_for_answer = State()
    waiting_for_clarification = State()
    waiting_for_voice = State()
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

        await conn.execute('''
            ALTER TABLE users ADD COLUMN IF NOT EXISTS is_academy_student BOOLEAN DEFAULT FALSE;
        ''')
        await conn.execute('''
            ALTER TABLE users ADD COLUMN IF NOT EXISTS academy_points REAL DEFAULT 0.0;
        ''')

                # 👇 Таблица answers
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS answers (
                id SERIAL PRIMARY KEY,
                user_id BIGINT,
                question TEXT,
                answer TEXT,
                grade TEXT,
                topic TEXT,
                score REAL,
                is_suspicious BOOLEAN DEFAULT FALSE,
                created_at TIMESTAMP DEFAULT now()
            )
        ''')

        # 👇 Таблица analytics
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS analytics (
                user_id BIGINT PRIMARY KEY,
                tasks_done INTEGER,
                average_score REAL,
                criteria_relevance REAL,
                criteria_completeness REAL,
                criteria_argumentation REAL,
                criteria_structure REAL,
                criteria_examples REAL,
                percentile INTEGER,
                next_target INTEGER
            )
        ''')

        # ✅ Проверка и добавление поля is_suspicious
        await conn.execute('''
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM information_schema.columns 
                    WHERE table_name='answers' AND column_name='is_suspicious'
                ) THEN
                    ALTER TABLE answers ADD COLUMN is_suspicious BOOLEAN DEFAULT FALSE;
                END IF;
            END
            $$;
        ''')
   
        await conn.execute('''
            CREATE TABLE IF NOT EXISTS academy_progress (
                user_id BIGINT,
                topic TEXT,
                points REAL DEFAULT 0.0,
                PRIMARY KEY (user_id, topic)
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

async def update_user_academy_points(user_id: int, additional_points: float):
    """Увеличить поле academy_points в таблице users"""
    async with db_pool.acquire() as conn:
        await conn.execute(
            'UPDATE users SET academy_points = academy_points + $1 WHERE id = $2',
            additional_points, user_id
        )

import time

async def save_user_answer(user_id: int, question: str, answer: str, grade: str, topic: str, score: float, state: FSMContext = None):
    # Получаем данные из FSMContext, если передан
    state_data = await state.get_data() if state else {}
    question_time = state_data.get("question_time", time.time())

    # Условие подозрительности
    is_suspicious = len(answer.strip()) < 30 or (time.time() - question_time) < 120

    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO answers (user_id, question, answer, grade, topic, score, is_suspicious)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
        ''', user_id, question, answer, grade, topic, score, is_suspicious)

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

async def get_user_rank(user_id: int) -> int:
    async with db_pool.acquire() as conn:
        rows = await conn.fetch('''
            SELECT id
            FROM users
            ORDER BY points DESC
        ''')
        ids = [row['id'] for row in rows]
        if user_id in ids:
            return ids.index(user_id) + 1  # позиция +1, т.к. с нуля
        return -1  # если вдруг не нашли

# Получить текущие баллы по теме
async def get_academy_topic_points(user_id: int, topic: str) -> float:
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT points FROM academy_progress WHERE user_id = $1 AND topic = $2",
            user_id, topic
        )
        return row["points"] if row else 0.0

# Добавить баллы
async def update_academy_topic_points(user_id: int, topic: str, additional: float):
    async with db_pool.acquire() as conn:
        await conn.execute('''
            INSERT INTO academy_progress (user_id, topic, points)
            VALUES ($1, $2, $3)
            ON CONFLICT (user_id, topic) DO UPDATE
            SET points = academy_progress.points + EXCLUDED.points
        ''', user_id, topic, additional)
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
        academy_points = user.get("academy_points", 0.0)
        is_academy = user.get("is_academy_student", False)
        rank = await get_user_rank(callback.from_user.id)

        # Получаем последние 3 ответа
        async with db_pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT topic, grade, score
                FROM answers
                WHERE user_id = $1
                ORDER BY created_at DESC
                LIMIT 3
            ''', callback.from_user.id)

        history_lines = "\n".join([
            f"• {r['topic']} ({r['grade']}) — {round(r['score'], 2)}" for r in rows
        ]) if rows else "— пока нет"

        # Основной текст профиля
        text = (
            f"<b>👤 Имя:</b> {name}\n"
            f"<b>🎂 Возраст:</b> {age}\n"
            f"<b>🎯 Уровень:</b> {level}\n"
            f"<b>⭐ Общий балл:</b> {round(points, 2)}\n"
        )

        # Добавляем Академию, если применимо
        if is_academy:
            text += f"<b>🎓 Баллы Академии:</b> {round(academy_points, 2)}\n"

        text += (
            f"\n<b>🏆 Рейтинг:</b> {rank}-е место\n\n"
            f"<b>🕘 Последние ответы:</b>\n{history_lines}"
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
    await state.clear()
    await message.answer("🔄 Перезапуск...", reply_markup=ReplyKeyboardRemove())

    user = await get_user_from_db(message.from_user.id)

    if user:
        name = user["name"]
        level = user["level"]
        points = round(user["points"], 2)

        welcome_text = (
            f"👋 С возвращением, {name}!\n"
            f"🎓 Уровень: {level}\n"
            f"⭐ Баллы: {points}\n\n"
            "Готов прокачаться сегодня?"
        )

        keyboard = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="🚀 Готов, погнали!")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )

        await message.answer(welcome_text, reply_markup=keyboard)
    else:
        await message.answer_photo(
            photo="https://i.imgur.com/zIPzQKF.jpeg",
            caption="Добро пожаловать в One to One IT Academy!"
        )
        await message.answer("👋 Как тебя зовут?")
        await state.set_state(RegisterState.name)

@router.message(lambda msg: msg.text == "🚀 Готов, погнали!")
async def start_from_welcome(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🚀 Отлично, погнали!", reply_markup=ReplyKeyboardRemove())
    await message.answer("👇 Главное меню", reply_markup=get_main_menu())

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

@router.callback_query(F.data == "admin_metrics")
async def admin_metrics_handler(callback: CallbackQuery):
    try:
        async with db_pool.acquire() as conn:
            # Среднее количество заданий на пользователя
            tasks_avg = await conn.fetchval('''
                SELECT AVG(cnt) FROM (
                    SELECT COUNT(*) AS cnt FROM answers GROUP BY user_id
                ) sub
            ''')

            # Средняя оценка
            avg_score = await conn.fetchval("SELECT AVG(score) FROM answers")

            # Популярные темы
            top_topics = await conn.fetch('''
                SELECT topic, COUNT(*) as count
                FROM answers
                GROUP BY topic
                ORDER BY count DESC
                LIMIT 3
            ''')

            top_lines = "\n".join([
                f"{i+1}. {r['topic']} — {r['count']} ответов" for i, r in enumerate(top_topics)
            ])

            # Заглушка для времени
            avg_time = "— скоро будет доступно"

            # Финальный текст
            text = (
                "<b>📈 Метрики продукта</b>\n\n"
                f"🧮 Среднее число заданий на пользователя: {round(tasks_avg or 0, 2)}\n"
                f"⭐ Средняя оценка за задания: {round(avg_score or 0, 2)}\n"
                f"⏱️ Среднее время в боте: {avg_time}\n\n"
                f"<b>🔥 Топ-3 темы заданий:</b>\n{top_lines}\n\n"
                "<i>Метрики собираются на основе пользовательской активности</i>"
            )

            await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_admin_menu())

    except Exception as e:
        logging.error(f"Ошибка при получении метрик: {e}")
        await callback.message.edit_text("❌ Ошибка при получении метрик.", reply_markup=get_admin_menu())

    await callback.answer()

@router.callback_query(F.data == "admin_add_academy")
async def add_academy_student_start(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("✍️ Введите ID пользователя, которого нужно сделать учеником Академии:")
    await state.set_state("waiting_for_student_id")
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
            f"<b>⭐ Баллы:</b> {round(user['points'], 2)}\n\n"
        )
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_main_menu())
    else:
        await callback.message.edit_text(welcome_text, reply_markup=get_main_menu())
    await callback.answer()

@router.callback_query(F.data == "learning")
async def learning_entry(callback: CallbackQuery):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 С 0 до Junior/Middle", callback_data="track_junior_middle")],
        [InlineKeyboardButton(text="🧠 Senior", callback_data="track_senior")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])
    await callback.message.edit_text(
        "🎓 <b>Выберите программу обучения:</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data == "track_junior_middle")
async def handle_junior_track(callback: CallbackQuery):
    user = await get_user_from_db(callback.from_user.id)

    if not user or not user["is_academy_student"]:
        await callback.message.edit_text(
            "🚫 Доступ только для учеников Академии One to One!\n\n"
            "За подробностями пишите сюда: [@apyat](https://t.me/apyat)",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        await callback.answer()
        return
    # если есть доступ
    await show_academy_topics(callback)

@router.callback_query(F.data.startswith("academy_topic_"))
async def handle_academy_topic(callback: CallbackQuery, state: FSMContext):
    user = await get_user_from_db(callback.from_user.id)

    # Проверка доступа
    if not user or not user["is_academy_student"]:
        await callback.message.edit_text(
            "🚫 Доступ только для учеников Академии One to One!\n\n"
            "За подробностями пишите сюда: [@apyat](https://t.me/apyat)",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        await callback.answer()
        return

    # Получаем код раздела
    topic_key = callback.data.replace("academy_topic_", "").strip()

    # Ищем подтемы для выбранного раздела
    subtopics = ACADEMY_SUBTOPICS.get(topic_key)
    if not subtopics:
        await callback.message.answer("❌ Ошибка: темы пока не найдены для этого раздела.")
        return

    # Сохраняем текущий раздел в состояние
    await state.update_data(selected_academy_topic=topic_key)

    # Строим клавиатуру подтем
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=name, callback_data=f"academy_subtopic_{code}")]
            for code, name in subtopics
        ] + [[InlineKeyboardButton(text="🔙 Назад", callback_data="learning")]]
    )

    await callback.message.edit_text(
        "🧠 <b>Выберите тему для практики:</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )

    await callback.answer()

@router.callback_query(F.data.startswith("academy_subtopic_"))
async def handle_academy_subtopic(callback: CallbackQuery, state: FSMContext):
    user = await get_user_from_db(callback.from_user.id)

    if not user or not user["is_academy_student"]:
        await callback.message.edit_text(
            "🚫 Доступ только для учеников Академии One to One!\n\n"
            "За подробностями пишите сюда: [@apyat](https://t.me/apyat)",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        await callback.answer()
        return

    # Определяем выбранную подтему
    subtopic_key = callback.data.replace("academy_subtopic_", "").strip()
    data = await state.get_data()
    main_topic_key = data.get("selected_academy_topic", "")

    subtopics = ACADEMY_SUBTOPICS.get(main_topic_key, [])
    subtopic_name = next((name for code, name in subtopics if code == subtopic_key), "—")

    if subtopic_name == "—":
        await callback.message.answer("❌ Ошибка выбора темы.")
        return

    # Генерируем вопрос
    question = await generate_academy_question(main_topic_key, subtopic_name, user["name"])

    await state.set_state(TaskState.waiting_for_answer)
    await state.update_data(
        question=question,
        grade=user["level"],
        selected_topic=subtopic_name,
        last_score=0.0,
        is_academy_task=True
    )

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
        f"🎯 Задание по подтеме «{subtopic_name}»:\n\n{question}\n\nЧто хотите сделать?",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data == "track_senior")
async def handle_senior_track(callback: CallbackQuery):
    user = await get_user_from_db(callback.from_user.id)

    if not user or not user["is_academy_student"]:
        await callback.message.edit_text(
            "🚫 Доступ только для учеников Академии One to One!\n\n"
            "За подробностями пишите сюда: [@apyat](https://t.me/apyat)",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        await callback.answer()
        return

    # Если доступ есть — показываем темы
    await show_academy_topics(callback)

@router.callback_query(F.data == "news")
async def news_callback(callback: CallbackQuery):
    text = (
        "<b>📌 Что уже умеет наш бот:</b>\n\n"
        "1️⃣ Генерирует реалистичные продуктовые кейсы по уровням и темам\n"
        "2️⃣ Принимает ответы текстом и голосом 🎙️\n"
        "3️⃣ Даёт мгновенную оценку и обратную связь по 5 критериям\n"
        "4️⃣ Показывает эталонные ответы после твоего\n"
        "5️⃣ Учит уточнять вопрос, как в реальном интервью\n"
        "6️⃣ Начисляет баллы и автоматически повышает уровень 🧠\n"
        "7️⃣ Удобное меню и навигация — всё интуитивно 👌\n\n"
        
        "<b>🧪 В разработке:</b>\n\n"
        "🔄 История твоих заданий и возможность повторить\n"
        "📊 Раздел «Прогресс»: отслеживай рост от Junior до CEO\n"
        "🏆 Геймификация: бейджи, уровни, рейтинг среди пользователей\n"
        "📚 Библиотека кейсов от реальных компаний\n"
        "🎯 Персонализированные треки обучения\n"
        "🤖 AI-интервьюер — как на реальном собеседовании\n"
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

@router.callback_query(F.data == "progress")
async def show_progress_analytics(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await get_user_from_db(user_id)
    if not user:
        await callback.message.edit_text("⚠️ Пользователь не найден.")
        return

    data = await get_or_generate_analytics(user_id)
    text = format_progress_analytics(user, data)
    await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_main_menu())
    await callback.answer()


@router.message(StateFilter("waiting_for_student_id"))
async def confirm_academy_student(message: Message, state: FSMContext):
    username = message.text.strip().lstrip('@')  # Убираем @ если есть
    async with db_pool.acquire() as conn:
        user = await conn.fetchrow(
            "SELECT id FROM users WHERE username = $1", username
        )
        if not user:
            await message.answer("❌ Пользователь с таким username не найден.")
            await state.clear()
            return
        
        await conn.execute(
            "UPDATE users SET is_academy_student = TRUE WHERE id = $1",
            user["id"]
        )
    await message.answer(f"✅ Пользователь @{username} добавлен в Академию!", reply_markup=get_admin_menu())
    await state.clear()

async def show_academy_topics(callback: CallbackQuery):
    user = await get_user_from_db(callback.from_user.id)

    if not user or not user["is_academy_student"]:
        await callback.message.edit_text(
            "🚫 Доступ только для учеников Академии One to One!\n\n"
            "За подробностями пишите сюда: [@apyat](https://t.me/apyat)",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
        await callback.answer()
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Исследования", callback_data="academy_topic_research")],
        [InlineKeyboardButton(text="🛠 Продукт и MVP", callback_data="academy_topic_mvp")],
        [InlineKeyboardButton(text="📈 Маркетинг IT продуктов", callback_data="academy_topic_marketing")],
        [InlineKeyboardButton(text="👨‍💻 Управление командой", callback_data="academy_topic_team")],
        [InlineKeyboardButton(text="📊 Продуктовая аналитика", callback_data="academy_topic_analytics")],
        [InlineKeyboardButton(text="🏹 Стратегия", callback_data="academy_topic_strategy")],
        [InlineKeyboardButton(text="🤝 Soft Skills", callback_data="academy_topic_softskills")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
    ])

    await callback.message.edit_text(
        "🎯 <b>Выберите раздел для практики:</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
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
    # Достаём выбранную тему и проверяем пользователя
    chosen_topic = callback.data.replace("topic_", "").strip()
    data = await state.get_data()
    selected_grade = data.get("selected_grade")
    user = await get_user_from_db(callback.from_user.id)

    if not selected_grade or not user:
        await callback.answer("⚠️ Что-то пошло не так. Сначала выберите грейд и тему.", show_alert=True)
        return

    # Генерируем вопрос
    question = await generate_question(selected_grade, chosen_topic, user["name"])
    if not question or question.startswith("❌"):
        await callback.answer("❌ Не удалось сгенерировать вопрос. Попробуйте другую тему.", show_alert=True)
        return

    # Переходим в состояние ожидания ответа
    await state.set_state(TaskState.waiting_for_answer)
    await state.update_data(question=question, grade=selected_grade, selected_topic=chosen_topic, last_score=0.0)

    # Редактируем сообщение: текст + inline-клавиатура NAV_KB_QUESTION
    await callback.message.edit_text(
        f"💬 Задание для уровня {selected_grade} по теме «{chosen_topic}»:\n\n{question}\n\n"
        "Что хотите сделать?",
        reply_markup=NAV_KB_QUESTION
    )
    await callback.answer()

@router.callback_query(F.data=="nav_show")
async def cb_show(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    q     = data.get("last_question")
    g     = data.get("last_grade")
    if not q or not g:
        return await call.answer("Нет активного вопроса", show_alert=True)

    # Генерируем эталонный ответ
    correct = await generate_correct_answer(q, g)

    # Редактируем сообщение: показываем правильный ответ + убираем все кнопки кроме Next и Main
    await call.message.edit_text(
        f"✅ Эталонный ответ:\n\n{correct}",
        parse_mode="HTML",
        reply_markup=NAV_KB_AFTER_SHOW
    )
    await call.answer()

@router.callback_query(F.data=="nav_next")
async def cb_next(call: CallbackQuery, state: FSMContext):
    # Получаем из state, что было в предыдущем вопросе
    data = await state.get_data()
    user = await get_user_from_db(call.from_user.id)
    if not user:
        return await call.answer("Пользователь не найден", show_alert=True)

    # В зависимости от режима (общий или академия) генерируем следующий вопрос
    if data.get("is_academy_task"):
        main_topic = data.get("selected_academy_topic")
        subtopic   = data.get("selected_topic")
        new_q = await generate_academy_question(main_topic, subtopic, user["name"])
    else:
        grade = data.get("grade")
        topic = data.get("selected_topic")
        new_q = await generate_question(grade, topic, user["name"])

    # Сбрасываем предыдущий score и сохраняем новый вопрос
    await state.update_data(question=new_q, last_score=0.0)

    # Меняем текст текущего сообщения на новый вопрос + inline-клавиатуру
    await call.message.edit_text(
        f"🎯 Новый вопрос:\n\n{new_q}",
        reply_markup=NAV_KB_QUESTION
    )
    await call.answer()

@router.callback_query(F.data=="nav_main")
async def cb_main(call: CallbackQuery, state: FSMContext):
    await state.clear()
    user = await get_user_from_db(call.from_user.id)
    text = welcome_text if not user else (
        f"<b>👤 {user['name']}</b>\n🎯 {user['level']} | ⭐ {round(user['points'],2)}"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=get_main_menu())
    await call.answer()

@router.callback_query(F.data == "start_answer")
async def handle_start_answer_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("✏️ Напишите, пожалуйста, свой ответ.", reply_markup=ReplyKeyboardRemove())
    await state.set_state(TaskState.waiting_for_answer)
    await callback.answer()

# --------------------------
# Поведение при уточнении
# --------------------------

@router.callback_query(F.data == "clarify_info")
async def clarify_info_callback(callback: CallbackQuery, state: FSMContext):
    await state.set_state(TaskState.waiting_for_clarification)
    await callback.message.answer(
        "✏️ Напишите, что именно хотите уточнить по заданию:",
        reply_markup=ReplyKeyboardRemove()
    )
    await callback.answer()

@router.message(TaskState.waiting_for_clarification)
async def process_clarification(message: Message, state: FSMContext):
    data = await state.get_data()
    question = data.get("question")
    if not question:
        await message.answer("⚠️ Нет активного вопроса для уточнения. Сначала получите задание.")
        await state.clear()
        return

    # Получаем имя студента
    user = await get_user_from_db(message.from_user.id)
    name = user["name"] if user else "студент"

    # Строим промпт: перефразировать и направить, но не давать ответ
    system_content = (
        "Ты — наставник на симуляторе собеседований. "
        "Твоя задача — помочь студенту лучше понять формулировку задания, "
        "но ни в коем случае не давай готовое решение или подсказки к ответу. "
        "Можешь переформулировать вопрос, задать встречный уточняющий вопрос или направить к сути, "
        "но не раскрывай правильный ответ и не объясняй, как решать."
    )
    user_content = (
        f"Вопрос для {name}:\n{question}\n\n"
        f"Уточнение студента:\n{message.text.strip()}\n\n"
        "Ответь дружелюбно и по-человечески: переформулируй задание или задай уточняющий вопрос, "
        "если что-то непонятно. Не давай решение."
    )

    try:
        resp = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content}
            ],
            max_tokens=150,
            temperature=0.5
        )
        reply = resp.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Ошибка при уточнении: {e}")
        reply = "❌ Не удалось получить уточнение. Попробуйте снова."

    # Кнопки для дальнейшего движения: ответ текстом, голосом или в главное меню
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✍️ Ответить текстом"), KeyboardButton(text="🎤 Ответить голосом")],
            [KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await message.answer(f"📎 Уточнение:\n{reply}", reply_markup=kb)
    await state.set_state(TaskState.waiting_for_answer)
    
# --------------------------
# Общий обработчик для TaskState.waiting_for_answer
# --------------------------

@router.message(
    TaskState.waiting_for_answer,
    lambda m: m.text not in ["➡️ Следующий вопрос", "✅ Показать правильный ответ", "🏠 Главное меню"]
)
async def handle_task_answer(message: Message, state: FSMContext):
    text = message.text.strip()

    # Проверка состояния
    if await state.get_state() != TaskState.waiting_for_answer.state:
        await message.answer("⚠️ Сейчас нет активного задания.", reply_markup=get_main_menu())
        await state.clear()
        return

    # Спец-кнопки
    if text in ["✍️ Ответить", "✍️ Ответить текстом"]:
        await message.answer("✏️ Напишите ответ текстом.", reply_markup=ReplyKeyboardRemove())
        return
    if text == "🎤 Ответить голосом":
        await message.answer("🎤 Отправьте голосовое сообщение.", reply_markup=ReplyKeyboardRemove())
        await state.set_state(TaskState.waiting_for_voice)
        return
    if text in ["❓ Уточнить", "❓ Уточнить по вопросу"]:
        await message.answer("✏️ Что хотите уточнить?", reply_markup=ReplyKeyboardRemove())
        await state.set_state(TaskState.waiting_for_clarification)
        return

    # Достаём данные из state
    data       = await state.get_data()
    grade      = data.get("grade")
    question   = data.get("question")
    last_score = data.get("last_score", 0.0)

    if not grade or not question:
        await message.answer("⚠️ Нет данных задания.", reply_markup=get_main_menu())
        return

    user = await get_user_from_db(message.from_user.id)
    if not user:
        await message.answer("⚠️ Пользователь не найден.", reply_markup=get_main_menu())
        return

    # Примитивная детекция нерелевантного ответа
    low_text = text.lower()
    if len(text) < 5 or low_text in {"не знаю", "нет ответа", "-", ""}:
        result_msg = (
            "<b>📊 Критерии:</b>\n"
            "• Соответствие вопросу: 0.00\n\n"
            "<b>🧮 Оценка (Score):</b> <code>0.00</code>\n\n"
            "<b>💬 Обратная связь (Feedback):</b>\n"
            "Ответ не соответствует вопросу. Пожалуйста, попробуйте ещё раз, опираясь на суть задания."
        )
        await message.answer(result_msg, parse_mode="HTML", reply_markup=NAV_KB_AFTER_ANSWER)
        return

    # Проверка на шаблонные фразы
    if detect_gpt_phrases(text):
        await message.answer("⚠️ Переформулируйте ответ своими словами.", reply_markup=NAV_KB_AFTER_ANSWER)
        return

    # Обычная оценка через OpenAI
    feedback_raw = await evaluate_answer(question, text, user["name"])
    if not feedback_raw or "Ошибка" in feedback_raw:
        await message.answer("❌ Ошибка оценки. Попробуйте позже.", reply_markup=get_main_menu())
        await state.clear()
        return

    # Парсим результат
    import re
    pattern = r"Критерии:\s*(.*?)Итог:\s*([\d.]+)\s*Feedback:\s*(.*)"
    match = re.search(pattern, feedback_raw, re.DOTALL)
    if match:
        criteria_block = match.group(1).strip()
        try:
            new_score = float(match.group(2))
        except:
            new_score = 0.0
        feedback_text = match.group(3).strip()
    else:
        criteria_block = ""
        new_score = 0.0
        feedback_text = feedback_raw.strip()

    # Вычисляем приращение
    increment = new_score - last_score
    if increment > 0:
        if data.get("is_academy_task"):
            await update_academy_topic_points(message.from_user.id, data.get("selected_topic"), increment)
            await update_user_academy_points(message.from_user.id, increment)
        await update_user_points(message.from_user.id, increment)
        await update_level(message.from_user.id)
        await save_user_answer(
            user_id=message.from_user.id,
            question=question,
            answer=text,
            grade=grade,
            topic=data.get("selected_topic", "—"),
            score=new_score,
            state=state
        )
        await state.update_data(last_score=new_score)

    # Формируем и отправляем сообщение с результатом
    result_msg = ""
    if criteria_block:
        result_msg += f"<b>📊 Критерии:</b>\n{criteria_block}\n\n"
    result_msg += f"<b>🧮 Оценка (Score):</b> <code>{round(new_score,2)}</code>\n\n"
    result_msg += f"<b>💬 Обратная связь (Feedback):</b>\n{feedback_text}"

    await message.answer(result_msg, parse_mode="HTML", reply_markup=NAV_KB_AFTER_ANSWER)

    # Сохраняем для навигации
    await state.update_data(last_question=question, last_grade=grade)
    await state.set_state(TaskState.waiting_for_answer)

@router.message(TaskState.waiting_for_voice)
async def process_voice_message(message: Message, state: FSMContext):
    if not message.voice:
        await message.answer("⚠️ Отправьте голосовое сообщение.")
        return

    # ... (скачивание и транскрипция как было) ...
    text = await transcribe_audio(save_path)
    os.remove(save_path)
    await message.answer(f"📝 Расшифровка: «{text}»")

    if detect_gpt_phrases(text):
        await message.answer("⚠️ Переформулируйте ответ своими словами.", reply_markup=get_main_menu())
        await state.clear()
        return

    data       = await state.get_data()
    question   = data.get("question")
    grade      = data.get("grade")
    last_score = data.get("last_score", 0.0)
    user       = await get_user_from_db(message.from_user.id)

    if not user or not grade or not question:
        await message.answer("⚠️ Нет данных для оценки.", reply_markup=get_main_menu())
        return

    feedback_raw = await evaluate_answer(question, text, user["name"])
    if not feedback_raw or "Ошибка" in feedback_raw:
        await message.answer("❌ Ошибка оценки.", reply_markup=get_main_menu())
        await state.clear()
        return

    import re
    pattern = r"Критерии:\s*(.*?)Итог:\s*([\d.]+)\s*Feedback:\s*(.*)"
    match = re.search(pattern, feedback_raw, re.DOTALL)
    if match:
        criteria = match.group(1).strip()
        try:
            new_score = float(match.group(2))
        except:
            new_score = 0.0
        feedback_text = match.group(3).strip()
    else:
        criteria = ""
        new_score = 0.0
        feedback_text = feedback_raw.strip()

    increment = new_score - last_score
    if increment > 0:
        if data.get("is_academy_task"):
            await update_academy_topic_points(message.from_user.id, data.get("selected_topic"), increment)
            await update_user_academy_points(message.from_user.id, increment)
        await update_user_points(message.from_user.id, increment)

        await update_level(message.from_user.id)
        await save_user_answer(
            user_id=message.from_user.id,
            question=question,
            answer=text,
            grade=grade,
            topic=data.get("selected_topic", "—"),
            score=new_score,
            state=state
        )
        await state.update_data(last_score=new_score)

    # Отправляем результат
    result_msg = ""
    if criteria:
        result_msg += f"<b>📊 Критерии:</b>\n{criteria}\n\n"
    result_msg += f"<b>🧮 Оценка:</b> <code>{round(new_score,2)}</code>\n\n"
    result_msg += f"<b>💬 Обратная связь:</b>\n{feedback_text}"

    await message.answer(result_msg, parse_mode="HTML", reply_markup=NAV_KB_AFTER_ANSWER)
    await state.update_data(last_question=question, last_grade=grade)
    await state.set_state(TaskState.waiting_for_answer)

# --------------------------
# Функции для работы с OpenAI
# --------------------------

async def generate_question(grade: str, topic: str, name: str) -> str:
    """
    Генерирует задание для продакта по грейду и теме.
    Особая логика для Soft skills и Управление командой.
    """
    # Специальный промпт для Soft skills
    if topic == "Soft skills":
        user_prompt = f"""
Придумай **уникальное**, практическое задание для продакт-менеджера уровня {grade} по теме «Soft skills». 
Сфокусируйся на одном из навыков: **лидерство**, **ответственность**, **разрешение конфликтов**, **внутренняя мотивация**, **рациональность**.
Формат:
1) Краткая ролевая ситуация (кто участвует, в чем проблема).
2) Конкретная задача для PM (что должен сделать, какие действия предпринять).
3) Аналитический вопрос: «Что здесь не так и почему?» или «Как улучшить ситуацию?» 
Дай только текст задания, до 800 символов, без приветствий.
        """.strip()

    # Специальный промпт для Управление командой
    elif topic == "Управление командой":
        user_prompt = f"""
Придумай **реалистичный** кейс для продакт-менеджера уровня {grade} по теме «Управление командой». 
Включи:
- Описание текущей ситуации (размер команды, роли, проект, узкие места).
- Задачу по корректировке работы команды или оптимизации ресурсов.
- Вопрос-оценку: «Какие инструменты (Scrum, Kanban и т.п.) ты внедришь и почему?» 
Дай только текст задания, до 800 символов, без вводных.
        """.strip()

    # Универсальный промпт для всех остальных тем
    else:
        user_prompt = f"""
Придумай **уникальный**, реалистичный кейс для продакт-менеджера уровня {grade} по теме «{topic}». Обязательно:
1. Укажи компанию (стартап, B2C/B2B, финтех, edtech, e-commerce и т.п.).
2. Опиши команду (размер, роли), бюджет/время, ограничения.
3. Сформулируй задачу, отражающую навык в теме «{topic}».
4. Не повторяй предыдущие примеры — каждый кейс должен быть **новым**.
5. Дай только текст задания (до 800 символов), без приветствий и списков «Пожалуйста…».
        """.strip()

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты — опытный интервьюер и наставник по продакт-менеджменту. "
                        "Генерируешь короткие (до 800 символов), но ёмкие и разнообразные кейсы. "
                        "Каждый раз сценарий должен быть новым и соответствовать теме и грейду."
                    )
                },
                {"role": "user", "content": user_prompt}
            ],
            max_tokens=350,
            temperature=0.9
        )
        text = response.choices[0].message.content.strip()
        return text[:800] if len(text) > 800 else text

    except Exception as e:
        logging.error(f"Ошибка генерации вопроса: {e}")
        return "❌ Ошибка генерации вопроса. Попробуйте чуть позже."

async def generate_academy_question(main_topic: str, subtopic: str, name: str) -> str:
    """
    Генерирует задание для ученика Академии по разделу main_topic и подтеме subtopic.
    Особая логика для Soft Skills и Управления командой, универсальный для остальных.
    """
    # Промпты для специальных категорий
    if main_topic == "softskills":
        prompt = f"""
Ты — преподаватель Академии. Придумай **практическое** задание для ученика {name} по подтеме «{subtopic}» раздела Soft Skills.
- Опиши ролевую ситуацию (контекст, роли участников).
- Укажи конкретную задачу, направленную на развитие навыка «{subtopic}».
- Добавь аналитический вопрос: «Что здесь не так и почему?» или «Как бы ты улучшил(-а) этот навык в реальной работе?». 
Только текст задания, до 800 символов, без приветствий.
        """.strip()
    elif main_topic == "team":
        prompt = f"""
Ты — преподаватель Академии. Сгенерируй **реалистичный** кейс для ученика {name} по подтеме «{subtopic}» раздела Управление командой.
- Описание команды (размер, роли, проект).
- Задача по оптимизации процессов или распределению ресурсов.
- Вопрос: «Какие инструменты (Scrum, Kanban и т.п.) ты бы предложил(-а) и почему?»
Только текст задания, до 800 символов, без вводных.
        """.strip()
    else:
        # Универсальный промпт
        prompt = f"""
Ты — преподаватель Академии. Придумай **уникальное**, тематическое задание для ученика {name} по разделу «{main_topic}» и подтеме «{subtopic}».
- Укажи контекст (компания, команда, ограничения).
- Сформулируй задачу, строго связанную с темой «{subtopic}».
- Не повторяй предыдущие примеры, каждая генерация должна быть новой.
- Только текст задания, до 800 символов, без приветствий.
        """.strip()
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": (
                    "Ты — опытный преподаватель Академии. Генерируешь понятные, реалистичные задания строго по теме, без приветствий."
                )},
                {"role": "user", "content": prompt}
            ],
            max_tokens=400,
            temperature=0.7
        )
        text = response.choices[0].message.content.strip()
        return text[:800] if len(text) > 800 else text
    except Exception as e:
        logging.error(f"Ошибка генерации задания Академии: {e}")
        return "❌ Ошибка генерации задания Академии. Попробуйте чуть позже."

async def evaluate_answer(question: str, student_answer: str, student_name: str) -> str:
    prompt = (
        f"Вопрос: {question}\n"
        f"Ответ студента: {student_answer}\n\n"
        "Проанализируй ответ пользователя по следующей схеме. "
        "Всего 5 критериев. Каждый оценивается от 0 до 0.2 баллов (шаг 0.05). "
        "Если критерий 'Соответствие вопросу' равен 0.0 — остальные не учитываются, и итоговая оценка = 0.0. "
        "Если он больше 0.0, оцени остальные 4 критерия.\n\n"
        "Критерии:\n"
        "• Соответствие вопросу\n"
        "• Полнота\n"
        "• Аргументация\n"
        "• Структура\n"
        "• Примеры\n\n"
        "Ответ строго в формате:\n\n"
        "Критерии:\n"
        "• Соответствие вопросу: <балл>\n"
        "• Полнота: <балл>\n"
        "• Аргументация: <балл>\n"
        "• Структура: <балл>\n"
        "• Примеры: <балл>\n\n"
        "Итог: <сумма баллов>\n"
        "Feedback: <текстовая обратная связь для пользователя>\n\n"
        "Поясни в Feedback, что именно не так (если есть недочёты), или похвали за хорошую работу (если всё ок)."
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
            file=audio_file,
            language="ru"
        )
    return response.text

# --------------------------
# Автостарт при любой активности вне FSM
# --------------------------

@router.message()
async def catch_all(message: Message, state: FSMContext):
    current_state = await state.get_state()
    
    if current_state is None:
        user = await get_user_from_db(message.from_user.id)

        if user:
            await state.clear()

            await message.answer("👋 Кажется, вы вернулись спустя время!", reply_markup=ReplyKeyboardRemove())
            await message.answer(
                f"🎓 Уровень: {user['level']} | ⭐ Баллы: {user['points']}\n\n"
                "Готов продолжить?",
                reply_markup=ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="🚀 Готов, погнали!")]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                )
            )
        else:
            await message.answer("👋 Привет! Давай зарегистрируемся. Как тебя зовут?")
            await state.set_state(RegisterState.name)

async def get_or_generate_analytics(user_id: int):
    async with db_pool.acquire() as conn:
        existing = await conn.fetchrow(
            "SELECT * FROM analytics WHERE user_id = $1", user_id
        )
        if existing:
            return existing

        # Примерно считаем средние значения — можно заменить на реальные вычисления
        averages = await conn.fetchrow('''
            SELECT 
                ROUND(AVG(score)::numeric, 2) as avg_score
            FROM answers
            WHERE user_id = $1
        ''', user_id)


        # Заглушка по критериям — ты можешь позже это детализировать
        analytics = {
            "tasks_done": await conn.fetchval("SELECT COUNT(*) FROM answers WHERE user_id = $1", user_id),
            "average_score": averages["avg_score"] or 0,
            "criteria_relevance": 0.18,
            "criteria_completeness": 0.14,
            "criteria_argumentation": 0.16,
            "criteria_structure": 0.11,
            "criteria_examples": 0.08,
            "percentile": 68,
            "next_target": 15,
        }

        # Сохраняем в таблицу
        await conn.execute('''
            INSERT INTO analytics (user_id, tasks_done, average_score, 
            criteria_relevance, criteria_completeness, criteria_argumentation, 
            criteria_structure, criteria_examples, percentile, next_target)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        ''', user_id, *analytics.values())

        return analytics

def format_progress_analytics(user, data):
    return (
        f"<b>📊 Твоя аналитика прогресса</b>\n\n"
        f"<b>📍 Всего заданий пройдено:</b> {data['tasks_done']}\n"
        f"<b>🎓 Текущий уровень:</b> {user['level']}\n"
        f"<b>⭐ Общий балл:</b> {round(user['points'], 2)}\n\n"
        f"🔍 <b>Критерии оценки:</b>\n\n"
        f"• <b>Соответствие вопросу:</b> {round(data['criteria_relevance'], 2)} / 0.20 — ты почти всегда в точку! 🔥\n"
        f"• <b>Полнота:</b> {round(data['criteria_completeness'], 2)} — немного не раскрываешь мысль до конца\n"
        f"• <b>Аргументация:</b> {round(data['criteria_argumentation'], 2)} — у тебя хорошие логические цепочки\n"
        f"• <b>Структура:</b> {round(data['criteria_structure'], 2)} — иногда теряется логика\n"
        f"• <b>Примеры:</b> {round(data['criteria_examples'], 2)} — добавь больше конкретики\n\n"
        f"🎯 <b>Суперсила:</b> попадание в суть задачи\n"
        f"🧱 <b>Зона роста:</b> примеры и структура\n\n"
        f"📈 <b>Ты лучше, чем {data['percentile']}% пользователей</b>\n"
        f"🧭 <b>Цель:</b> +{data['next_target']} баллов до следующего уровня 🚀\n\n"
        f"<i>📌 Обновление аналитики происходит раз в неделю</i>"
    )

def detect_gpt_phrases(text: str) -> bool:
    suspicious_phrases = re.compile(
        r"это важный аспект для рассмотрения|данный подход позволяет|"
        r"таким образом можно охарактеризовать|можно выделить несколько ключевых моментов|"
        r"рассмотрим подробнее|это свидетельствует о|необходимо подчеркнуть|"
        r"представляется логичным|в рамках данного контекста|"
        r"представим ситуацию, при которой",
        re.IGNORECASE
    )
    return bool(suspicious_phrases.search(text))

# --------------------------
# Запуск бота
# --------------------------

async def on_startup():
    await create_db_pool()
    await dp.start_polling(bot, skip_updates=True)

if __name__ == "__main__":
    print("=== Запускаем бота ===")
    asyncio.run(on_startup())
