# finance_handlers.py
from aiogram import types, F
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.state import State, StatesGroup
import logging
from datetime import datetime, timedelta
from typing import List, Dict
from calendar_utils import generate_finance_calendar
from config import SUBJECTS

logger = logging.getLogger(__name__)


class FinanceStates(StatesGroup):
    SELECT_PERSON = State()
    SELECT_SUBJECT = State()
    SELECT_DATE = State()
    SHOW_FINANCES = State()
    SHOW_BALANCE = State()


class FinanceHandlers:
    def __init__(self, storage, gsheets, subjects_config, generate_subjects_keyboard_func):
        self.storage = storage
        self.gsheets = gsheets
        self.subjects_config = subjects_config
        self.generate_subjects_keyboard_func = generate_subjects_keyboard_func

    def register_handlers(self, dp):
        """Регистрирует все обработчики для финансов"""
        # Обработчик кнопки "Финансы" в меню
        dp.message.register(self.start_finances, F.text == "💰 Финансы")

        # Обработчики выбора действия
        dp.callback_query.register(self.finance_select_person, F.data == "finance_start")
        dp.callback_query.register(self.finance_show_balance, F.data == "finance_show_balance")
        dp.callback_query.register(self.finance_back_from_balance, F.data == "finance_back_from_balance")

        # Обработчики выбора человека
        dp.callback_query.register(self.finance_select_child, F.data.startswith("finance_child_"))
        dp.callback_query.register(self.finance_select_self, F.data == "finance_self")
        dp.callback_query.register(self.finance_back_to_person_selection, F.data == "finance_back_to_person")

        # Обработчики выбора предмета
        dp.callback_query.register(self.finance_select_subject, F.data.startswith("subject_"))

        # Обработчики календаря финансов
        dp.callback_query.register(self.finance_select_date, F.data.startswith("finance_day_"))
        dp.callback_query.register(self.finance_change_month, F.data.startswith("finance_change_"))

        # Обработчики навигации
        dp.callback_query.register(self.finance_back_to_dates, F.data == "finance_back_to_dates")
        dp.callback_query.register(self.finance_back_to_subjects, F.data == "finance_back_to_subjects")
        dp.callback_query.register(self.finance_cancel, F.data == "finance_cancel")
        
        # Обработчики баланса
        dp.callback_query.register(self.balance_show_self, F.data == "balance_self")
        dp.callback_query.register(self.balance_show_child, F.data.startswith("balance_child_"))

    async def start_finances(self, message: types.Message, state: FSMContext):
        """Начало работы с финансами - выбор действия"""
        user_id = message.from_user.id
        user_roles = self.storage.get_user_roles(user_id)

        # Сохраняем ID пользователя, который запрашивает финансы
        await state.update_data(finance_user_id=user_id)

        # Проверяем, есть ли доступ к финансам
        is_student = 'student' in user_roles
        is_parent = 'parent' in user_roles

        if not (is_student or is_parent):
            await message.answer(
                "❌ У вас нет доступа к финансовой информации.\n"
                "Финансы доступны только ученикам и родителям.",
                reply_markup=await self._generate_main_menu(user_id)
            )
            return

        # Создаем клавиатуру выбора действия
        builder = InlineKeyboardBuilder()

        builder.button(
            text="📊 Детали по дате",
            callback_data="finance_start"
        )
        
        builder.button(
            text="💰 Текущий баланс", 
            callback_data="finance_show_balance"
        )
        
        builder.button(
            text="❌ Отмена",
            callback_data="finance_cancel"
        )
        
        builder.adjust(1)

        message_text = "💰 Выберите действие:"

        await message.answer(message_text, reply_markup=builder.as_markup())
        await state.set_state(FinanceStates.SELECT_PERSON)

    async def finance_show_balance(self, callback: types.CallbackQuery, state: FSMContext):
        """Показывает текущий баланс"""
        try:
            user_id = callback.from_user.id
            user_roles = self.storage.get_user_roles(user_id)

            # Получаем информацию о детях для родителей
            children = []
            if 'parent' in user_roles:
                children_ids = self.storage.get_parent_children(user_id)
                for child_id in children_ids:
                    child_info = self.storage.get_child_info(child_id)
                    if child_info:
                        children.append({
                            'id': child_id,
                            'name': child_info.get('user_name', f'Ученик {child_id}')
                        })

            # Создаем клавиатуру выбора человека для баланса
            builder = InlineKeyboardBuilder()

            # Если пользователь ученик - может выбрать себя
            if 'student' in user_roles:
                user_name = self.storage.get_user_name(user_id)
                balance = self.storage.get_student_balance(user_id)
                builder.button(
                    text=f"👤 {user_name}: {balance} руб.",
                    callback_data="balance_self"
                )

            # Если пользователь родитель - может выбрать детей
            if 'parent' in user_roles and children:
                for child in children:
                    balance = self.storage.get_student_balance(child['id'])
                    builder.button(
                        text=f"👶 {child['name']}: {balance} руб.",
                        callback_data=f"balance_child_{child['id']}"
                    )

            builder.button(
                text="⬅️ Назад", 
                callback_data="finance_back_from_balance"
            )
            builder.adjust(1)

            await callback.message.edit_text(
                "💰 Текущий баланс:\n\n"
                "Баланс = Все пополнения - Все списания\n\n"
                "Выберите для просмотра:",
                reply_markup=builder.as_markup()
            )
            await state.set_state(FinanceStates.SHOW_BALANCE)

        except Exception as e:
            logger.error(f"Error in finance_show_balance: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    async def balance_show_self(self, callback: types.CallbackQuery, state: FSMContext):
        """Показывает детальную информацию о балансе для себя с транзакциями за последний месяц"""
        try:
            user_id = callback.from_user.id
            user_name = self.storage.get_user_name(user_id)
            balance = self.storage.get_student_balance(user_id)
            
            # Получаем баланс по предметам
            balance_by_subjects = self.storage.get_student_balance_by_subjects(user_id)
            
            # Получаем историю операций за последний месяц
            finance_history = self.gsheets.get_student_finance_history_last_month(user_id)
            
            # Рассчитываем итоги за последний месяц
            monthly_replenished = sum(op["replenished"] for op in finance_history)
            monthly_withdrawn = sum(op["withdrawn"] for op in finance_history)
            monthly_change = monthly_replenished - monthly_withdrawn
            
            # Форматируем баланс по предметам
            subjects_balance_text = ""
            if balance_by_subjects:
                for subject_id, subject_balance in balance_by_subjects.items():
                    subject_name = self.subjects_config.get(subject_id, f"Предмет {subject_id}")
                    balance_emoji = "🟢" if subject_balance >= 0 else "🔴"
                    subjects_balance_text += f"{balance_emoji} {subject_name}: {subject_balance:.2f} руб.\n"
            else:
                subjects_balance_text = "Информация по предметам отсутствует\n"
            
            # Форматируем все транзакции за последний месяц
            transactions_text = ""
            if finance_history:
                # Берем последние 15 операций
                recent_operations = finance_history[-15:]
                for op in recent_operations:
                    date_display = datetime.strptime(op["date"], "%Y-%m-%d").strftime("%d.%m")
                    
                    # Получаем название предмета
                    subject_name = self.subjects_config.get(op.get("subject", ""), "Общий")
                    
                    # Показываем ОБЕ операции (пополнение и списание) если они есть в один день
                    replenished_text = f"+{op['replenished']:.2f} руб." if op["replenished"] > 0 else ""
                    withdrawn_text = f"-{op['withdrawn']:.2f} руб." if op["withdrawn"] > 0 else ""
                    
                    # Если есть и пополнение и списание в один день - показываем обе операции отдельно
                    if replenished_text and withdrawn_text:
                        transactions_text += f"📅 {date_display} 💳 Пополнение ({subject_name}): {replenished_text}\n"
                        transactions_text += f"📅 {date_display} 📚 Занятие ({subject_name}): {withdrawn_text}\n"
                    elif replenished_text:
                        transactions_text += f"📅 {date_display} 💳 Пополнение ({subject_name}): {replenished_text}\n"
                    elif withdrawn_text:
                        transactions_text += f"📅 {date_display} 📚 Занятие ({subject_name}): {withdrawn_text}\n"
            else:
                transactions_text = "Транзакций за последний месяц нет\n"
            
            # Получаем текущий месяц и год для отображения
            current_month = datetime.now().strftime("%m.%Y")
            
            message_text = (
                f"💰 Детальная информация о балансе\n\n"
                f"👤 Студент: {user_name}\n"
                f"💳 Общий баланс: {balance:.2f} руб.\n"
                f"📊 Изменение за {current_month}: {monthly_change:+.2f} руб.\n"
                f"   (Пополнения: +{monthly_replenished:.2f} руб., Списания: -{monthly_withdrawn:.2f} руб.)\n\n"
                f"📈 Баланс по предметам:\n"
                f"{subjects_balance_text}\n"
                f"💸 Последние транзакции:\n"
                f"{transactions_text}\n"
                f"Баланс = Все пополнения - Все списания\n\n"
                f"Остаток средств переносится на следующие занятия."
            )
            
            builder = InlineKeyboardBuilder()
            builder.button(text="🔄 Обновить", callback_data="balance_self")
            builder.button(text="⬅️ Назад", callback_data="finance_show_balance")
            builder.adjust(2)
            
            # ИСПРАВЛЕНИЕ: Добавляем timestamp к тексту, чтобы сообщение всегда было разным
            timestamp = datetime.now().strftime("%H:%M:%S")
            message_text += f"\n\n🕐 Обновлено: {timestamp}"
            
            try:
                await callback.message.edit_text(
                    message_text,
                    reply_markup=builder.as_markup()
                )
            except Exception as edit_error:
                # Если сообщение не изменилось, просто подтверждаем callback
                if "message is not modified" in str(edit_error):
                    await callback.answer("✅ Данные актуальны")
                else:
                    raise edit_error
                    
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error in balance_show_self: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)                  


    async def balance_show_child(self, callback: types.CallbackQuery, state: FSMContext):
        """Показывает детальную информацию о балансе для ребенка с транзакциями за последний месяц"""
        try:
            child_id = int(callback.data.replace("balance_child_", ""))
            child_info = self.storage.get_child_info(child_id)
            
            if not child_info:
                await callback.answer("❌ Информация о ребенке не найдена", show_alert=True)
                return
                
            child_name = child_info.get('user_name', f'Ученик {child_id}')
            balance = self.storage.get_student_balance(child_id)
            
            # Получаем баланс по предметам
            balance_by_subjects = self.storage.get_student_balance_by_subjects(child_id)
            
            # Получаем историю операций за последний месяц
            finance_history = self.gsheets.get_student_finance_history_last_month(child_id)
            
            # Рассчитываем итоги за последний месяц
            monthly_replenished = sum(op["replenished"] for op in finance_history)
            monthly_withdrawn = sum(op["withdrawn"] for op in finance_history)
            monthly_change = monthly_replenished - monthly_withdrawn
            
            # Форматируем баланс по предметам
            subjects_balance_text = ""
            if balance_by_subjects:
                for subject_id, subject_balance in balance_by_subjects.items():
                    subject_name = self.subjects_config.get(subject_id, f"Предмет {subject_id}")
                    balance_emoji = "🟢" if subject_balance >= 0 else "🔴"
                    subjects_balance_text += f"{balance_emoji} {subject_name}: {subject_balance:.2f} руб.\n"
            else:
                subjects_balance_text = "Информация по предметам отсутствует\n"
            
            # Форматируем все транзакции за последний месяц
            transactions_text = ""
            if finance_history:
                # Берем последние 15 операций
                recent_operations = finance_history[-15:]
                for op in recent_operations:
                    date_display = datetime.strptime(op["date"], "%Y-%m-%d").strftime("%d.%m")
                    
                    # Получаем название предмета
                    subject_name = self.subjects_config.get(op.get("subject", ""), "Общий")
                    
                    # Показываем ОБЕ операции (пополнение и списание) если они есть в один день
                    replenished_text = f"+{op['replenished']:.2f} руб." if op["replenished"] > 0 else ""
                    withdrawn_text = f"-{op['withdrawn']:.2f} руб." if op["withdrawn"] > 0 else ""
                    
                    # Если есть и пополнение и списание в один день - показываем обе операции отдельно
                    if replenished_text and withdrawn_text:
                        transactions_text += f"📅 {date_display} 💳 Пополнение ({subject_name}): {replenished_text}\n"
                        transactions_text += f"📅 {date_display} 📚 Занятие ({subject_name}): {withdrawn_text}\n"
                    elif replenished_text:
                        transactions_text += f"📅 {date_display} 💳 Пополнение ({subject_name}): {replenished_text}\n"
                    elif withdrawn_text:
                        transactions_text += f"📅 {date_display} 📚 Занятие ({subject_name}): {withdrawn_text}\n"
            else:
                transactions_text = "Транзакций за последний месяц нет\n"
            
            # Получаем текущий месяц и год для отображения
            current_month = datetime.now().strftime("%m.%Y")
            
            message_text = (
                f"💰 Детальная информация о балансе\n\n"
                f"👶 Ребенок: {child_name}\n"
                f"💳 Общий баланс: {balance:.2f} руб.\n"
                f"📊 Изменение за {current_month}: {monthly_change:+.2f} руб.\n"
                f"   (Пополнения: +{monthly_replenished:.2f} руб., Списания: -{monthly_withdrawn:.2f} руб.)\n\n"
                f"📈 Баланс по предметам:\n"
                f"{subjects_balance_text}\n"
                f"💸 Транзакции за последний месяц:\n"
                f"{transactions_text}\n"
                f"Баланс = Все пополнения - Все списания\n\n"
                f"Остаток средств переносится на следующие занятия."
            )
            
            builder = InlineKeyboardBuilder()
            builder.button(text="🔄 Обновить", callback_data=f"balance_child_{child_id}")
            builder.button(text="⬅️ Назад", callback_data="finance_show_balance")
            builder.adjust(2)
            
            # ИСПРАВЛЕНИЕ: Добавляем timestamp к тексту, чтобы сообщение всегда было разным
            timestamp = datetime.now().strftime("%H:%M:%S")
            message_text += f"\n\n🕐 Обновлено: {timestamp}"
            
            try:
                await callback.message.edit_text(
                    message_text,
                    reply_markup=builder.as_markup()
                )
            except Exception as edit_error:
                # Если сообщение не изменилось, просто подтверждаем callback
                if "message is not modified" in str(edit_error):
                    await callback.answer("✅ Данные актуальны")
                else:
                    raise edit_error
                    
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error in balance_show_child: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    @staticmethod
    async def finance_back_from_balance(callback: types.CallbackQuery, state: FSMContext):
        """Возврат из просмотра баланса"""
        try:
            # Получаем данные из состояния
            data = await state.get_data()
            user_id = data.get('finance_user_id', callback.from_user.id)
            
            # Сбрасываем состояние финансов
            await state.clear()
            
            # Создаем клавиатуру выбора действия для финансов
            builder = InlineKeyboardBuilder()

            builder.button(
                text="📊 Детали по дате",
                callback_data="finance_start"
            )
            
            builder.button(
                text="💰 Текущий баланс", 
                callback_data="finance_show_balance"
            )
            
            builder.button(
                text="❌ Отмена",
                callback_data="finance_cancel"
            )
            
            builder.adjust(1)

            message_text = "💰 Выберите действие:"

            await callback.message.edit_text(
                message_text, 
                reply_markup=builder.as_markup()
            )
            await state.set_state(FinanceStates.SELECT_PERSON)
            await callback.answer()
            
        except Exception as e:
            logger.error(f"Error in finance_back_from_balance: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    async def finance_select_person(self, callback: types.CallbackQuery, state: FSMContext):
        """Выбор человека для просмотра деталей по дате"""
        try:
            user_id = callback.from_user.id
            user_roles = self.storage.get_user_roles(user_id)

            # Сбрасываем состояние
            await state.clear()
            await state.set_state(FinanceStates.SELECT_PERSON)

            builder = InlineKeyboardBuilder()

            # Если пользователь ученик - добавляем себя
            if 'student' in user_roles:
                user_name = self.storage.get_user_name(user_id)
                builder.button(
                    text=f"👤 {user_name} (Я)",
                    callback_data="finance_self"
                )

            # Если пользователь родитель - добавляем детей
            if 'parent' in user_roles:
                children_ids = self.storage.get_parent_children(user_id)
                for child_id in children_ids:
                    child_info = self.storage.get_child_info(child_id)
                    if child_info:
                        child_name = child_info.get('user_name', f'Ученик {child_id}')
                        builder.button(
                            text=f"👶 {child_name}",
                            callback_data=f"finance_child_{child_id}"
                        )

            builder.button(text="⬅️ Назад", callback_data="finance_back_from_balance")
            builder.adjust(1)

            await callback.message.edit_text(
                "👥 Выберите человека для просмотра финансовых деталей:",
                reply_markup=builder.as_markup()
            )

        except Exception as e:
            logger.error(f"Error in finance_select_person: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    async def finance_select_child(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка выбора ребенка для финансовых деталей"""
        try:
            child_id = int(callback.data.replace("finance_child_", ""))
            child_info = self.storage.get_child_info(child_id)

            if not child_info:
                await callback.answer("❌ Информация о ребенке не найдена", show_alert=True)
                return

            child_name = child_info.get('user_name', f'Ученик {child_id}')

            # Сохраняем информацию о выбранном человеке
            await state.update_data(
                finance_target_id=child_id,
                finance_target_name=child_name,
                finance_target_type='child'
            )

            # Получаем доступные предметы для этого ребенка
            available_subjects = self.storage.get_available_subjects_for_student(child_id)

            if not available_subjects:
                await callback.answer(
                    f"❌ У {child_name} нет доступных предметов",
                    show_alert=True
                )
                return

            await callback.message.edit_text(
                f"👶 Выбран: {child_name}\n"
                "📚 Теперь выберите предмет:",
                reply_markup=self.generate_subjects_keyboard_func(
                    available_subjects=available_subjects
                )
            )
            await state.set_state(FinanceStates.SELECT_SUBJECT)
            await callback.answer()

        except Exception as e:
            logger.error(f"Error in finance_select_child: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    async def finance_select_self(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка выбора себя для финансовых деталей"""
        try:
            data = await state.get_data()
            user_id = data.get('finance_user_id', callback.from_user.id)

            user_name = self.storage.get_user_name(user_id)

            # Сохраняем информацию о выбранном человеке
            await state.update_data(
                finance_target_id=user_id,
                finance_target_name=user_name,
                finance_target_type='self'
            )

            # Получаем доступные предметы для ученика
            available_subjects = self.storage.get_available_subjects_for_student(user_id)

            if not available_subjects:
                await callback.answer("❌ У вас нет доступных предметов", show_alert=True)
                return

            await callback.message.edit_text(
                f"👤 Выбран: {user_name}\n"
                "📚 Теперь выберите предмет:",
                reply_markup=self.generate_subjects_keyboard_func(
                    available_subjects=available_subjects
                )
            )
            await state.set_state(FinanceStates.SELECT_SUBJECT)
            await callback.answer()

        except Exception as e:
            logger.error(f"Error in finance_select_self: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    async def finance_select_subject(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка выбора предмета"""
        try:
            subject_id = callback.data.replace("subject_", "")

            # Проверяем, что предмет существует
            if subject_id not in self.subjects_config:
                await callback.answer("❌ Предмет не найден", show_alert=True)
                return

            subject_name = self.subjects_config[subject_id]

            # Сохраняем выбранный предмет
            await state.update_data(
                finance_subject_id=subject_id,
                finance_subject_name=subject_name
            )

            # Получаем данные из состояния
            data = await state.get_data()
            target_id = data.get('finance_target_id')
            target_name = data.get('finance_target_name')

            # Получаем доступные даты для финансов
            available_dates = self.gsheets.get_available_finance_dates(target_id, subject_id)

            if not available_dates:
                await callback.message.edit_text(
                    f"💰 Финансы для {target_name}\n"
                    f"📚 Предмет: {subject_name}\n\n"
                    "❌ Нет финансовых данных за выбранный период."
                )
                await state.clear()
                return

            # Показываем календарь для выбора даты
            await callback.message.edit_text(
                f"💰 Финансы для: {target_name}\n"
                f"📚 Предмет: {subject_name}\n\n"
                "📅 Выберите дату для просмотра финансов:",
                reply_markup=generate_finance_calendar()
            )
            await state.set_state(FinanceStates.SELECT_DATE)
            await callback.answer()

        except Exception as e:
            logger.error(f"Error in finance_select_subject: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    async def finance_select_date(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка выбора даты из календаря"""
        try:
            date_str = callback.data.replace("finance_day_", "")
            year, month, day = map(int, date_str.split("-"))
            selected_date = datetime(year, month, day).date()
            formatted_date = selected_date.strftime("%Y-%m-%d")

            # Сохраняем выбранную дату
            await state.update_data(finance_selected_date=formatted_date)

            # Получаем все данные из состояния
            data = await state.get_data()
            target_id = data.get('finance_target_id')
            target_name = data.get('finance_target_name')
            subject_id = data.get('finance_subject_id')
            subject_name = data.get('finance_subject_name')

            # Получаем финансовую информацию
            finance_data = self.gsheets.get_student_finances(
                target_id, subject_id, formatted_date
            )

            # Формируем сообщение с финансовой информацией
            message_text = self._format_finance_message(
                target_name, subject_name, formatted_date, finance_data
            )

            # Создаем клавиатуру для навигации
            keyboard = self._generate_finance_navigation_keyboard()

            await callback.message.edit_text(
                message_text,
                reply_markup=keyboard
            )
            await state.set_state(FinanceStates.SHOW_FINANCES)
            await callback.answer()

        except Exception as e:
            logger.error(f"Error in finance_select_date: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    async def finance_change_month(self, callback: types.CallbackQuery, state: FSMContext):
        """Обработка смены месяца в календаре"""
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

    async def finance_back_to_dates(self, callback: types.CallbackQuery, state: FSMContext):
        """Возврат к выбору даты"""
        data = await state.get_data()
        target_name = data.get('finance_target_name')
        subject_name = data.get('finance_subject_name')

        await callback.message.edit_text(
            f"💰 Финансы для: {target_name}\n"
            f"📚 Предмет: {subject_name}\n\n"
            "📅 Выберите дату для просмотра финансов:",
            reply_markup=generate_finance_calendar()
        )
        await state.set_state(FinanceStates.SELECT_DATE)
        await callback.answer()

    async def finance_back_to_subjects(self, callback: types.CallbackQuery, state: FSMContext):
        """Возврат к выбору предмета"""
        data = await state.get_data()
        target_name = data.get('finance_target_name')

        target_id = data.get('finance_target_id')
        available_subjects = self.storage.get_available_subjects_for_student(target_id)

        await callback.message.edit_text(
            f"💰 Финансы для: {target_name}\n"
            "📚 Выберите предмет:",
            reply_markup=self.generate_subjects_keyboard_func(
                available_subjects=available_subjects
            )
        )
        await state.set_state(FinanceStates.SELECT_SUBJECT)
        await callback.answer()

    async def finance_back_to_person_selection(self, callback: types.CallbackQuery, state: FSMContext):
        """Возврат к выбору человека"""
        await self.start_finances(callback.message, state)
        await callback.answer()

    async def finance_cancel(self, callback: types.CallbackQuery, state: FSMContext):
        """Отмена просмотра финансов"""
        try:
            user_id = callback.from_user.id

            # Очищаем состояние
            await state.clear()

            # Получаем главное меню
            main_menu = await self._generate_main_menu(user_id)

            # Вместо edit_text используем edit_message_reply_markup с новым сообщением
            await callback.message.edit_text(
                "❌ Просмотр финансов отменен.",
                reply_markup=None  # Убираем inline клавиатуру
            )

            # Отправляем новое сообщение с главным меню
            await callback.message.answer(
                "Выберите действие:",
                reply_markup=main_menu
            )

            await callback.answer()

        except Exception as e:
            logger.error(f"Error in finance_cancel: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    def _format_finance_message(self, target_name: str, subject_name: str,
                                date: str, finance_data: Dict) -> str:
        """Форматирует сообщение с финансовой информацией"""
        replenished = finance_data.get("replenished", 0.0)
        withdrawn = finance_data.get("withdrawn", 0.0)
        tariff = finance_data.get("tariff", 0.0)

        # Форматируем дату для отображения
        try:
            display_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d.%m.%Y")
        except:
            display_date = date

        message = (
            f"💰 Финансовая информация\n"
            f"👤 Для: {target_name}\n"
            f"📚 Предмет: {subject_name}\n"
            f"📅 Дата: {display_date}\n\n"
        )

        # Добавляем информацию о занятии
        if withdrawn > 0:
            message += f"✅ Занятие проведено: -{withdrawn} руб.\n"
        else:
            message += "❌ Занятие не проводилось\n"

        # Добавляем информацию о пополнении
        if replenished > 0:
            message += f"💳 Пополнение: +{replenished} руб.\n"

        # Добавляем информацию о тарифе
        message += f"📋 Тариф: {tariff} руб./занятие\n\n"

        # Рассчитываем изменение за день
        # daily_change = replenished - withdrawn
        # if daily_change > 0:
        #     message += f"📈 Изменение за день: +{daily_change} руб."
        # elif daily_change < 0:
        #     message += f"📉 Изменение за день: {daily_change} руб."
        # else:
        #     message += "➖ За день баланс не изменился"

        return message

    def _generate_finance_navigation_keyboard(self, show_balance_button=True):
        """Создает клавиатуру для навигации по финансам"""
        builder = InlineKeyboardBuilder()

        builder.button(
            text="📅 Выбрать другую дату",
            callback_data="finance_back_to_dates"
        )
        builder.button(
            text="📚 Выбрать другой предмет",
            callback_data="finance_back_to_subjects"
        )
        builder.button(
            text="👤 Выбрать другого человека",
            callback_data="finance_back_to_person"
        )
        
        if show_balance_button:
            builder.button(
                text="💰 Текущий баланс",
                callback_data="finance_show_balance"
            )
            
        builder.button(
            text="❌ Завершить",
            callback_data="finance_cancel"
        )

        builder.adjust(1)
        return builder.as_markup()

    async def _generate_main_menu(self, user_id: int):
        """Генерирует главное меню"""
        from menu_handlers import generate_main_menu
        return await generate_main_menu(user_id, self.storage)