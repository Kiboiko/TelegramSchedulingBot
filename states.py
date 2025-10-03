# states.py
from aiogram.fsm.state import State, StatesGroup

class BookingStates(StatesGroup):
    SELECT_ROLE = State()
    INPUT_NAME = State()
    SELECT_SUBJECT = State()
    SELECT_DATE = State()
    SELECT_TIME_RANGE = State()
    CONFIRMATION = State()
    SELECT_CHILD = State()
    PARENT_SELECT_CHILD = State()
    SELECT_SCHEDULE_DATE = State()
    CONFIRM_SCHEDULE = State()

class FinanceStates(StatesGroup):
    SELECT_SUBJECT = State()
    SELECT_DATE = State()
    SHOW_FINANCES = State()