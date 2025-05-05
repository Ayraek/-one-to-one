import time
import logging
from aiogram import BaseMiddleware, types, Bot
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext

class InactivityMiddleware(BaseMiddleware):
    def __init__(self, timeout_seconds: int = 7200):
        super().__init__()
        self.timeout = timeout_seconds  # 7200 секунд = 2 часа

    async def __call__(self, handler, event, data):
        state: FSMContext = data.get("state")
        bot: Bot = data.get("bot")
        now = time.time()

        if state:
            state_data = await state.get_data()
            last_active = state_data.get("last_active")

            # Если первый раз — просто сохраняем время
            if last_active is None:
                await state.update_data(last_active=now)

            # Если бездействие больше таймаута
            elif now - last_active > self.timeout:
                logging.info(f"[InactivityMiddleware] Более {self.timeout} сек бездействия — очищаем состояние.")

                # Очищаем историю бота
                bot_messages = state_data.get("bot_messages", [])
                for msg_id in bot_messages:
                    try:
                        if isinstance(event, types.Message):
                            chat_id = event.chat.id
                        elif isinstance(event, types.CallbackQuery):
                            chat_id = event.message.chat.id
                        else:
                            continue
                        await bot.delete_message(chat_id=chat_id, message_id=msg_id)
                    except Exception as e:
                        logging.warning(f"[InactivityMiddleware] Не удалось удалить сообщение {msg_id}: {e}")

                # Сброс состояния
                await state.clear()

                # Новый стартовый экран
                keyboard = ReplyKeyboardMarkup(
                    keyboard=[[KeyboardButton(text="🚀 Готов, погнали!")]],
                    resize_keyboard=True,
                    one_time_keyboard=True
                )

                text = (
                    f"🔄 Прошло более 2 часов бездействия. История очищена.\n"
                    "Нажмите «🚀 Готов, погнали!» для нового старта."
                )

                # Отправляем сообщение-приглашение
                if isinstance(event, types.Message):
                    await event.answer(text, reply_markup=keyboard)
                elif isinstance(event, types.CallbackQuery):
                    await event.message.answer(text, reply_markup=keyboard)

                # Прерываем основной хэндлер — дальше это событие не пойдёт
                return

            else:
                # Обновляем время последней активности
                await state.update_data(last_active=now)

        # Если всё в порядке — передаём управление дальше
        return await handler(event, data)
