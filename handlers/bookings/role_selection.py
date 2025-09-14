from aiogram import types
from aiogram.fsm.context import FSMContext
from ...keyboards import generate_subjects_keyboard
from ...states import BookingStates


async def process_role_selection(callback: types.CallbackQuery, state: FSMContext):
    role = callback.data.split("_")[1]
    user_id = callback.from_user.id

    await state.update_data(user_role=role)

    if role == 'teacher':
        # Для преподавателя получаем предметы из Google Sheets
        teacher_subjects = storage.get_teacher_subjects(user_id)

        # ДЕБАГ: Логируем полученные предметы
        logger.info(f"Teacher {user_id} subjects: {teacher_subjects} (type: {type(teacher_subjects)})")

        # ВРЕМЕННОЕ ИСПРАВЛЕНИЕ: Если пришел список с одним элементом '1234'
        if (teacher_subjects and
                isinstance(teacher_subjects, list) and
                len(teacher_subjects) == 1 and
                teacher_subjects[0].isdigit() and
                len(teacher_subjects[0]) > 1):
            # Разбиваем '1234' на ['1', '2', '3', '4']
            combined_subject = teacher_subjects[0]
            teacher_subjects = [digit for digit in combined_subject]
            logger.info(f"Fixed combined subjects: {teacher_subjects}")

        if not teacher_subjects:
            await callback.answer(
                "У вас нет назначенных предметов. Обратитесь к администратору.\n Телефон администратора: +79001372727",
                show_alert=True
            )
            return

        await state.update_data(subjects=teacher_subjects)

        # Безопасное форматирование названий предметов
        subject_names = []
        for subj_id in teacher_subjects:
            subject_names.append(SUBJECTS.get(subj_id, f"Предмет {subj_id}"))

        await callback.message.edit_text(
            f"Вы выбрали роль преподавателя\n"
            f"Ваши предметы: {', '.join(subject_names)}\n"
            "Теперь выберите дату:",
            reply_markup=generate_calendar()
        )
        await state.set_state(BookingStates.SELECT_DATE)

    elif role == 'student':
        # Для ученика сразу запрашиваем предмет
        available_subjects = storage.get_available_subjects_for_student(user_id)

        if not available_subjects:
            await callback.answer(
                "У вас нет доступных предметов. Обратитесь к администратору.\n Телефон администратора: +79001372727",
                show_alert=True
            )
            return

        await callback.message.edit_text(
            "Вы выбрали роль ученика\n"
            "Выберите предмет для занятия:",
            reply_markup=generate_subjects_keyboard(available_subjects=available_subjects)
        )
        await state.set_state(BookingStates.SELECT_SUBJECT)

    elif role == 'parent':
        # Для родителя получаем детей
        children_ids = storage.get_parent_children(user_id)

        if not children_ids:
            await callback.answer(
                "У вас нет привязанных детей. Обратитесь к администратору.\n Телефон администратора: +79001372727",
                show_alert=True
            )
            return

        builder = InlineKeyboardBuilder()
        for child_id in children_ids:
            child_info = storage.get_child_info(child_id)
            child_name = child_info.get('user_name', f'Ученик {child_id}')
            builder.button(
                text=f"👶 {child_name}",
                callback_data=f"select_child_{child_id}"
            )

        builder.button(text="❌ Отмена", callback_data="cancel_child_selection")
        builder.adjust(1)

        await callback.message.edit_text(
            "Вы выбрали роль родителя\n"
            "Выберите ребенка для записи:",
            reply_markup=builder.as_markup()
        )
        await state.set_state(BookingStates.PARENT_SELECT_CHILD)

    await callback.answer()