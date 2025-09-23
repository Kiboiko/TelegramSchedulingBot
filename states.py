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

    SELECT_POSSIBILITY_TIME_RANGE = State()
    SELECT_POSSIBILITY_DATE = State()
    SELECT_POSSIBILITY_START_TIME = State()
    SELECT_POSSIBILITY_END_TIME = State()
    INPUT_MIN_DURATION = State()
    INPUT_MAX_DURATION = State()
    INPUT_CONFIRMATION_TIME = State()