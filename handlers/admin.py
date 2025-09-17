from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from services.storage_service import storage

router = Router()


@router.message(F.text == "👤 Моя роль")
async def show_my_role(message: types.Message):
    user_id = message.from_user.id
    user_roles = storage.get_user_roles(user_id)
    user_name = storage.get_user_name(user_id)

    if not user_roles:
        await message.answer(
            "⏳ Ваш аккаунт находится на проверке.\n"
            "Обратитесь к администратору для получения доступа.\n"
            "Телефон администратора: +79001372727"
        )
        return

    role_descriptions = {
        'teacher': '👨‍🏫 Преподаватель',
        'student': '👨‍🎓 Ученик',
        'parent': '👨‍👩‍👧‍👦 Родитель',
        'admin': '👑 Администратор'
    }

    roles_text = "\n".join([role_descriptions.get(role, role) for role in user_roles])

    await message.answer(
        f"👤 {user_name}\n\n"
        f"Ваши роли:\n{roles_text}\n\n"
        "Используйте кнопки ниже для навигации:"
    )