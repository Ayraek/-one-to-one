import os
import re
import logging
import sqlite3
import asyncio
from dotenv import load_dotenv

from openai import OpenAI

from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import (
    Message, 
    CallbackQuery,
    InlineKeyboardButton, 
    InlineKeyboardMarkup
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.fsm.state import StatesGroup, State

#####################
# Загрузка окружения
#####################

load_dotenv()
API_TOKEN = os.getenv("API_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

############################
# Настройка OpenAI клиента
############################

client = OpenAI(api_key=OPENAI_API_KEY)

##################
# Настройка логов
##################

logging.basicConfig(level=logging.INFO)

#############################
# Инициализация бота/диспетчера
#############################

bot = Bot(token=API_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()
dp.include_router(router)

#############
# Уровни
#############

LEVELS = ["Junior", "Middle", "Senior", "Head of Product", "CPO", "CEO"]

#############################
# Меню тем (после выбора грейда)
#############################

TOPICS = [
    "Гипотезы",
    "Маркетинг",
    "Метрики",
    "Управление командой",
    "Soft skills",
    "Стратегия",
    "Требования к продукту",
]

########################################
# Текст приветствия
########################################

welcome_text = (
    "💡 Добро пожаловать в \"One to One Booster bot\" — "
    "вашего личного ассистента для прокачки навыков "
    "в продакт-менеджменте!\n\nНажмите /start, чтобы начать 🔥"
)

########################################
# Главное меню
########################################

def get_main_menu():
    keyboard = [
        [InlineKeyboardButton(text="👤 Мой профиль", callback_data="profile")],
        [InlineKeyboardButton(text="📚 Получить задание", callback_data="task")],
        [InlineKeyboardButton(text="❓ Помощь", callback_data="help")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

########################################
# Меню выбора грейда
########################################

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

########################################
# Меню выбора темы
########################################

def get_topics_menu():
    """
    Показываем список тем + кнопку «Назад» (возвращаемся к выбору грейда).
    """
    buttons = []
    for topic in TOPICS:
        buttons.append([InlineKeyboardButton(text=topic, callback_data=f"topic_{topic}")])
    buttons.append([InlineKeyboardButton(text="🔙 Назад", callback_data="choose_grade")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

########################################
# Работа с базой данных
########################################

def add_user_to_db(user_id: int, username: str, name: str, age: int):
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

def get_user_from_db(user_id: int):
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
        return cursor.fetchone()

def update_user_points(user_id: int, additional_points: float):
    with sqlite3.connect('users.db') as conn:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET points = points + ? WHERE id = ?', (additional_points, user_id))
        conn.commit()

def update_level(user_id: int):
    """
    Логика перехода на следующий уровень:
    Junior -> Middle -> Senior -> Head of Product -> CPO -> CEO
    Для каждого уровня требуется 50*(index+1) баллов.
    """
    user = get_user_from_db(user_id)
    if not user:
        return
    _, username, name, age, current_level, points = user
    cur_index = LEVELS.index(current_level) if current_level in LEVELS else 0
    required_points = 50 * (cur_index + 1)

    if points >= required_points and cur_index < len(LEVELS) - 1:
        new_level = LEVELS[cur_index + 1]
        with sqlite3.connect('users.db') as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE users SET level = ? WHERE id = ?', (new_level, user[0]))
            conn.commit()
        logging.info(f"Пользователь {user[0]} повышен с {current_level} до {new_level}.")

########################################
# Состояния
########################################

class RegisterState(StatesGroup):
    name = State()
    age = State()

class TaskState(StatesGroup):
    waiting_for_answer = State()

########################################
# Команды
########################################

@router.message(lambda msg: msg.text == "/start")
async def cmd_start(message: Message, state: FSMContext):
    user = get_user_from_db(message.from_user.id)
    if user is None:
        # Показываем логотип и приветствие только новому пользователю
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
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Сколько тебе лет?")
    await state.set_state(RegisterState.age)

@router.message(RegisterState.age)
async def process_age(message: Message, state: FSMContext):
    if not message.text.isdigit():
        await message.answer("Пожалуйста, введите возраст числом (цифрами).")
        return
    data = await state.get_data()
    name = data.get("name")
    add_user_to_db(
        user_id=message.from_user.id,
        username=message.from_user.username or "",
        name=name,
        age=int(message.text)
    )
    await message.answer(f"✅ Готово, {name}! Добро пожаловать!", reply_markup=get_main_menu())
    await state.clear()

@router.message(lambda msg: msg.text == "/ping")
async def cmd_ping(message: Message):
    await message.answer("🏓 Pong!")

########################################
# Обработчики меню (CallbackQuery)
########################################

@router.callback_query(F.data == "profile")
async def profile_callback(callback: CallbackQuery):
    user = get_user_from_db(callback.from_user.id)
    if not user:
        await callback.message.edit_text(
            "🚫 Пользователь не найден. Попробуйте заново /start.",
            reply_markup=get_main_menu()
        )
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
async def help_callback(callback: CallbackQuery):
    text = (
        "ℹ️ Помощь:\n"
        "/start — начать\n"
        "📚 Получить задание — выбрать грейд и тему, затем решить кейс."
    )
    await callback.message.edit_text(text, reply_markup=get_main_menu())
    await callback.answer()

@router.callback_query(F.data == "main_menu")
async def main_menu_callback(callback: CallbackQuery):
    # Показываем профиль (или приветствие) – здесь выбрана логика: показать профиль
    user = get_user_from_db(callback.from_user.id)
    if user:
        _, username, name, age, level, points = user
        text = (
            f"<b>👤 Имя:</b> {name}\n"
            f"<b>🎂 Возраст:</b> {age}\n"
            f"<b>🎯 Уровень:</b> {level}\n"
            f"<b>⭐ Баллы:</b> {points}\n"
        )
        await callback.message.edit_text(text, parse_mode="HTML", reply_markup=get_main_menu())
    else:
        await callback.message.edit_text(
            welcome_text,
            reply_markup=get_main_menu()
        )
    await callback.answer()

@router.callback_query(F.data == "task")
async def task_callback(callback: CallbackQuery):
    # Показываем меню выбора грейда
    await callback.message.edit_text(
        "Выберите грейд, для которого хотите получить задание:",
        reply_markup=get_grades_menu()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("grade_"))
async def handle_grade_selection(callback: CallbackQuery, state: FSMContext):
    """
    Пользователь выбрал конкретный грейд.
    Показываем меню выбора темы (Гипотезы, Маркетинг и т.д.).
    """
    selected_grade = callback.data.replace("grade_", "").strip()

    user = get_user_from_db(callback.from_user.id)
    if not user:
        await callback.message.answer(
            "🚫 Пользователь не найден. Попробуйте /start",
            reply_markup=get_main_menu()
        )
        await callback.answer()
        return

    current_level = user[4]  # Колонка level
    if selected_grade != current_level:
        await callback.message.answer(
            f"🚫 Доступ запрещён! Ваш текущий уровень: {current_level}.",
            reply_markup=get_main_menu()
        )
        await callback.answer()
        return

    # Сохраняем в state текущий грейд
    await state.update_data(selected_grade=selected_grade)

    # Показываем меню тем
    await callback.message.edit_text(
        "Выберите тему для задания:",
        reply_markup=get_topics_menu()
    )
    await callback.answer()

@router.callback_query(F.data == "choose_grade")
async def back_to_grades(callback: CallbackQuery):
    """
    Возврат к выбору грейда.
    """
    await callback.message.edit_text(
        "Выберите грейд, для которого хотите получить задание:",
        reply_markup=get_grades_menu()
    )
    await callback.answer()

@router.callback_query(F.data.startswith("topic_"))
async def handle_topic_selection(callback: CallbackQuery, state: FSMContext):
    """
    Пользователь выбрал тему (Гипотезы, Маркетинг и т.д.).
    Генерируем короткий вопрос по грейду и выбранной теме.
    """
    chosen_topic = callback.data.replace("topic_", "").strip()

    data = await state.get_data()
    selected_grade = data.get("selected_grade")
    if not selected_grade:
        await callback.message.answer(
            "⚠️ Ошибка: не найден грейд. Попробуйте сначала выбрать грейд заново.",
            reply_markup=get_grades_menu()
        )
        await callback.answer()
        return

    # Генерация краткого вопроса
    question = await generate_question(selected_grade, chosen_topic)

    # Сохраняем в состоянии для дальнейшего использования
    await state.set_state(TaskState.waiting_for_answer)
    await state.update_data(question=question, grade=selected_grade, last_score=0.0)

    # Редактируем сообщение — показываем задание
    await callback.message.edit_text(
        f"💬 Задание для уровня {selected_grade} по теме «{chosen_topic}»:\n\n"
        f"{question}\n\n"
        "✍️ Напишите свой ответ сообщением."
    )
    await callback.answer()

################################################
# Обработка ответа (состояние TaskState.waiting_for_answer)
################################################

@router.message(TaskState.waiting_for_answer)
async def handle_task_answer(message: Message, state: FSMContext):
    data = await state.get_data()
    if not data:
        await message.answer("⚠️ Не найдены данные задания. Попробуйте снова.")
        return

    grade = data.get("grade")
    question = data.get("question")
    last_score = data.get("last_score", 0.0)

    user = get_user_from_db(message.from_user.id)
    if not user:
        await message.answer("🚫 Пользователь не найден. Повторите /start.")
        return

    student_name = user[2]

    # Запрос к OpenAI для оценки ответа
    feedback_raw = await evaluate_answer(question, message.text, student_name)
    logging.info(f"RAW FEEDBACK:\n{feedback_raw}")

    # Пытаемся извлечь критерии, Score и Feedback
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
        # Если формат не совпал
        criteria_block = ""
        new_score = 0.0
        feedback_text = feedback_raw.strip()

    # Если новая оценка выше предыдущей
    if new_score > last_score:
        diff = new_score - last_score
        update_user_points(message.from_user.id, diff)
        update_level(message.from_user.id)
        await state.update_data(last_score=new_score)

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

    # Если результат слишком большой – разбиваем
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

###################################
# Кнопка "Показать правильный ответ"
###################################

@router.callback_query(F.data == "show_answer")
async def show_correct_answer(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    question = data.get("last_question")
    grade = data.get("last_grade")

    if not question or not grade:
        await callback.message.answer(
            "⚠️ Ошибка: не найден вопрос для показа ответа.",
            reply_markup=get_main_menu()
        )
        await callback.answer()
        return

    correct = await generate_correct_answer(question, grade)
    await callback.message.answer(
        f"✅ Эталонный ответ уровня {grade}:\n\n{correct}",
        parse_mode="HTML",
        reply_markup=get_main_menu()
    )
    await callback.answer()

###################################
# Кнопка "Попробовать снова" (retry)
###################################

@router.callback_query(F.data == "retry")
async def retry_question(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    question = data.get("last_question")
    grade = data.get("last_grade")
    if not question or not grade:
        await callback.message.answer(
            "⚠️ Ошибка: нет сохранённого задания.",
            reply_markup=get_main_menu()
        )
        await callback.answer()
        return

    await state.set_state(TaskState.waiting_for_answer)
    await state.update_data(question=question, grade=grade, last_score=data.get("last_score", 0.0))

    await callback.message.answer(
        f"✍️ Повторите, пожалуйста, ответ на вопрос уровня {grade}:\n\n{question}"
    )
    await callback.answer()

###################################
# OpenAI функции
###################################

async def generate_question(grade: str, topic: str) -> str:
    """
    Генерирует краткий вопрос (до ~350 символов) для продакт-менеджера уровня {grade} 
    по теме {topic}, без использования звёздочек.
    """
    prompt = (
        f"Ты опытный продакт-менеджер. Сформулируй короткий, точный вопрос для уровня {grade} "
        f"по теме «{topic}». Не более 350 символов, только самое важное. "
        "Избегай звёздочек, можешь применять эмодзи. Не обрывай фразу в конце."
    )
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Ты генерируешь краткие вопросы для продакт-менеджеров. "
                        "Не используй звёздочки(*). Размер текста не должен превышать 350 символов."
                    )
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=200,
            temperature=0.6
        )
        question_text = response.choices[0].message.content.strip()
        # Если вопрос длиннее 350 символов, обрезаем
        if len(question_text) > 350:
            question_text = question_text[:347] + "..."
        return question_text
    except Exception as e:
        logging.error(f"Ошибка генерации вопроса: {e}")
        return "❌ Ошибка генерации вопроса."

async def evaluate_answer(question: str, student_answer: str, student_name: str) -> str:
    """
    Оцениваем ответ студента, используя формат:
    Критерии:
    ...
    Score: <число>
    Feedback: Ваш ответ...
    """
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
        "Определи итоговую оценку (Score) от 0.0 до 1.0. Если ответ частично верный, используй дробное число (например, 0.5).\n"
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
                {
                    "role": "system",
                    "content": "Ты преподаватель, строго оценивающий ответы по формату. Не добавляй лишних слов."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=450,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Ошибка оценки ответа: {e}")
        return "❌ Ошибка оценки ответа."

async def generate_correct_answer(question: str, grade: str) -> str:
    """
    Генерация "эталонного" ответа:
    """
    prompt = (
        f"Ты опытный преподаватель продакт-менеджмента. Дай подробный ответ на вопрос уровня {grade}.\n\n"
        f"Вопрос: {question}\n\n"
        "Объясни ключевые моменты и приведи примеры, почему ответ правильный. "
        "Отвечай от первого лица, обращаясь к студенту как 'Ваш ответ...'. "
        "Не используй звёздочки(*)."
    )
    try:
        response = await asyncio.to_thread(
            client.chat.completions.create,
            model="gpt-3.5-turbo",
            messages=[
                {
                    "role": "system",
                    "content": "Ты генерируешь подробные ответы для студентов. Без звёздочек."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            max_tokens=300,
            temperature=0.7
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Ошибка генерации эталонного ответа: {e}")
        return "❌ Ошибка генерации эталонного ответа."

###############################
# Запуск бота
###############################

if __name__ == "__main__":
    asyncio.run(dp.start_polling(bot, skip_updates=True))
