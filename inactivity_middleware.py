import time
import logging
from aiogram import BaseMiddleware, types, Bot
from aiogram.fsm.context import FSMContext

class InactivityMiddleware(BaseMiddleware):
    def __init__(self, timeout_seconds=900):
        super().__init__()
        self.timeout = timeout_seconds  # 900 секунд = 15 минут

    async def __call__(self, handler, event, data):
        state: FSMContext = data.get("state")
        bot: Bot = data.get("bot")
        now = time.time()

        if state:
            state_data = await state.get_data()
            last_active = state_data.get("last_active")
            # Если время последней активности не установлено, установим его сейчас
            if last_active is None:
                await state.update_data(last_active=now)
            # Если прошло больше 15 минут
            elif now - last_active > self.timeout:
                logging.info("[InactivityMiddleware] 15 минут бездействия – очищаем состояние и удаляем сообщения бота.")

                # Удаляем сообщения бота
                bot_messages = state_data.get("bot_messages", [])
                for msg_id in bot_messages:
                    try:
                        # Определяем chat_id (если событие Message или CallbackQuery)
                        if isinstance(event, types.Message):
                            chat_id = event.chat.id
                        elif isinstance(event, types.CallbackQuery):
                            chat_id = event.message.chat.id
                        else:
                            continue
                        await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                    except Exception as e:
                        logging.warning(f"[InactivityMiddleware] Не удалось удалить сообщение {msg_id}: {e}")

                # Очищаем состояние (удаляем всю информацию о диалоге)
                await state.clear()

                # Отправляем новое приветственное сообщение с кнопкой "Начать обучение"
                keyboard = types.ReplyKeyboardMarkup(
                    keyboard=[[types.KeyboardButton(text="Начать обучение")]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                )

                if isinstance(event, types.Message):
                    await event.answer("🔄 Прошло больше 15 минут без взаимодействия. История очищена.\nНажмите «Начать обучение» для нового старта.", reply_markup=keyboard)
                elif isinstance(event, types.CallbackQuery):
                    await event.message.answer("🔄 Прошло больше 15 минут без взаимодействия. История очищена.\nНажмите «Начать обучение» для нового старта.", reply_markup=keyboard)
                return  # Прерываем дальнейшую обработку события

            else:
                # Если время не истекло – обновляем время последней активности
                await state.update_data(last_active=now)

        return await handler(event, data)
