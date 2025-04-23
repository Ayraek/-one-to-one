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
    Message, CallbackQuery,
    InlineKeyboardButton, InlineKeyboardMarkup,
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

        text = (
            f"<b>👤 Имя:</b> {name}\n"
            f"<b>🎂 Возраст:</b> {age}\n"
            f"<b>🎯 Уровень:</b> {level}\n"
            f"<b>⭐ Баллы:</b> {round(points, 2)}\n\n"
            f"<b>🏆 Рейтинг:</b> {rank}-е место\n\n"
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
    await callback.message.edit_text(
        "🚀 Вы выбрали обучение с 0 до Junior/Middle. Здесь скоро появится программа и задания.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
    )
    await callback.answer()

@router.callback_query(F.data == "track_senior")
async def handle_senior_track(callback: CallbackQuery):
    await callback.message.edit_text(
        "🧠 Вы выбрали Senior-трек. Здесь скоро появится программа и задания.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="main_menu")]
        ])
    )
    await callback.answer()

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

@router.callback_query(F.data=="nav_show")
async def cb_show(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    q, g = data.get("last_question"), data.get("last_grade")
    if not q or not g:
        return await call.answer("Нет активного задания", show_alert=True)
    correct = await generate_correct_answer(q, g)
    kb = InlineKeyboardMarkup(inline_keyboard=[
       [InlineKeyboardButton(text="➡️ Следующий вопрос", callback_data="nav_next")],
       [InlineKeyboardButton(text="🏠 Главное меню", callback_data="nav_main")]
    ])

    await call.message.edit_text(f"✅ Эталонный ответ:\n\n{correct}", parse_mode="HTML", reply_markup=kb)
    await call.answer()

@router.callback_query(F.data=="nav_next")
async def cb_next(call: CallbackQuery, state: FSMContext):
    data  = await state.get_data()
    grade = data.get("grade"); topic=data.get("selected_topic")
    user  = await get_user_from_db(call.from_user.id)
    if not grade or not topic or not user:
        return await call.answer("Нет данных для нового вопроса", show_alert=True)
    new_q = await generate_question(grade, topic, user["name"])
    await state.update_data(
    question=new_q,
    last_score=0.0,
    grade=grade,
    selected_topic=topic
)
    kb = InlineKeyboardMarkup(inline_keyboard=[
      [InlineKeyboardButton(text="✍️ Ответить текстом", callback_data="start_answer")],
      [InlineKeyboardButton(text="🎤 Ответить голосом", callback_data="start_voice")],
      [InlineKeyboardButton(text="🏠 Главное меню", callback_data="nav_main")],
    ])

    await call.message.edit_text(f"Новый вопрос:\n\n{new_q}", reply_markup=kb)
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
    user = await get_user_from_db(message.from_user.id)
    name = user["name"] if user else "кандидат"

    if not question:
        await message.answer("⚠️ Нет активного вопроса для уточнения. Сначала получите задание.")
        await state.clear()
        return

    clarification_prompt = (
        f"Вопрос: {question}\n"
        f"Уточнение от кандидата {name}:\n{message.text.strip()}\n\n"
        "Отвечай дружелюбно, по-человечески, как будто это чат между коллегами. "
        "Если вопрос непонятен — мягко уточни. Если просит пример — приведи. "
        "Если путается — переформулируй задание. Без приветствий, сразу к сути."
    )

    try:
        clarification_response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты наставник на симуляторе собеседований. Не решай задачу за кандидата. Отвечай как человек в чате: помоги понять задание, разъясни формулировку, но не подсказывай готовый ответ. Без приветствий, строго по теме, дружелюбно и понятно. Если кандидат запутался — переформулируй задание. Если уточнение не по делу — мягко направь обратно к сути."
                        "Отвечай как человек в Slack или Telegram: дружелюбно, понятно, с примерами. "
                        "Если вопрос не по теме — мягко направь. "
                        "Если пользователь запутался — переформулируй задание. "
                        "Будь простым, но профессиональным. Без приветствий, переходи сразу к сути."
                    )
                },
                {"role": "user", "content": clarification_prompt}
            ],
            max_tokens=200,
            temperature=0.5
        )
        reply = clarification_response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Ошибка при уточнении: {e}")
        reply = "❌ Не удалось получить ответ на уточнение. Попробуйте снова."

    reply_keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✍️ Ответить текстом"), KeyboardButton(text="🎤 Ответить голосом")],
            [KeyboardButton(text="🏠 Главное меню")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )

    await message.answer(
        f"📎 Уточнение:\n{reply}\n\nЧто делаем дальше?",
        reply_markup=reply_keyboard
    )
    await state.set_state(TaskState.waiting_for_answer)

@router.message(
    TaskState.waiting_for_answer,
    lambda m: m.text in ["➡️ Следующий вопрос", "✅ Показать правильный ответ", "🏠 Главное меню"]
)
async def handle_answer_navigation(message: Message, state: FSMContext):
    ...

    text = message.text
    data = await state.get_data()
    user = await get_user_from_db(message.from_user.id)

    # 1) Главное меню
    if text == "🏠 Главное меню":
        await state.clear()
        return await message.answer("Вы вернулись в главное меню:", reply_markup=get_main_menu())

    # 2) Показать правильный ответ
    if text == "✅ Показать правильный ответ":
        last_q = data.get("last_question"); last_g = data.get("last_grade")
        if not last_q or not last_g:
            await state.clear()
            return await message.answer("⚠️ Сейчас нет активного задания.", reply_markup=get_main_menu())
        correct = await generate_correct_answer(last_q, last_g)
        kb = ReplyKeyboardMarkup([[KeyboardButton("➡️ Следующий вопрос")],
                                  [KeyboardButton("🏠 Главное меню")]],
                                  resize_keyboard=True, one_time_keyboard=True)
        return await message.answer(f"✅ Эталонный ответ уровня {last_g}:\n\n{correct}",
                                    parse_mode="HTML", reply_markup=kb)

    # 3) Следующий вопрос
    if text == "➡️ Следующий вопрос":
        grade = data.get("grade"); topic = data.get("selected_topic")
        if not grade or not topic or not user:
            return await message.answer("⚠️ Ошибка: не найдены нужные данные.", reply_markup=get_main_menu())
        new_q = await generate_question(grade, topic, user["name"])
        await state.update_data(question=new_q, last_score=0.0)
        await state.set_state(TaskState.waiting_for_answer)
        kb = ReplyKeyboardMarkup([
                [KeyboardButton("✍️ Ответить текстом"), KeyboardButton("🎤 Ответить голосом")],
                [KeyboardButton("❓ Уточнить"), KeyboardButton("🏠 Главное меню")]
            ], resize_keyboard=True, one_time_keyboard=True)
        return await message.answer(f"Новый вопрос для уровня {grade} по теме «{topic}»:\n\n{new_q}",
                                    reply_markup=kb)

    
# --------------------------
# Общий обработчик для TaskState.waiting_for_answer
# --------------------------

@router.message(
    TaskState.waiting_for_answer,
    lambda m: m.text not in ["➡️ Следующий вопрос", "✅ Показать правильный ответ", "🏠 Главное меню"]
)
async def handle_task_answer(message: Message, state: FSMContext):
    text = message.text.strip()
    
    if text in ["➡️ Следующий вопрос", "✅ Показать правильный ответ", "🏠 Главное меню"]:
        return
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

    if text == "✍️ Ответить текстом":
        logging.info("[DEBUG] Пользователь выбрал '✍️ Ответить текстом'")
        await state.set_state(TaskState.waiting_for_answer)
        await message.answer("✏️ Напишите, пожалуйста, свой ответ.", reply_markup=types.ReplyKeyboardRemove())
        return

    if text == "🎤 Ответить голосом":
        logging.info("[DEBUG] Пользователь выбрал '🎤 Ответить голосом'")
        await state.set_state(TaskState.waiting_for_voice)
        await message.answer("🎤 Пожалуйста, отправьте голосовое сообщение с вашим ответом.", reply_markup=types.ReplyKeyboardRemove())
        return

    if text in ["❓ Уточнить", "❓ Уточнить по вопросу"]:
        logging.info("[DEBUG] Пользователь нажал '❓ Уточнить'")
        await state.set_state(TaskState.waiting_for_clarification)
        await message.answer("✏️ Напишите, что именно хотите уточнить по заданию:", reply_markup=types.ReplyKeyboardRemove())
        return

    # Основная обработка ответа
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

    # Проверка на GPT-шаблонные фразы
    if detect_gpt_phrases(text):
        await message.answer(
            "⚠️ Похоже, что ваш ответ содержит шаблонные фразы. "
            "Постарайтесь переформулировать своими словами, чтобы получить честную оценку."
        )
        return

    # Оценка ответа
    student_name = user["name"]
    logging.info(f"[DEBUG] Оцениваем ответ для вопроса: {repr(question)} пользователя: {student_name}")
    feedback_raw = await evaluate_answer(question, text, student_name)
    logging.info(f"[DEBUG] RAW FEEDBACK:\n{feedback_raw}")

    if not feedback_raw or "Ошибка" in feedback_raw:
        await message.answer(
            "❌ Произошла ошибка при оценке ответа. Попробуйте снова или вернитесь в главное меню.",
            reply_markup=get_main_menu()
        )
        await state.clear()
        return

    import re
    pattern = r"Критерии:\s*(.*?)Итог:\s*([\d.]+)\s*Feedback:\s*(.*)"
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

    # Собираем ответ
    result_msg = ""
    if criteria_block:
        result_msg += f"<b>📊 Критерии:</b>\n{criteria_block}\n\n"
    result_msg += f"<b>🧮 Оценка (Score):</b> <code>{round(new_score, 2)}</code>\n\n"
    result_msg += f"<b>💬 Обратная связь (Feedback):</b>\n{feedback_text}"

    inline_nav = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="➡️ Следующий вопрос", callback_data="nav_next")],
    [InlineKeyboardButton(text="✅ Показать правильный ответ", callback_data="nav_show")],
    [InlineKeyboardButton(text="🏠 Главное меню", callback_data="nav_main")],
])
    await message.answer(result_msg, parse_mode="HTML", reply_markup=inline_nav)
    await state.update_data(last_question=question, last_grade=grade)
    await state.set_state(TaskState.waiting_for_answer)


@router.message(TaskState.waiting_for_voice)
async def process_voice_message(message: Message, state: FSMContext):
    text = message.text.strip() if message.text else ""

    # Проверка на наличие голосового сообщения
    if not message.voice:
        await message.answer("⚠️ Пожалуйста, отправьте именно голосовое сообщение.")
        return

    # Обработка файла
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

    # Проверка на шаблонные GPT-фразы (после голосовой расшифровки)
    if detect_gpt_phrases(text):
        await message.answer(
        "⚠️ Похоже, что ваш голосовой ответ содержит шаблонные GPT-фразы. "
        "Попробуйте переформулировать своими словами, чтобы получить более точную и честную оценку.",
        reply_markup=get_main_menu()
    )
        await state.clear()
        return

    # Оценка
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
        await message.answer("❌ Ошибка при оценке ответа. Попробуйте снова.", reply_markup=get_main_menu())
        await state.clear()
        return

    pattern = r"Критерии:\s*(.*?)Итог:\s*([\d.]+)\s*Feedback:\s*(.*)"
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

    await message.answer(result_msg, parse_mode="HTML", reply_markup=ReplyKeyboardRemove())
    await message.answer("👇 Что делаем дальше?", reply_markup=kb)
    await state.update_data(last_question=question, last_grade=grade)
    await state.set_state(TaskState.waiting_for_answer) 

# --------------------------
# Функции для работы с OpenAI
# --------------------------

async def generate_question(grade: str, topic: str, name: str) -> str:
    prompt = (
        f"Придумай задачу для продакт-менеджера уровня {grade} по теме {topic}. "
        f"Задача должна быть в формате реального кейса, с цифрами, ограничениями, вводной. "
        f"Добавь немного контекста: кто продукт, какая компания, на каком этапе развития продукт. "
        f"Формулировка — не сухая, а дружелюбная, как будто ты даёшь задание коллеге по имени {name}. "
        f"Максимум 800 символов."
    )

    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": (
                    "Ты опытный интервьюер по найму продакт-менеджеров. "
                    "Твоя задача — придумывать живые, реалистичные, полезные кейсы. "
                    "Формулируй как человек: с теплотой, но профессионально. Без приветствий."
                )},
                {"role": "user", "content": prompt}
            ],
            max_tokens=350,
            temperature=0.8
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
    asyncio.run(on_startup())
