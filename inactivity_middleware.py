import time
import logging
from aiogram import BaseMiddleware, types, Bot
from aiogram.fsm.context import FSMContext

class InactivityMiddleware(BaseMiddleware):
    def __init__(self, timeout_seconds=900):
        super().__init__()
        self.timeout = timeout_seconds  # по умолчанию 900 секунд = 15 минут

    async def __call__(self, handler, event, data):
        state: FSMContext = data.get("state")
        bot: Bot = data.get("bot")  # Получаем объект бота из контекста
        now = time.time()

        if not state:
            return await handler(event, data)

        # Получаем данные состояния
        state_data = await state.get_data()
        last_active = state_data.get("last_active")

        # Сколько времени прошло с момента последней активности?
        if last_active is None:
            # Если мы не знаем последнее время — устанавливаем его прямо сейчас
            await state.update_data(last_active=now)
            return await handler(event, data)

        # Если прошло больше 15 минут
        if now - last_active > self.timeout:
            logging.info("[InactivityMiddleware] 15 мин. бездействия. Очищаем состояние и удаляем сообщения бота.")

            # 1) Удаляем бот-сообщения
            bot_messages = state_data.get("bot_messages", [])
            for msg_id in bot_messages:
                try:
                    # Тип события может быть Message или CallbackQuery; определим chat_id
                    if isinstance(event, types.Message):
                        chat_id = event.chat.id
                    elif isinstance(event, types.CallbackQuery):
                        chat_id = event.message.chat.id
                    else:
                        continue
                    await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                except Exception as e:
                    logging.warning(f"Не удалось удалить сообщение {msg_id}: {e}")

            # 2) Очищаем всё состояние
            await state.clear()

            # 3) Отправляем приветственное сообщение. Например, просим /start:
            if isinstance(event, types.Message):
                await event.answer(
                    "🔄 Прошло больше 15 минут. История очищена.\nНажмите /start, чтобы начать заново."
                )
            elif isinstance(event, types.CallbackQuery):
                await event.message.answer(
                    "🔄 Прошло больше 15 минут. История очищена.\nНажмите /start, чтобы начать заново."
                )
            return  # не вызываем остальные хендлеры
        else:
            # Обновляем время последней активности
            await state.update_data(last_active=now)

        # Если всё ок, пропускаем событие дальше
        return await handler(event, data)
