import asyncio
import openai
import logging

# Установите уровень логирования, чтобы видеть подробные сообщения в консоли
logging.basicConfig(level=logging.INFO)

# Задайте свой API-ключ OpenAI (замени строку ниже своим реальным ключом)
openai.api_key = "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"  # Замените "YOUR_OPENAI_API_KEY" на свой ключ

async def test_generation():
    # Создаем текст запроса, который будет отправлен OpenAI
    prompt = "Сгенерируй реалистичный вопрос для продакт-менеджера уровня Junior. Вопрос должен быть понятным и конкретным."
    
    try:
        # Здесь мы используем метод ChatCompletion для генерации вопроса
        response = await asyncio.to_thread(
            openai.ChatCompletion.create,
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "Ты помощник, который генерирует вопросы для продакт-менеджеров."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=100,
            temperature=0.7
        )
        # Логируем полный ответ для отладки
        logging.info(f"Ответ от OpenAI: {response}")
        # Извлекаем сгенерированный вопрос
        question = response.choices[0].message.content.strip()
        print("Сгенерированный вопрос:")
        print(question)
    except Exception as e:
        logging.error(f"Ошибка: {e}")

# Запускаем функцию тестирования
asyncio.run(test_generation())
