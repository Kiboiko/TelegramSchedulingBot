from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from services.storage_service import storage
from keyboards import generate_booking_actions

router = Router()


@router.message(F.text == "📋 Мои бронирования")
async def show_my_bookings(message: types.Message):
    user_id = message.from_user.id
    bookings = storage.load()
    user_bookings = [b for b in bookings if b.get('user_id') == user_id]

    if not user_bookings:
        await message.answer("У вас пока нет активных бронирований")
        return

    response = "📋 Ваши активные бронирования:\n\n"
    for booking in sorted(user_bookings, key=lambda x: (x.get('date'), x.get('start_time'))):
        response += (
            f"📅 {booking.get('date')} | ⏰ {booking.get('start_time')}-{booking.get('end_time')}\n"
            f"👤 Роль: {booking.get('user_role')}\n"
        )

        if booking.get('user_role') == 'teacher':
            subjects = booking.get('subjects', [])
            subject_text = ", ".join([SUBJECTS.get(subj, subj) for subj in subjects])
            response += f"📚 Предметы: {subject_text}\n"
        else:
            subject_text = SUBJECTS.get(booking.get('subject', ''), '')
            response += f"📚 Предмет: {subject_text}\n"

        response += f"🔗 ID: {booking.get('id')}\n\n"

    await message.answer(response)


@router.callback_query(F.data.startswith("cancel_booking_"))
async def cancel_booking(callback: types.CallbackQuery):
    booking_id = int(callback.data.replace("cancel_booking_", ""))

    if storage.cancel_booking(booking_id):
        await callback.message.edit_text("✅ Бронирование успешно отменено")
    else:
        await callback.message.edit_text("❌ Не удалось найти бронирование для отмены")


@router.callback_query(F.data == "back_to_bookings")
async def back_to_bookings(callback: types.CallbackQuery):
    await callback.message.delete()
    await show_my_bookings(callback.message)