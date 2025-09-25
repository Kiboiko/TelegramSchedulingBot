# states.py
from aiogram.fsm.state import State, StatesGroup

# states.py - ДОБАВЛЯЕМ НОВЫЕ СОСТОЯНИЯ

class BookingStates(StatesGroup):
    # Существующие состояния...
    INPUT_NAME = State()
    SELECT_ROLE = State()
    SELECT_SUBJECT = State()
    SELECT_DATE = State()
    SELECT_TIME_RANGE = State()
    CONFIRMATION = State()
    PARENT_SELECT_CHILD = State()
    
    # Новые состояния для системы возможностей
    INPUT_NAME_FOR_POSSIBILITY = State()
    SELECT_POSSIBILITY_ROLE = State()
    SELECT_POSSIBILITY_SUBJECT = State()
    PARENT_SELECT_POSSIBILITY_CHILD = State()
    SELECT_POSSIBILITY_DATE = State()
    SELECT_POSSIBILITY_TIME_RANGE = State()
    SELECT_POSSIBILITY_START_TIME = State()
    SELECT_POSSIBILITY_END_TIME = State()
    INPUT_MIN_DURATION = State()
    INPUT_MAX_DURATION = State()
    INPUT_CONFIRMATION_TIME = State()
    
    # Состояния для составления расписания
    SELECT_SCHEDULE_DATE = State()
    CONFIRM_SCHEDULE = State()