import sys
import os
import pytest
from unittest.mock import patch, MagicMock

# Добавляем текущую директорию в sys.path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from ai_utils import generate_question, generate_correct_answer

@pytest.mark.asyncio
@patch("openai.ChatCompletion.create")
async def test_generate_question(mock_create):
    mock_create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Тестовое задание по теме управления"))]
    )
    result = await generate_question("Middle", "Управление командой", "Антон")
    assert "задание" in result.lower() or "управление" in result.lower()

@pytest.mark.asyncio
@patch("openai.ChatCompletion.create")
async def test_generate_correct_answer(mock_create):
    mock_create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Это эталонный ответ"))]
    )
    result = await generate_correct_answer("Что такое MVP?", "Junior")
    assert "эталонный" in result.lower() or "ответ" in result.lower()

@pytest.mark.asyncio
@patch("openai.ChatCompletion.create")
async def test_generate_question_soft_skills(mock_create):
    mock_create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Ситуация про внутреннюю мотивацию"))]
    )
    result = await generate_question("Senior", "Soft skills", "Антон")
    assert "мотивация" in result.lower() or "ситуация" in result.lower()


@pytest.mark.asyncio
@patch("openai.ChatCompletion.create")
async def test_generate_question_generic(mock_create):
    mock_create.return_value = MagicMock(
        choices=[MagicMock(message=MagicMock(content="Кейс по теме Маркетинг с ограничениями"))]
    )
    result = await generate_question("Junior", "Маркетинг", "Антон")
    assert "маркетинг" in result.lower() or "ограничения" in result.lower()