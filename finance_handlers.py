from aiogram import types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from datetime import datetime
from states import FinanceStates
from calendar_utils import generate_finance_calendar
from menu_handlers import generate_main_menu

logger = logging.getLogger(__name__)

class FinanceHandlers:
    def __init__(self, storage, gsheets, subjects_config, generate_subjects_keyboard_func):
        self.storage = storage
        self.gsheets = gsheets
        self.subjects_config = subjects_config
        self.generate_subjects_keyboard_func = generate_subjects_keyboard_func

    def register_handlers(self, dp):
        # Обработчик кнопки "Финансы"
        dp.message.register(
            self.start_finance_flow,
            F.text == "💰 Финансы"
        )

        # Обработчик выбора предмета
        dp.callback_query.register(
            self.process_finance_subject_selection,
            F.data.startswith("subject_"),
            FinanceStates.SELECT_SUBJECT
        )

        # Обработчики календаря финансов
        dp.callback_query.register(
            self.process_finance_calendar_change,
            F.data.startswith("finance_change_")
        )

        dp.callback_query.register(
            self.process_finance_date_selection,
            F.data.startswith("finance_day_"),
            FinanceStates.SELECT_DATE
        )

        # Игнорирование вспомогательных callback'ов
        dp.callback_query.register(
            self.ignore_finance_callback,
            F.data.startswith("ignore_"),
            FinanceStates.SELECT_DATE
        )

        # Обработчики навигации
        dp.callback_query.register(
            self.finance_back_to_subjects,
            F.data == "back_to_finance_subjects"
        )

        dp.callback_query.register(
            self.finance_back_to_dates,
            F.data == "back_to_finance_calendar"
        )

        dp.callback_query.register(
            self.back_to_menu_from_finance,
            F.data == "back_to_menu_from_finance"
        )

    async def start_finance_flow(self, message: types.Message, state: FSMContext):
        """Начало процесса просмотра финансов"""
        user_id = message.from_user.id

        # Проверяем, является ли пользователь учеником
        roles = self.storage.get_user_roles(user_id)
        if 'student' not in roles:
            await message.answer(
                "❌ Просмотр финансов доступен только для учеников",
                reply_markup=await generate_main_menu(user_id, self.storage)
            )
            return

        # Получаем доступные предметы для ученика
        available_subjects = self.storage.get_available_subjects_for_student(user_id)
        if not available_subjects:
            await message.answer(
                "❌ У вас нет доступных предметов для просмотра финансов",
                reply_markup=await generate_main_menu(user_id, self.storage)
            )
            return

        await state.update_data(available_subjects=available_subjects)

        await message.answer(
            "💰 Просмотр финансов\n"
            "Выберите предмет:",
            reply_markup=self.generate_subjects_keyboard_func(available_subjects=available_subjects)
        )
        await state.set_state(FinanceStates.SELECT_SUBJECT)

    async def process_finance_subject_selection(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка выбора предмета для финансов"""
        subject_id = callback.data.split("_")[1]
        user_id = callback.from_user.id

        # Сохраняем выбранный предмет
        await state.update_data(selected_subject=subject_id)

        # Получаем доступные даты для выбранного предмета
        available_dates = self.gsheets.get_available_finance_dates(user_id, subject_id)

        if not available_dates:
            await callback.message.edit_text(
                f"❌ Для предмета {self.subjects_config.get(subject_id, '')} нет финансовых данных",
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[[
                    types.InlineKeyboardButton(
                        text="🔙 Назад к выбору предмета",
                        callback_data="back_to_finance_subjects"
                    )
                ]])
            )
            return

        await state.update_data(available_dates=available_dates)

        await callback.message.edit_text(
            f"📊 Финансы по предмету: {self.subjects_config.get(subject_id, '')}\n"
            "📅 Выберите дату для просмотра финансов:",
            reply_markup=generate_finance_calendar()
        )
        await state.set_state(FinanceStates.SELECT_DATE)
        await callback.answer()

    async def process_finance_calendar_change(self, callback: types.CallbackQuery):
        """Обработка переключения месяцев в финансовом календаре"""
        try:
            date_str = callback.data.replace("finance_change_", "")
            year, month = map(int, date_str.split("-"))

            await callback.message.edit_reply_markup(
                reply_markup=generate_finance_calendar(year, month)
            )
            await callback.answer()
        except Exception as e:
            logger.error(f"Error changing finance calendar month: {e}")
            await callback.answer("Не удалось изменить месяц", show_alert=True)

    async def process_finance_date_selection(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка выбора даты в финансовом календаре"""
        try:
            data = callback.data
            date_str = data.replace("finance_day_", "")
            year, month, day = map(int, date_str.split("-"))
            selected_date = datetime(year, month, day).date()
            formatted_date = selected_date.strftime("%Y-%m-%d")

            # Получаем данные из состояния
            state_data = await state.get_data()
            subject_id = state_data.get('selected_subject')
            available_dates = state_data.get('available_dates', [])

            # Проверяем, есть ли финансовая информация для выбранной даты
            if formatted_date not in available_dates:
                await callback.answer(
                    "❌ На выбранную дату нет финансовых данных",
                    show_alert=True
                )
                return

            user_id = callback.from_user.id

            # Получаем финансовую информацию
            finance_data = self.gsheets.get_student_finances(
                user_id, subject_id, formatted_date
            )

            # Форматируем дату для отображения
            display_date = selected_date.strftime("%d.%m.%Y")
            subject_name = self.subjects_config.get(subject_id, '')

            # Формируем сообщение с финансовой информацией
            message_text = (
                f"💰 Финансовая информация\n\n"
                f"📅 Дата: {display_date}\n"
                f"📚 Предмет: {subject_name}\n"
                f"💳 Тариф: {finance_data.get('tariff', 0):.2f} руб.\n"
                f"💵 Пополнение: {finance_data.get('replenished', 0):.2f} руб.\n"
                f"📉 Списание: {finance_data.get('withdrawn', 0):.2f} руб.\n"
            )

            # Рассчитываем баланс
            balance = finance_data.get('replenished', 0) - finance_data.get('withdrawn', 0)
            message_text += f"📊 Баланс: {balance:.2f} руб.\n"

            # Добавляем информацию о занятии
            if finance_data.get('withdrawn', 0) > 0:
                message_text += f"✅ Занятие проведено\n"
            else:
                message_text += f"❌ Занятие не проведено\n"

            # Клавиатура для навигации
            keyboard = InlineKeyboardBuilder()
            keyboard.row(
                types.InlineKeyboardButton(
                    text="📅 Выбрать другую дату",
                    callback_data="back_to_finance_calendar"
                ),
                types.InlineKeyboardButton(
                    text="📚 Выбрать другой предмет",
                    callback_data="back_to_finance_subjects"
                )
            )
            keyboard.row(
                types.InlineKeyboardButton(
                    text="🔙 В главное меню",
                    callback_data="back_to_menu_from_finance"
                )
            )

            await callback.message.edit_text(
                message_text,
                reply_markup=keyboard.as_markup()
            )
            await state.set_state(FinanceStates.SHOW_FINANCES)
            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка при выборе даты финансов: {e}")
            await callback.answer("Ошибка при выборе даты", show_alert=True)

    async def ignore_finance_callback(self, callback: types.CallbackQuery):
        """Игнорирование вспомогательных callback'ов финансового календаря"""
        await callback.answer()

    async def finance_back_to_subjects(self, callback: types.CallbackQuery, state: FSMContext):
        """Возврат к выбору предмета"""
        data = await state.get_data()
        available_subjects = data.get('available_subjects', [])

        await callback.message.edit_text(
            "💰 Просмотр финансов\n"
            "Выберите предмет:",
            reply_markup=self.generate_subjects_keyboard_func(available_subjects=available_subjects)
        )
        await state.set_state(FinanceStates.SELECT_SUBJECT)
        await callback.answer()

    async def finance_back_to_dates(self, callback: types.CallbackQuery, state: FSMContext):
        """Возврат к календарю финансов"""
        await callback.message.edit_text(
            "📅 Выберите дату для просмотра финансов:",
            reply_markup=generate_finance_calendar()
        )
        await state.set_state(FinanceStates.SELECT_DATE)
        await callback.answer()

    async def back_to_menu_from_finance(self, callback: types.CallbackQuery, state: FSMContext):
        """Возврат в главное меню из финансов"""
        user_id = callback.from_user.id
        menu = await generate_main_menu(user_id, self.storage)

        await callback.message.edit_text(
            "Главное меню:",
            reply_markup=None
        )
        await callback.message.answer(
            "Выберите действие:",
            reply_markup=menu
        )
        await state.clear()
        await callback.answer()