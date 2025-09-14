from aiogram import types, F
from aiogram.fsm.context import FSMContext
from ..keyboards.main_menu import generate_main_menu_keyboard
from ..states import BookingStates


async def cmd_start(message: types.Message, state: FSMContext, storage):
    user_id = message.from_user.id
    user_name = storage.get_user_name(user_id)

    menu = generate_main_menu_keyboard(storage.get_user_roles(user_id), is_admin(user_id))

    if user_name:
        await message.answer(
            f"С возвращением, {user_name}!\nИспользуйте кнопки ниже для навигации:",
            reply_markup=menu
        )
    else:
        await message.answer(
            "Добро пожаловать в систему бронирования!\nВведите ваше полное ФИО для регистрации:",
            reply_markup=types.ReplyKeyboardRemove()
        )
        await state.set_state(BookingStates.INPUT_NAME)