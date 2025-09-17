from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from services.storage_service import storage
from keyboards import generate_calendar
from states import BookingStates

router = Router()


@router.message(F.text == "📊 Составить расписание")
async def create_schedule(message: types.Message, state: FSMContext):
    if message.from_user.id not in [1180878673, 973231400, 1312414595]:
        await message.answer("Эта функция доступна только администраторам")
        return

    await message.answer(
        "Выберите дату для составления расписания:",
        reply_markup=generate_calendar()
    )
    await state.set_state(BookingStates.SELECT_SCHEDULE_DATE)


@router.callback_query(BookingStates.SELECT_SCHEDULE_DATE, F.data.startswith("calendar_day_"))
async def select_schedule_date(callback: types.CallbackQuery, state: FSMContext):
    date_str = callback.data.replace("calendar_day_", "")
    await state.update_data(schedule_date=date_str)

    # Здесь будет логика генерации расписания
    await callback.message.edit_text(
        f"Расписание для {date_str} будет сгенерировано здесь"
    )
    await state.clear()