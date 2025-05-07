import pytest
from unittest.mock import patch, MagicMock
from ai_utils import evaluate_answer  # ← правильно!

@pytest.mark.asyncio
@patch("openai.ChatCompletion.create")  # ← правильно!
async def test_evaluate_answer(mock_create):
    mock_create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Критерии:\n• Соответствие вопросу: 0.2\nИтог: 1.0\nFeedback: отлично"))]
    )

    result = await evaluate_answer("Что такое MVP?", "Это минимальный продукт", "Антон")

    assert "Критерии" in result
    assert "Feedback" in result
    assert "Итог" in result
