from aiogram.fsm.state import StatesGroup, State

class TaskState(StatesGroup):
    waiting_for_answer = State()
    waiting_for_voice = State()