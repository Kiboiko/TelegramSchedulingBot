# payment_handlers.py
import os
import sqlite3
import uuid
from aiogram import types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from yookassa import Configuration, Payment
from dotenv import load_dotenv

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
        """Начало процесса оплаты - запрос суммы"""
        await message.answer(
            "💳 Введите сумму для оплаты (в рублях):\n\n"
            "Примеры:\n"
            "• 100\n"
            "• 500.50\n"
            "• 1000\n\n"
            "Минимальная сумма: 1 рубль\n"
            "Максимальная сумма: 15000 рублей"
        )
        await state.set_state(PaymentStates.WAITING_AMOUNT)

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
            
            # Сохраняем сумму в состоянии
            await state.update_data(amount=amount)
            
            # Создаем клавиатуру подтверждения
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(text="✅ Подтвердить оплату", callback_data="confirm_payment")],
                [types.InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_payment")]
            ])
            
            await message.answer(
                f"📋 Подтвердите данные платежа:\n\n"
                f"💰 Сумма: {amount:.2f} руб.\n\n"
                f"💳 Тестовые карты для оплаты:\n"
                f"• 5555 5555 5555 4477 - успешный платеж\n"
                f"• 5555 5555 5555 4444 - отказ в оплате",
                reply_markup=keyboard
            )
            await state.set_state(PaymentStates.CONFIRM_PAYMENT)
            
        except ValueError:
            await message.answer("❌ Пожалуйста, введите корректную сумму\n\nПример: 100 или 500.50")

    @staticmethod
    async def handle_confirm_payment(callback: types.CallbackQuery, state: FSMContext):
        """Создание платежа после подтверждения"""
        try:
            data = await state.get_data()
            amount = data.get('amount')
            
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
                    "user_id": callback.from_user.id
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