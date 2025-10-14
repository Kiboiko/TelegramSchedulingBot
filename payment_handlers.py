# payment_handlers.py
import os
import sqlite3
import uuid
from aiogram import types
from aiogram.fsm.context import FSMContext
from yookassa import Configuration, Payment
from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY

# Настройка ЮKassa
Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET_KEY

# Инициализация базы данных платежей
def init_payments_db():
    conn = sqlite3.connect('payments.db', check_same_thread=False)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS payments
                 (user_id INTEGER, payment_id TEXT UNIQUE, status TEXT)''')
    conn.commit()
    conn.close()

init_payments_db()

# Сохраняем платеж в базу
def save_payment(user_id, payment_id):
    conn = sqlite3.connect('payments.db', check_same_thread=False)
    c = conn.cursor()
    try:
        c.execute("INSERT INTO payments (user_id, payment_id, status) VALUES (?, ?, 'pending')",
                  (user_id, payment_id))
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

class PaymentHandlers:
    """Обработчики платежной системы"""
    
    @staticmethod
    async def handle_payment_start(message: types.Message):
        """Начало процесса оплаты"""
        keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
            [types.InlineKeyboardButton(text="💳 Оплатить 1 рубль", callback_data="pay_1")]
        ])

        await message.answer(
            "🤖 Тестовая платежная система\n\n"
            "Протестируйте оплату через ЮKassa\n"
            "Стоимость: 1 рубль\n\n"
            "💳 Тестовые карты:\n"
            "• 5555 5555 5555 4477 - успешный платеж\n"
            "• 5555 5555 5555 4444 - отказ",
            reply_markup=keyboard
        )

    @staticmethod
    async def handle_create_payment(callback: types.CallbackQuery):
        """Создание платежа"""
        try:
            # Создаем платеж в ЮKassa на 1 рубль
            payment = Payment.create({
                "amount": {
                    "value": "1.00",
                    "currency": "RUB"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": "https://t.me/your_bot_username"  # Замените на username вашего бота
                },
                "capture": True,
                "description": "Тестовая услуга за 1 рубль",
                "metadata": {
                    "user_id": callback.from_user.id
                }
            }, str(uuid.uuid4()))

            # Сохраняем в базу
            save_payment(callback.from_user.id, payment.id)

            # Создаем кнопки
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(
                    text="💳 Оплатить 1 рубль",
                    url=payment.confirmation.confirmation_url
                )],
                [types.InlineKeyboardButton(
                    text="🔍 Проверить оплату",
                    callback_data=f"check_{payment.id}"
                )]
            ])

            await callback.message.edit_text(
                f"💸 Платеж создан!\n"
                f"💰 Сумма: 1 рубль\n"
                f"🆔 ID: {payment.id[:8]}...\n\n"
                f"1. Нажмите 'Оплатить 1 рубль'\n"
                f"2. Оплатите на сайте ЮKassa\n"
                f"3. Вернитесь и нажмите 'Проверить оплату'",
                reply_markup=keyboard
            )

        except Exception as e:
            await callback.message.edit_text(f"❌ Ошибка при создании платежа: {str(e)}")

    @staticmethod
    async def handle_check_payment(callback: types.CallbackQuery):
        """Проверка статуса платежа"""
        payment_id = callback.data.replace('check_', '')

        try:
            payment = Payment.find_one(payment_id)

            if payment.status == 'succeeded':
                update_payment_status(payment_id, 'succeeded')
                await callback.message.edit_text(
                    "✅ Платеж прошел успешно!\n"
                    "💰 Сумма: 1 рубль\n"
                    "🎉 Тестовая услуга активирована!\n\n"
                    "Для нового теста используйте команду /pay"
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