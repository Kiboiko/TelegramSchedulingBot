# payment_handlers.py
import os
import sqlite3
import uuid
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from yookassa import Configuration, Payment
from dotenv import load_dotenv
import logging
from typing import List, Dict

logger = logging.getLogger(__name__)

load_dotenv()
# Настройка ЮKassa
Configuration.account_id = os.getenv("YOOKASSA_SHOP_ID")
Configuration.secret_key = os.getenv("YOOKASSA_SECRET_KEY")


# Состояния для процесса оплаты
class PaymentStates(StatesGroup):
    WAITING_AMOUNT = State()
    CONFIRM_PAYMENT = State()


# Инициализация базы данных платежей
def init_payments_db():
    conn = sqlite3.connect('payments.db', check_same_thread=False)
    c = conn.cursor()

    # Проверяем существование таблицы и добавляем колонку amount если нужно
    c.execute('''CREATE TABLE IF NOT EXISTS payments
                 (user_id INTEGER, payment_id TEXT UNIQUE, status TEXT)''')

    # Проверяем есть ли колонка amount
    c.execute("PRAGMA table_info(payments)")
    columns = [column[1] for column in c.fetchall()]

    if 'amount' not in columns:
        c.execute("ALTER TABLE payments ADD COLUMN amount REAL")
        print("Added amount column to payments table")

    conn.commit()
    conn.close()


init_payments_db()


# Сохраняем платеж в базу
def save_payment(user_id, payment_id, amount):
    conn = sqlite3.connect('payments.db', check_same_thread=False)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO payments (user_id, payment_id, amount, status) VALUES (?, ?, ?, 'pending')",
                  (user_id, payment_id, amount))
        conn.commit()
    except Exception as e:
        print(f"Error saving payment: {e}")
    finally:
        conn.close()


# Обновляем статус платежа
def update_payment_status(payment_id, status):
    conn = sqlite3.connect('payments.db', check_same_thread=False)
    c = conn.cursor()
    c.execute("UPDATE payments SET status = ? WHERE payment_id = ?", (status, payment_id))
    conn.commit()
    conn.close()


# Получаем сумму платежа из базы
def get_payment_amount(payment_id):
    conn = sqlite3.connect('payments.db', check_same_thread=False)
    c = conn.cursor()
    try:
        c.execute("SELECT amount FROM payments WHERE payment_id = ?", (payment_id,))
        result = c.fetchone()
        return result[0] if result else 0
    except Exception as e:
        print(f"Error getting payment amount: {e}")
        return 0
    finally:
        conn.close()


class PaymentHandlers:
    """Обработчики платежной системы"""

    @staticmethod
    async def handle_payment_start(message: types.Message | types.CallbackQuery, state: FSMContext):
        """Начало процесса оплаты - сразу переходим к выбору ученика/ребенка"""
        try:
            # Обрабатываем оба типа входящих данных
            if isinstance(message, types.CallbackQuery):
                user_id = message.from_user.id
                message_obj = message.message
                from_callback = True
            else:
                user_id = message.from_user.id
                message_obj = message
                from_callback = False

            # Получаем роли пользователя
            from main import storage
            user_roles = storage.get_user_roles(user_id)

            if not user_roles:
                if from_callback:
                    await message.answer("❌ У вас нет ролей для оплаты", show_alert=True)
                else:
                    await message_obj.answer("❌ У вас нет ролей для оплаты")
                return

            # Очищаем состояние перед началом нового процесса оплаты
            await state.clear()

            builder = InlineKeyboardBuilder()

            has_options = False

            # ДОБАВЛЯЕМ ВЫБОР СЕБЯ ДЛЯ УЧЕНИКОВ
            if 'student' in user_roles:
                user_name = storage.get_user_name(user_id)
                builder.add(types.InlineKeyboardButton(
                    text=f"👤 {user_name} (Я)",
                    callback_data="payment_self"
                ))
                has_options = True

            if 'parent' in user_roles:
                # Для родителя - показываем выбор ребенка
                children_ids = storage.get_parent_children(user_id)
                if children_ids:
                    for child_id in children_ids:
                        child_info = storage.get_child_info(child_id)
                        child_name = child_info.get('user_name', f'Ученик {child_id}')
                        builder.add(types.InlineKeyboardButton(
                            text=f"👶 {child_name}",
                            callback_data=f"payment_child_{child_id}"
                        ))
                    has_options = True

            if not has_options:
                if from_callback:
                    await message.answer("❌ У вас нет доступных опций для оплаты", show_alert=True)
                else:
                    await message_obj.answer("❌ У вас нет доступных опций для оплаты")
                return

            builder.add(types.InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="cancel_payment"
            ))
            builder.adjust(1)

            message_text = "💳 Выберите, для кого производится оплата:\n\n"
            message_text += "📝 Предмет будет выбран автоматически (с наименьшим балансом)"

            if from_callback:
                await message_obj.edit_text(
                    message_text,
                    reply_markup=builder.as_markup()
                )
            else:
                await message_obj.answer(
                    message_text,
                    reply_markup=builder.as_markup()
                )

        except Exception as e:
            logger.error(f"Ошибка в handle_payment_start: {e}")
            if isinstance(message, types.CallbackQuery):
                await message.answer("❌ Произошла ошибка", show_alert=True)
            else:
                await message.answer("❌ Произошла ошибка")

    # @staticmethod
    # async def _show_subjects(message: types.Message, state: FSMContext):
    #     """Показывает выбор предметов"""
    #     try:
    #         data = await state.get_data()
    #         target_user_id = data.get('target_user_id')

    #         if not target_user_id:
    #             await message.answer("❌ Ошибка: не выбран пользователь")
    #             return

    #         from main import storage
    #         available_subjects = storage.get_available_subjects_for_student(target_user_id)

    #         if not available_subjects:
    #             await message.answer("❌ Нет доступных предметов для оплаты")
    #             return

    #         builder = InlineKeyboardBuilder()
    #         for subject_id in available_subjects:
    #             from config import SUBJECTS
    #             subject_name = SUBJECTS.get(subject_id, f"Предмет {subject_id}")
    #             builder.add(types.InlineKeyboardButton(
    #                 text=subject_name,
    #                 callback_data=f"payment_subject_{subject_id}"
    #             ))

    #         builder.add(types.InlineKeyboardButton(
    #             text="❌ Отмена",
    #             callback_data="cancel_payment"
    #         ))
    #         builder.adjust(2)

    #         target_name = data.get('target_user_name', 'Пользователь')

    #         await message.answer(
    #             f"💳 Оплата для: {target_name}\n"
    #             "📚 Выберите предмет для оплаты:",
    #             reply_markup=builder.as_markup()
    #         )

    #     except Exception as e:
    #         logger.error(f"Ошибка в _show_subjects: {e}")
    #         await message.answer("❌ Ошибка при загрузке предметов")

    @staticmethod
    async def handle_child_selection(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает выбор ребенка - автоматически определяем предмет"""
        try:
            child_id = int(callback.data.replace("payment_child_", ""))

            from main import storage
            child_info = storage.get_child_info(child_id)

            if not child_info:
                await callback.answer("❌ Ошибка: информация о ребенке не найдена", show_alert=True)
                return

            # Получаем доступные предметы для ребенка
            available_subjects = storage.get_available_subjects_for_student(child_id)
            
            if not available_subjects:
                await callback.answer("❌ У ребенка нет доступных предметов для оплаты", show_alert=True)
                return

            # Автоматически выбираем предмет с наименьшим балансом
            subject_id = await PaymentHandlers._get_subject_with_lowest_balance(child_id, available_subjects)
            
            if not subject_id:
                await callback.answer("❌ Не удалось определить предмет для оплаты", show_alert=True)
                return

            await state.update_data(
                target_user_id=child_id,
                target_user_name=child_info.get('user_name', ''),
                subject_id=subject_id
            )

            from config import SUBJECTS
            subject_name = SUBJECTS.get(subject_id, f"Предмет {subject_id}")

            await callback.message.edit_text(
                f"💳 Оплата:\n"
                f"👤 Для: {child_info.get('user_name', '')}\n"
                f"📚 Предмет: {subject_name} (выбран автоматически)\n\n"
                f"Введите сумму для оплаты (в рублях):\n\n"
                f"Примеры:\n"
                f"• 100\n"
                f"• 500.50\n"
                f"• 1000\n\n"
                f"Минимальная сумма: 1 рубль\n"
                f"Максимальная сумма: 15000 рублей"
            )

            await state.set_state(PaymentStates.WAITING_AMOUNT)
            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка в handle_child_selection: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    @staticmethod
    async def _get_subject_with_lowest_balance(user_id: int, available_subjects: List[str]) -> str:
        """Определяет предмет с наименьшим балансом"""
        try:
            from main import gsheets
            
            if not gsheets:
                # Если Google Sheets недоступен, возвращаем предмет с наименьшим ID
                return min(available_subjects) if available_subjects else None

            subject_balances = {}
            
            for subject_id in available_subjects:
                # Получаем баланс для каждого предмета
                balance = gsheets.get_student_balance_for_subject(user_id, subject_id)
                subject_balances[subject_id] = balance
            
            # Находим минимальный баланс
            min_balance = min(subject_balances.values())
            
            # Получаем все предметы с минимальным балансом
            min_balance_subjects = [subj for subj, bal in subject_balances.items() if bal == min_balance]
            
            # Если несколько предметов с одинаковым минимальным балансом, выбираем с наименьшим ID
            return min(min_balance_subjects) if min_balance_subjects else None
            
        except Exception as e:
            logger.error(f"Ошибка при определении предмета с наименьшим балансом: {e}")
            # В случае ошибки возвращаем предмет с наименьшим ID
            return min(available_subjects) if available_subjects else None

    # @staticmethod
    # async def handle_subject_selection(callback: types.CallbackQuery, state: FSMContext):
    #     """Обрабатывает выбор предмета"""
    #     try:
    #         subject_id = callback.data.replace("payment_subject_", "")

    #         await state.update_data(subject_id=subject_id)

    #         data = await state.get_data()
    #         target_name = data.get('target_user_name', 'Пользователь')

    #         from config import SUBJECTS
    #         subject_name = SUBJECTS.get(subject_id, f"Предмет {subject_id}")

    #         await callback.message.edit_text(
    #             f"💳 Оплата:\n"
    #             f"👤 Для: {target_name}\n"
    #             f"📚 Предмет: {subject_name}\n\n"
    #             f"Введите сумму для оплаты (в рублях):\n\n"
    #             f"Примеры:\n"
    #             f"• 100\n"
    #             f"• 500.50\n"
    #             f"• 1000\n\n"
    #             f"Минимальная сумма: 1 рубль\n"
    #             f"Максимальная сумма: 15000 рублей"
    #         )

    #         await state.set_state(PaymentStates.WAITING_AMOUNT)
    #         await callback.answer()

    #     except Exception as e:
    #         logger.error(f"Ошибка в handle_subject_selection: {e}")
    #         await callback.answer("❌ Произошла ошибка", show_alert=True)

    @staticmethod
    async def handle_self_selection(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает выбор себя для оплаты - автоматически определяем предмет"""
        try:
            user_id = callback.from_user.id

            # Импортируем storage из main
            from main import storage
            user_name = storage.get_user_name(user_id)

            # Получаем доступные предметы для пользователя
            available_subjects = storage.get_available_subjects_for_student(user_id)
            
            if not available_subjects:
                await callback.answer("❌ Нет доступных предметов для оплаты", show_alert=True)
                return

            # Автоматически выбираем предмет с наименьшим балансом
            subject_id = await PaymentHandlers._get_subject_with_lowest_balance(user_id, available_subjects)
            
            if not subject_id:
                await callback.answer("❌ Не удалось определить предмет для оплаты", show_alert=True)
                return

            await state.update_data(
                target_user_id=user_id,
                target_user_name=user_name,
                subject_id=subject_id
            )

            from config import SUBJECTS
            subject_name = SUBJECTS.get(subject_id, f"Предмет {subject_id}")

            await callback.message.edit_text(
                f"💳 Оплата:\n"
                f"👤 Для: {user_name}\n"
                f"📚 Предмет: {subject_name} (выбран автоматически)\n\n"
                f"Введите сумму для оплаты (в рублях):\n\n"
                f"Примеры:\n"
                f"• 100\n"
                f"• 500.50\n"
                f"• 1000\n\n"
                f"Минимальная сумма: 1 рубль\n"
                f"Максимальная сумма: 15000 рублей"
            )

            await state.set_state(PaymentStates.WAITING_AMOUNT)
            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка в handle_self_selection: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    @staticmethod
    async def handle_amount_input(message: types.Message, state: FSMContext):
        """Обработка введенной суммы"""
        try:
            amount = float(message.text.replace(',', '.'))

            # Проверка минимальной и максимальной суммы
            if amount < 1:
                await message.answer("❌ Минимальная сумма оплаты - 1 рубль")
                return
            if amount > 15000:
                await message.answer("❌ Максимальная сумма оплаты - 15000 рублей")
                return

            # Получаем данные из состояния
            data = await state.get_data()
            target_user_id = data.get('target_user_id')
            subject_id = data.get('subject_id')

            if not target_user_id or not subject_id:
                await message.answer("❌ Ошибка: недостаточно данных")
                await state.clear()
                return

            # УДАЛЯЕМ ЗАПИСЬ В ТАБЛИЦУ - сумма будет записываться только после успешной оплаты
            # success = await PaymentHandlers._write_payment_to_sheets(
            #     target_user_id, subject_id, amount
            # )

            # if success:
            #     logger.info(f"Сумма {amount} руб. записана в таблицу для user_id {target_user_id}, subject {subject_id}")
            # else:
            #     logger.error(f"Ошибка записи суммы в таблицу для user_id {target_user_id}, subject {subject_id}")

            # Сохраняем сумму в состоянии для дальнейшей оплаты
            await state.update_data(amount=amount)

            # Создаем клавиатуру подтверждения
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data="confirm_payment")],
                [types.InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_payment")]
            ])

            from main import storage
            target_name = storage.get_user_name(target_user_id)
            from config import SUBJECTS
            subject_name = SUBJECTS.get(subject_id, f"Предмет {subject_id}")

            await message.answer(
                f"📋 Подтвердите данные платежа:\n\n"
                f"👤 Для: {target_name}\n"
                f"📚 Предмет: {subject_name}\n"
                f"💰 Сумма: {amount:.2f} руб.\n\n"
                f"💳 Тестовые карты для оплаты:\n"
                f"• 5555 5555 5555 4477 - успешный платеж\n"
                f"• 5555 5555 5555 4444 - отказ в оплате",
                reply_markup=keyboard
            )
            await state.set_state(PaymentStates.CONFIRM_PAYMENT)

        except ValueError:
            await message.answer("❌ Пожалуйста, введите корректную сумму\n\nПример: 100 или 500.50")
        except Exception as e:
            logger.error(f"Ошибка в handle_amount_input: {e}")
            await message.answer("❌ Произошла ошибка при обработки суммы")

    @staticmethod
    async def handle_confirm_payment(callback: types.CallbackQuery, state: FSMContext):
        """Создание платежа после подтверждения"""
        try:
            data = await state.get_data()
            amount = data.get('amount')
            target_user_id = data.get('target_user_id')
            # subject_id = data.get('subject_id')

            if not amount:
                await callback.message.edit_text("❌ Ошибка: сумма не найдена")
                await state.clear()
                return

            # Создаем платеж в ЮKassa
            payment = Payment.create({
                "amount": {
                    "value": f"{amount:.2f}",
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": "https://t.me/testoviySchedile_bot"
                },
                "capture": True,
                "description": f"Оплата услуги на сумму {amount:.2f} руб.",
                "metadata": {
                    "user_id": callback.from_user.id,
                    "target_user_id": target_user_id,
                }
            }, str(uuid.uuid4()))

            # Сохраняем в базу
            save_payment(callback.from_user.id, payment.id, amount)

            # Создаем кнопки
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(
                    text=f"💳 Оплатить {amount:.2f} руб.",
                    url=payment.confirmation.confirmation_url
                )],
                [types.InlineKeyboardButton(
                    text="🔍 Проверить оплату",
                    callback_data=f"check_{payment.id}"
                )],
                [types.InlineKeyboardButton(
                    text="🔄 Новый платеж",
                    callback_data="new_payment"
                )]
            ])

            # СООБЩЕНИЕ С ЯРКИМ ПРЕДУПРЕЖДЕНИЕМ
            warning_text = "🚨🚨🚨 ВАЖНОЕ ПРЕДУПРЕЖДЕНИЕ 🚨🚨🚨\n\n"
            warning_text += "❌ НЕ ЗАКРЫВАЙТЕ ЭТОТ ДИАЛОГ И НЕ УДАЛЯЙТЕ ЭТО СООБЩЕНИЕ!\n\n"
            warning_text += "📋 ПОСЛЕ ОПЛАТЫ ВЫ ДОЛЖНЫ:\n"
            warning_text += "1. Оплатить на сайте ЮKassa\n"
            warning_text += "2. 🔄 ВЕРНУТЬСЯ В БОТ\n"
            warning_text += "3. НАЖАТЬ КНОПКУ '🔍 Проверить оплату'\n\n"
            warning_text += "⚠️ ЕСЛИ ВЫ НЕ НАЖМЕТЕ 'Проверить оплату':\n"
            warning_text += "• Деньги НЕ поступят на ваш баланс\n"
            warning_text += "• Платеж НЕ запишется в таблицу\n"
            warning_text += "• Вы ПОТЕРЯЕТЕ деньги!\n\n"
            warning_text += f"💸 Платеж создан!\n"
            warning_text += f"💰 Сумма: {amount:.2f} руб.\n"
            warning_text += f"🆔 ID: {payment.id[:8]}...\n\n"
            warning_text += f"💳 Тестовые карты:\n"
            warning_text += f"• 5555 5555 5555 4477 - успешный платеж\n"
            warning_text += f"• 5555 5555 5555 4444 - отказ"

            await callback.message.edit_text(
                warning_text,
                reply_markup=keyboard
            )
            await state.clear()

        except Exception as e:
            await callback.message.edit_text(f"❌ Ошибка при создании платежа: {str(e)}")
            await state.clear()

    @staticmethod
    async def handle_cancel_payment(callback: types.CallbackQuery, state: FSMContext):
        """Отмена платежа"""
        await callback.message.edit_text("❌ Оплата отменена")
        await state.clear()
        await callback.answer()

    @staticmethod
    async def handle_new_payment(callback: types.CallbackQuery, state: FSMContext):
        """Начать новый платеж - ПЕРЕЗАПУСКАЕМ ПРОЦЕСС С НАЧАЛА"""
        try:
            # Полностью очищаем состояние
            await state.clear()

            # Получаем user_id и проверяем роли
            user_id = callback.from_user.id

            from main import storage
            user_roles = storage.get_user_roles(user_id)

            if not user_roles:
                await callback.answer("❌ У вас нет ролей для оплаты", show_alert=True)
                return

            # Начинаем процесс оплаты с самого начала
            if 'parent' in user_roles:
                # Для родителя - показываем выбор ребенка
                children_ids = storage.get_parent_children(user_id)
                if not children_ids:
                    await callback.answer("❌ У вас нет привязанных детей", show_alert=True)
                    return

                builder = InlineKeyboardBuilder()
                for child_id in children_ids:
                    child_info = storage.get_child_info(child_id)
                    child_name = child_info.get('user_name', f'Ученик {child_id}')
                    builder.add(types.InlineKeyboardButton(
                        text=f"👶 {child_name}",
                        callback_data=f"payment_child_{child_id}"
                    ))

                builder.add(types.InlineKeyboardButton(
                    text="❌ Отмена",
                    callback_data="cancel_payment"
                ))
                builder.adjust(1)

                await callback.message.edit_text(
                    "💳 Выберите ребенка для оплаты:",
                    reply_markup=builder.as_markup()
                )

            elif 'student' in user_roles:
                # Для ученика - сразу выбираем себя
                await state.update_data(
                    target_user_id=user_id,
                    target_user_name=storage.get_user_name(user_id)
                )

                # Показываем выбор предметов
                await PaymentHandlers._show_subjects(callback.message, state)

            else:
                await callback.answer("❌ У вас нет ролей для оплаты", show_alert=True)

            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка в handle_new_payment: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    @staticmethod
    async def handle_check_payment(callback: types.CallbackQuery):
        """Проверка статуса платежа"""
        payment_id = callback.data.replace('check_', '')

        try:
            payment = Payment.find_one(payment_id)

            # Получаем сумму из базы
            amount = get_payment_amount(payment_id)

            if payment.status == 'succeeded':
                update_payment_status(payment_id, 'succeeded')

                # ЗАПИСЫВАЕМ СУММУ В ТАБЛИЦУ ТОЛЬКО ПОСЛЕ УСПЕШНОЙ ОПЛАТЫ
                metadata = payment.metadata
                target_user_id = metadata.get('target_user_id')
                # subject_id = metadata.get('subject_id')

                if target_user_id:
                    success = await PaymentHandlers._write_payment_to_sheets(
                        target_user_id, amount
                    )

                    if success:
                        logger.info(f"Сумма {amount} руб. успешно записана в таблицу после подтверждения оплаты")

                        # УСПЕШНОЕ СООБЩЕНИЕ
                        success_text = "🎉🎉🎉 ОПЛАТА УСПЕШНО ПОДТВЕРЖДЕНА! 🎉🎉🎉\n\n"
                        success_text += f"✅ Платеж прошел успешно!\n"
                        success_text += f"💰 Сумма: {amount:.2f} руб. зачислена на баланс!\n"
                        success_text += f"📊 Деньги записаны в таблицу\n"
                        success_text += f"🎉 Услуга активирована!\n\n"
                        success_text += f"Спасибо за оплату! 💫"

                        await callback.message.edit_text(
                            success_text,
                            reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                                [types.InlineKeyboardButton(
                                    text="🔄 Новый платеж",
                                    callback_data="new_payment"
                                )]
                            ])
                        )
                    else:
                        error_text = "⚠️⚠️⚠️ ВНИМАНИЕ! ⚠️⚠️⚠️\n\n"
                        error_text += f"✅ Платеж прошел успешно!\n"
                        error_text += f"💰 Сумма: {amount:.2f} руб.\n"
                        error_text += f"❌ Но произошла ошибка при зачислении на баланс.\n\n"
                        error_text += f"🚨 СРОЧНО ОБРАТИТЕСЬ К АДМИНИСТРАТОРУ!\n"
                        error_text += f"📞 Телефон: +79001372727\n\n"
                        error_text += f"Сообщите ID платежа: {payment_id[:8]}..."

                        await callback.message.edit_text(error_text)
                else:
                    error_text = "⚠️⚠️⚠️ ВНИМАНИЕ! ⚠️⚠️⚠️\n\n"
                    error_text += f"✅ Платеж прошел успешно!\n"
                    error_text += f"💰 Сумма: {amount:.2f} руб.\n"
                    error_text += f"❌ Но не удалось определить данные для зачисления.\n\n"
                    error_text += f"🚨 СРОЧНО ОБРАТИТЕСЬ К АДМИНИСТРАТОРУ!\n"
                    error_text += f"📞 Телефон: +79001372727"

                    await callback.message.edit_text(error_text)

            elif payment.status == 'pending':
                # Сообщение с напоминанием
                reminder_text = "⏳ Платеж обрабатывается...\n\n"
                reminder_text += "💡 Не забудьте нажать '🔍 Проверить оплату' еще раз через несколько минут!\n\n"
                reminder_text += "❌ Без проверки деньги НЕ поступят на баланс!"

                await callback.answer(reminder_text, show_alert=True)

            elif payment.status == 'canceled':
                update_payment_status(payment_id, 'canceled')
                await callback.answer("❌ Платеж отменен", show_alert=True)

            else:
                await callback.answer(f"Статус: {payment.status}", show_alert=True)

        except Exception as e:
            await callback.answer(f"Ошибка: {str(e)}", show_alert=True)

    @staticmethod
    async def _write_payment_to_sheets(user_id: int, amount: float) -> bool:
        """Записывает платеж в Google Sheets на предмет с наименьшим балансом"""
        try:
            from main import gsheets, storage
            
            if not gsheets:
                logger.error("Google Sheets не доступен")
                return False

            # Получаем доступные предметы для ученика
            available_subjects = storage.get_available_subjects_for_student(user_id)
            
            if not available_subjects:
                logger.error(f"Нет доступных предметов для user_id {user_id}")
                return False

            # Автоматически определяем предмет с наименьшим балансом
            subject_id = await PaymentHandlers._get_subject_with_lowest_balance(user_id, available_subjects)
            
            if not subject_id:
                logger.error(f"Не удалось определить предмет для оплаты user_id {user_id}")
                return False

            from datetime import datetime
            current_date = datetime.now().strftime("%Y-%m-%d")
            formatted_date = gsheets.format_date(current_date)

            worksheet = gsheets._get_or_create_worksheet("Ученики бот")
            data = worksheet.get_all_values()

            if len(data) < 1:
                logger.error("Таблица 'Ученики бот' пустая")
                return False

            headers = [str(h).strip().lower() for h in data[0]]

            # Ищем финансовый столбец для текущей даты (первый из двух)
            target_col = -1
            for i in range(245, len(headers)):
                header = headers[i]
                if formatted_date.lower() in header:
                    target_col = i
                    break

            if target_col == -1:
                logger.error(f"Не найден финансовый столбец для даты {formatted_date}")
                return False

            # Ищем строку пользователя с указанным subject_id
            target_row = -1
            for row_idx, row in enumerate(data[1:], start=2):
                if (len(row) > 0 and str(row[0]).strip() == str(user_id) and
                        len(row) > 2 and str(row[2]).strip() == str(subject_id)):
                    target_row = row_idx
                    break

            if target_row == -1:
                logger.error(f"Не найдена строка для user_id {user_id} и subject_id {subject_id}")
                return False

            # Получаем текущее значение ячейки
            current_value = 0.0
            if len(data[target_row - 1]) > target_col:
                cell_value = data[target_row - 1][target_col].strip()
                if cell_value and cell_value.replace('.', '').replace(',', '').isdigit():
                    try:
                        current_value = float(cell_value.replace(',', '.'))
                    except ValueError:
                        current_value = 0.0

            # Вычисляем новое значение (прибавляем к текущему)
            new_value = current_value + amount

            # Записываем новое значение в ячейку
            worksheet.update_cell(target_row, target_col + 1, f"{new_value:.2f}")

            # Получаем название предмета для логов
            from config import SUBJECTS
            subject_name = SUBJECTS.get(subject_id, f"Предмет {subject_id}")
            user_name = storage.get_user_name(user_id)

            logger.info(
                f"💰 Платеж записан в таблицу: {user_name} (ID:{user_id}), "
                f"предмет: {subject_name} (ID:{subject_id}), "
                f"сумма: {amount:.2f} руб., дата: {formatted_date}, "
                f"было: {current_value:.2f}, стало: {new_value:.2f}"
            )
            
            return True

        except Exception as e:
            logger.error(f"Ошибка записи платежа в таблицу: {e}")
            return False

    @staticmethod
    async def _update_payment_status_in_sheets(user_id: int, subject_id: str, amount: float, status: str):
        """Обновляет статус платежа в таблице (для успешных оплат)"""
        try:
            # Можно добавить дополнительную логику для отметки успешных оплат
            # Например, запись во второй столбец даты или добавление пометки
            logger.info(
                f"Платеж подтвержден: user_id={user_id}, subject={subject_id}, amount={amount}, status={status}")
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления статуса платежа: {e}")
            return False
        
    @staticmethod
    async def _get_subject_with_lowest_balance(user_id: int, available_subjects: List[str]) -> str:
        """Определяет предмет с наименьшим балансом (использует новый метод из gsheets)"""
        try:
            from main import gsheets
            
            if not gsheets:
                logger.warning("Google Sheets недоступен, используем первый доступный предмет")
                return available_subjects[0] if available_subjects else None
            
            # Используем новый метод из gsheets_manager для точного определения
            lowest_balance_subject = gsheets.get_subject_with_lowest_balance(user_id)
            
            logger.info(f"Предмет с наименьшим балансом для user_id {user_id}: {lowest_balance_subject}")
            
            # Проверяем, что найденный предмет доступен для оплаты
            if lowest_balance_subject and lowest_balance_subject in available_subjects:
                logger.info(f"Используем предмет с наименьшим балансом: {lowest_balance_subject}")
                return lowest_balance_subject
            elif available_subjects:
                # Если метод не нашел предмет или он недоступен, используем первый доступный
                logger.warning(f"Предмет {lowest_balance_subject} недоступен, используем первый из доступных: {available_subjects[0]}")
                return available_subjects[0]
            else:
                logger.error("Нет доступных предметов для оплаты")
                return None
            
        except Exception as e:
            logger.error(f"Ошибка при определении предмета с наименьшим балансом: {e}")
            # Fallback: возвращаем первый доступный предмет
            return available_subjects[0] if available_subjects else None