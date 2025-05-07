import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, Voice
from bot import handle_task_answer, process_voice_message
from bot import TaskState
from unittest.mock import ANY
from aiogram.types import CallbackQuery
from bot import cb_show, cb_next

@pytest.mark.asyncio
@patch("bot.bot.send_chat_action", new_callable=AsyncMock)
@patch("bot.evaluate_answer", return_value="Критерии:\n• Соответствие вопросу: 0.2\nИтог: 0.2\nFeedback: Хорошо")
@patch("bot.get_user_from_db", return_value={"name": "Антон"})
@patch("bot.generate_correct_answer", return_value="Правильный ответ")
@patch("bot.detect_gpt_phrases", return_value=False)
@patch("bot.client.embeddings.create")
@patch("bot.update_user_points")
@patch("bot.update_level")
@patch("bot.save_user_answer")
@patch("bot.update_academy_topic_points")
@patch("bot.update_user_academy_points")
async def test_handle_task_answer(
    mock_update_academy, mock_update_user_academy, mock_save, mock_level, mock_points,
    mock_emb, mock_detect, mock_user, mock_eval, mock_correct, mock_send_action
):
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {"grade": "Junior", "question": "Что такое JTBD?", "last_score": 0.0}

    message = AsyncMock()
    message.text = "Это подход..."
    message.answer = AsyncMock()
    message.chat = MagicMock()
    message.chat.id = 1

    await handle_task_answer(message, state)

    assert message.answer.called


@pytest.mark.asyncio
@patch("bot.bot.send_chat_action", new_callable=AsyncMock)
@patch("bot.evaluate_answer", return_value="Критерии:\n• Соответствие вопросу: 0.2\nИтог: 0.2\nFeedback: Хорошо")
@patch("bot.get_user_from_db", return_value={"name": "Антон"})
@patch("bot.detect_gpt_phrases", return_value=False)
@patch("bot.transcribe_audio", return_value="Это голосовой ответ")
@patch("bot.bot.get_file")
@patch("bot.bot.download_file")
@patch("bot.generate_correct_answer", return_value="Правильный ответ")
@patch("bot.client.embeddings.create")
@patch("bot.update_user_points")
@patch("bot.update_level")
@patch("bot.save_user_answer")
@patch("bot.update_academy_topic_points")
@patch("bot.update_user_academy_points")
async def test_process_voice_message(
    mock_update_academy, mock_update_user_academy, mock_save, mock_level, mock_points,
    mock_emb, mock_correct, mock_download, mock_get_file, mock_transcribe,
    mock_detect, mock_user, mock_eval, mock_send_action
):
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {"grade": "Middle", "question": "Что такое CJM?", "last_score": 0.0}
    voice = MagicMock(spec=Voice)
    voice.file_id = "test_id"
    message = AsyncMock()
    message.voice = voice
    message.answer = AsyncMock()
    message.chat = MagicMock()
    message.chat.id = 1

    await process_voice_message(message, state)

    assert message.answer.called


@pytest.mark.asyncio
@patch("bot.bot.send_chat_action", new_callable=AsyncMock)
async def test_handle_text_answer_button(mock_send_action):
    state = AsyncMock(spec=FSMContext)
    state.get_state.return_value = TaskState.waiting_for_answer

    message = AsyncMock()
    message.text = "✍️ Ответить текстом"
    message.answer = AsyncMock()
    message.chat = MagicMock()
    message.chat.id = 1

    await handle_task_answer(message, state)

    message.answer.assert_called_with("✏️ Напишите ответ текстом.", reply_markup=ANY)


@pytest.mark.asyncio
@patch("bot.bot.send_chat_action", new_callable=AsyncMock)
async def test_handle_voice_answer_button(mock_send_action):
    state = AsyncMock(spec=FSMContext)
    state.get_state.return_value = TaskState.waiting_for_answer

    message = AsyncMock()
    message.text = "🎤 Ответить голосом"
    message.answer = AsyncMock()
    message.chat = MagicMock()
    message.chat.id = 1

    await handle_task_answer(message, state)

    message.answer.assert_called_with("🎤 Отправьте голосовое сообщение.", reply_markup=ANY)
    state.set_state.assert_called_with(TaskState.waiting_for_voice)

@pytest.mark.asyncio
@patch("bot.generate_correct_answer", return_value="Эталонный ответ")
async def test_cb_show_correct_answer(mock_gen_correct):
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {"last_question": "Что такое CJM?", "last_grade": "Middle"}

    message = AsyncMock()
    callback = AsyncMock(spec=CallbackQuery)
    callback.message = message
    callback.answer = AsyncMock()

    await cb_show(callback, state)

    mock_gen_correct.assert_called_once_with("Что такое CJM?", "Middle")
    message.edit_text.assert_called_once()
    callback.answer.assert_called_once()

@pytest.mark.asyncio
@patch("bot.generate_question", return_value="Новый вопрос")
@patch("bot.get_user_from_db", return_value={"name": "Антон"})
async def test_cb_next_generates_new_question(mock_user, mock_gen):
    state = AsyncMock(spec=FSMContext)
    state.get_data.return_value = {
        "grade": "Junior", "selected_topic": "Маркетинг", "is_academy_task": False
    }

    message = AsyncMock()
    callback = AsyncMock(spec=CallbackQuery)
    callback.message = message
    callback.from_user = AsyncMock()
    callback.from_user.id = 12345
    callback.answer = AsyncMock()

    await cb_next(callback, state)

    mock_gen.assert_called_once_with("Junior", "Маркетинг", "Антон")
    message.edit_text.assert_called_once()
    callback.answer.assert_called_once()
