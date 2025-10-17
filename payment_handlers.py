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
    async def handle_payment_start(message: types.Message, state: FSMContext):
        """Начало процесса оплаты - выбор ребенка/ученика и предмета"""
        user_id = message.from_user.id

        # Получаем роли пользователя
        from main import storage
        user_roles = storage.get_user_roles(user_id)

        if 'parent' in user_roles:
            # Для родителя - показываем выбор ребенка
            children_ids = storage.get_parent_children(user_id)
            if not children_ids:
                await message.answer("❌ У вас нет привязанных детей")
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

            await message.answer(
                "💳 Выберите ребенка для оплаты:",
                reply_markup=builder.as_markup()
            )

        elif 'student' in user_roles:
            # Для ученика - сразу выбираем себя
            await state.update_data(
                target_user_id=user_id,
                target_user_name=storage.get_user_name(user_id)
            )
            await PaymentHandlers._show_subjects(message, state)

        else:
            await message.answer("❌ У вас нет ролей для оплаты")

    @staticmethod
    async def _show_subjects(message: types.Message, state: FSMContext):
        """Показывает выбор предметов"""
        try:
            data = await state.get_data()
            target_user_id = data.get('target_user_id')

            if not target_user_id:
                await message.answer("❌ Ошибка: не выбран пользователь")
                return

            from main import storage
            available_subjects = storage.get_available_subjects_for_student(target_user_id)

            if not available_subjects:
                await message.answer("❌ Нет доступных предметов для оплаты")
                return

            builder = InlineKeyboardBuilder()
            for subject_id in available_subjects:
                from config import SUBJECTS
                subject_name = SUBJECTS.get(subject_id, f"Предмет {subject_id}")
                builder.add(types.InlineKeyboardButton(
                    text=subject_name,
                    callback_data=f"payment_subject_{subject_id}"
                ))

            builder.add(types.InlineKeyboardButton(
                text="❌ Отмена",
                callback_data="cancel_payment"
            ))
            builder.adjust(2)

            await message.answer(
                "📚 Выберите предмет для оплаты:",
                reply_markup=builder.as_markup()
            )

        except Exception as e:
            logger.error(f"Ошибка в _show_subjects: {e}")
            await message.answer("❌ Ошибка при загрузке предметов")

    @staticmethod
    async def handle_child_selection(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает выбор ребенка"""
        try:
            child_id = int(callback.data.replace("payment_child_", ""))

            from main import storage
            child_info = storage.get_child_info(child_id)

            if not child_info:
                await callback.answer("❌ Ошибка: информация о ребенке не найдена", show_alert=True)
                return

            await state.update_data(
                target_user_id=child_id,
                target_user_name=child_info.get('user_name', '')
            )

            await PaymentHandlers._show_subjects(callback.message, state)
            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка в handle_child_selection: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    @staticmethod
    async def handle_subject_selection(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает выбор предмета"""
        try:
            subject_id = callback.data.replace("payment_subject_", "")

            await state.update_data(subject_id=subject_id)

            data = await state.get_data()
            target_name = data.get('target_user_name', 'Пользователь')

            from config import SUBJECTS
            subject_name = SUBJECTS.get(subject_id, f"Предмет {subject_id}")

            await callback.message.edit_text(
                f"💳 Оплата:\n"
                f"👤 Для: {target_name}\n"
                f"📚 Предмет: {subject_name}\n\n"
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
            logger.error(f"Ошибка в handle_subject_selection: {e}")
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

            # ЗАПИСЫВАЕМ СУММУ В ТАБЛИЦУ СРАЗУ ПРИ ВВОДЕ
            success = await PaymentHandlers._write_payment_to_sheets(
                target_user_id, subject_id, amount
            )

            if success:
                logger.info(
                    f"Сумма {amount} руб. записана в таблицу для user_id {target_user_id}, subject {subject_id}")
            else:
                logger.error(f"Ошибка записи суммы в таблицу для user_id {target_user_id}, subject {subject_id}")

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
            await message.answer("❌ Произошла ошибка при обработке суммы")

    @staticmethod
    async def handle_confirm_payment(callback: types.CallbackQuery, state: FSMContext):
        """Создание платежа после подтверждения"""
        try:
            data = await state.get_data()
            amount = data.get('amount')
            target_user_id = data.get('target_user_id')
            subject_id = data.get('subject_id')

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
                    "subject_id": subject_id
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

            await callback.message.edit_text(
                f"💸 Платеж создан!\n"
                f"💰 Сумма: {amount:.2f} руб.\n"
                f"🆔 ID: {payment.id[:8]}...\n\n"
                f"📋 Инструкция:\n"
                f"1. Нажмите 'Оплатить {amount:.2f} руб.'\n"
                f"2. Оплатите на сайте ЮKassa\n"
                f"3. Вернитесь и нажмите 'Проверить оплату'\n\n"
                f"💳 Тестовые карты:\n"
                f"• 5555 5555 5555 4477 - успешный платеж\n"
                f"• 5555 5555 5555 4444 - отказ",
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
        """Начать новый платеж"""
        await PaymentHandlers.handle_payment_start(callback.message, state)
        await callback.answer()

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

                # Дополнительно подтверждаем запись в таблицу после успешной оплаты
                metadata = payment.metadata
                target_user_id = metadata.get('target_user_id')
                subject_id = metadata.get('subject_id')

                if target_user_id and subject_id:
                    # Обновляем запись в таблице с пометкой об успешной оплате
                    await PaymentHandlers._update_payment_status_in_sheets(
                        target_user_id, subject_id, amount, 'succeeded'
                    )

                await callback.message.edit_text(
                    f"✅ Платеж прошел успешно!\n"
                    f"💰 Сумма: {amount:.2f} руб.\n"
                    f"🎉 Услуга активирована!\n\n"
                    f"Для нового платежа нажмите кнопку ниже:",
                    reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                        [types.InlineKeyboardButton(
                            text="🔄 Новый платеж",
                            callback_data="new_payment"
                        )]
                    ])
                )

            elif payment.status == 'pending':
                await callback.answer("⏳ Платеж обрабатывается...", show_alert=True)

            elif payment.status == 'canceled':
                update_payment_status(payment_id, 'canceled')
                await callback.answer("❌ Платеж отменен", show_alert=True)

            else:
                await callback.answer(f"Статус: {payment.status}", show_alert=True)

        except Exception as e:
            await callback.answer(f"Ошибка: {str(e)}", show_alert=True)

    @staticmethod
    async def _write_payment_to_sheets(user_id: int, subject_id: str, amount: float) -> bool:
        """Записывает платеж в Google Sheets (сумма прибавляется к текущему значению)"""
        try:
            from main import gsheets
            if not gsheets:
                logger.error("Google Sheets не доступен")
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

            logger.info(
                f"Платеж записан в таблицу: user_id={user_id}, subject={subject_id}, "
                f"amount={amount}, current_value={current_value}, new_value={new_value}, date={formatted_date}")
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