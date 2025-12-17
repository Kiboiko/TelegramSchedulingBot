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
    SELECT_MATERIALS_DATE = State()
    CONFIRM_MATERIALS_GENERATION = State()
class FinanceStates(StatesGroup):
    SELECT_PERSON = State()
    SELECT_SUBJECT = State()
    SELECT_DATE = State()
    SHOW_FINANCES = State()

class PaymentStates(StatesGroup):
    WAITING_PAYMENT = State()
    CONFIRMING_PAYMENT = State()

class AdminAssignStates(StatesGroup):
    SELECT_ROLE = State()
    SELECT_SUBJECTS = State()
    CONFIRM = State()

class AdminAddRoleStates(StatesGroup):
    INPUT_USER_NAME = State()  # Ввод ФИО пользователя
    SELECT_ROLE_TO_ADD = State()  # Выбор роли для добавления
    SELECT_SUBJECTS = State()  # Выбор предметов (для teacher/student)


class AdminRemoveRoleStates(StatesGroup):
    INPUT_USER_NAME = State()  # Ввод ФИО пользователя для поиска
    SELECT_ROLE_TO_REMOVE = State()  # Выбор роли для удаления