from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from datetime import datetime, date
from services.storage_service import storage
from keyboards import (
    generate_calendar, generate_time_range_keyboard_with_availability,
    generate_subjects_keyboard, generate_confirmation
)
from states import BookingStates
from config import BOOKING_TYPES
from services.availability_service import get_subject_distribution_by_time
from shedule_app.GoogleParser import GoogleSheetsDataLoader

router = Router()


@router.callback_query(F.data.startswith("role_"))
async def select_role(callback: types.CallbackQuery, state: FSMContext):
    role = callback.data.split("_")[1]
    user_id = callback.from_user.id

    await state.update_data(user_role=role)

    if role == 'teacher':
        subjects = storage.get_teacher_subjects(user_id)
        if subjects:
            await callback.message.edit_text(
                "Выберите предметы для занятия:",
                reply_markup=generate_subjects_keyboard([], is_teacher=True)
            )
            await state.update_data(subjects=[])
            await state.set_state(BookingStates.SELECT_SUBJECT)
        else:
            await callback.message.edit_text(
                "У вас нет доступных предметов для преподавания"
            )
    elif role == 'student':
        available_subjects = storage.get_available_subjects_for_student(user_id)
        if available_subjects:
            await callback.message.edit_text(
                "Выберите предмет для занятия:",
                reply_markup=generate_subjects_keyboard([], available_subjects=available_subjects)
            )
            await state.set_state(BookingStates.SELECT_SUBJECT)
        else:
            await callback.message.edit_text(
                "У вас нет доступных предметов для изучения"
            )
    else:
        await callback.message.edit_text(
            "Выберите дату для бронирования:",
            reply_markup=generate_calendar()
        )
        await state.set_state(BookingStates.SELECT_DATE)


@router.callback_query(F.data.startswith("subject_"))
async def select_subject(callback: types.CallbackQuery, state: FSMContext):
    subject_id = callback.data.split("_")[1]
    data = await state.get_data()
    user_role = data.get('user_role')

    if user_role == 'teacher':
        current_subjects = data.get('subjects', [])
        if subject_id in current_subjects:
            current_subjects.remove(subject_id)
        else:
            current_subjects.append(subject_id)

        await state.update_data(subjects=current_subjects)
        await callback.message.edit_reply_markup(
            reply_markup=generate_subjects_keyboard(current_subjects, is_teacher=True)
        )
    else:
        await state.update_data(subject=subject_id)
        await callback.message.edit_text(
            "Выберите дату для бронирования:",
            reply_markup=generate_calendar()
        )
        await state.set_state(BookingStates.SELECT_DATE)


@router.callback_query(F.data == "subjects_done")
async def subjects_done(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    subjects = data.get('subjects', [])

    if not subjects:
        await callback.answer("Выберите хотя бы один предмет", show_alert=True)
        return

    await callback.message.edit_text(
        "Выберите дату для бронирования:",
        reply_markup=generate_calendar()
    )
    await state.set_state(BookingStates.SELECT_DATE)


@router.callback_query(F.data.startswith("calendar_day_"))
async def select_date(callback: types.CallbackQuery, state: FSMContext):
    date_str = callback.data.replace("calendar_day_", "")
    data = await state.get_data()
    user_role = data.get('user_role')

    if storage.has_booking_on_date(callback.from_user.id, date_str, user_role):
        await callback.answer(
            "У вас уже есть бронь на этот день. Вы можете иметь только одну бронь в день.",
            show_alert=True
        )
        return

    await state.update_data(date=date_str)

    loader = GoogleSheetsDataLoader()
    subject_distribution = get_subject_distribution_by_time(loader, date_str)
    availability_map = {time_slot: data['condition_result'] for time_slot, data in subject_distribution.items()}

    await callback.message.edit_text(
        f"Выбрана дата: {date_str}\nВыберите время начала и окончания занятия:",
        reply_markup=generate_time_range_keyboard_with_availability(
            selected_date=date_str, availability_map=availability_map
        )
    )
    await state.set_state(BookingStates.SELECT_TIME_RANGE)


@router.callback_query(F.data.startswith("time_point_"))
async def select_time(callback: types.CallbackQuery, state: FSMContext):
    time_str = callback.data.replace("time_point_", "")
    data = await state.get_data()

    if 'start_time' not in data:
        await state.update_data(start_time=time_str)
        await callback.message.edit_reply_markup(
            reply_markup=generate_time_range_keyboard_with_availability(
                selected_date=data.get('date'),
                start_time=time_str,
                end_time=None
            )
        )
    else:
        await state.update_data(end_time=time_str)
        await callback.message.edit_reply_markup(
            reply_markup=generate_time_range_keyboard_with_availability(
                selected_date=data.get('date'),
                start_time=data.get('start_time'),
                end_time=time_str
            )
        )


@router.callback_query(F.data == "confirm_time_range")
async def confirm_time_range(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()

    if not all([data.get('start_time'), data.get('end_time')]):
        await callback.answer("Выберите начало и конец времени", show_alert=True)
        return

    start_time = datetime.strptime(data['start_time'], "%H:%M")
    end_time = datetime.strptime(data['end_time'], "%H:%M")

    if end_time <= start_time:
        await callback.answer("Время окончания должно быть позже времени начала", show_alert=True)
        return

    if storage.has_time_conflict(callback.from_user.id, data['date'], data['start_time'], data['end_time']):
        await callback.answer("У вас уже есть бронь в это время", show_alert=True)
        return

    user_role = data.get('user_role')
    if user_role == 'teacher':
        subjects = data.get('subjects', [])
        subject_text = ", ".join([SUBJECTS.get(subj, subj) for subj in subjects])
    else:
        subject_text = SUBJECTS.get(data.get('subject', ''), '')

    booking_text = (
        f"📋 Подтвердите бронирование:\n\n"
        f"👤 Роль: {'Преподаватель' if user_role == 'teacher' else 'Ученик'}\n"
        f"📅 Дата: {data['date']}\n"
        f"⏰ Время: {data['start_time']} - {data['end_time']}\n"
    )

    if subject_text:
        booking_text += f"📚 Предмет: {subject_text}\n"

    await callback.message.edit_text(
        booking_text,
        reply_markup=generate_confirmation()
    )
    await state.set_state(BookingStates.CONFIRMATION)


@router.callback_query(F.data == "booking_confirm")
async def booking_confirm(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = callback.from_user.id
    user_name = storage.get_user_name(user_id)

    booking_data = {
        'user_id': user_id,
        'user_name': user_name,
        'user_role': data.get('user_role'),
        'booking_type': BOOKING_TYPES[0],
        'date': data.get('date'),
        'start_time': data.get('start_time'),
        'end_time': data.get('end_time'),
        'created_at': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    if data.get('user_role') == 'teacher':
        booking_data['subjects'] = data.get('subjects', [])
    else:
        booking_data['subject'] = data.get('subject')

    storage.add_booking(booking_data)

    await callback.message.edit_text(
        "✅ Бронирование успешно создано!\n\n"
        "Вы можете посмотреть свои бронирования через главное меню."
    )
    await state.clear()


@router.callback_query(F.data == "booking_cancel")
async def booking_cancel(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.edit_text("❌ Бронирование отменено")
    await state.clear()