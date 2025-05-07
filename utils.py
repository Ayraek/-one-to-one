import re
import logging
import asyncio
import openai  # просто импортируем библиотеку, без OpenAI

openai.api_key = "FAKE-KEY"  # заменим позже на реальный ключ

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
            openai.ChatCompletion.create,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты строгий преподаватель."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=450,
            temperature=0.3
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logging.error(f"Ошибка оценки ответа: {e}")
        return "❌ Ошибка оценки ответа."
