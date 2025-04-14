import time
from aiogram import BaseMiddleware, types
from aiogram.fsm.context import FSMContext
import logging

class InactivityMiddleware(BaseMiddleware):
    """
    Middleware, которое проверяет, не прошло ли 15 минут с последнего взаимодействия.
    Если прошло – очищает состояние и отправляет сообщение о перезапуске.
    """
    async def __call__(self, handler, event, data):
        state: FSMContext = data.get("state")
        now = time.time()

        if state:
            state_data = await state.get_data()
            last_active = state_data.get("last_active")
            if last_active is None or (now - last_active > 900):  # 900 секунд = 15 минут
                logging.info("[InactivityMiddleware] Время бездействия истекло. Очищаем состояние.")
                await state.clear()
                if isinstance(event, types.Message):
                    await event.answer("🔄 Прошло больше 15 минут без взаимодействия. Начнём сначала. Нажмите /start, чтобы перезапустить.")
                return  # Прерываем выполнение дальнейших обработчиков
            else:
                # Обновляем время активности пользователя
                await state.update_data(last_active=now)
        return await handler(event, data)
