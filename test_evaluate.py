import pytest
from unittest.mock import patch, MagicMock
from utils import evaluate_answer

from bot import evaluate_answer  # или из utils, если ты туда вынес

@pytest.mark.asyncio
@patch("bot.client.chat.completions.create")  # ← подменяем вызов OpenAI
async def test_evaluate_answer(mock_create):
    # Мокаем возвращаемый ответ OpenAI
    mock_create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Критерии:\n• Соответствие вопросу: 0.2\nИтог: 1.0\nFeedback: отлично"))]
    )

    result = await evaluate_answer("Что такое MVP?", "Это минимальный продукт", "Антон")

    # Проверяем, что результат содержит ключевые части
    assert "Критерии" in result
    assert "Feedback" in result
    assert "Итог" in result