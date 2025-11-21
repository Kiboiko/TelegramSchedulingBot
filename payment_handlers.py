# payment_handlers.py
import os
import sqlite3
import uuid
from aiogram import types
import traceback
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from yookassa import Configuration, Payment
from dotenv import load_dotenv
import logging
from typing import List, Dict
from config import ADMIN_IDS
from datetime import datetime
import os
from typing import Dict, Any
from database import db

logger = logging.getLogger(__name__)

load_dotenv()
# Настройка ЮKassa
Configuration.account_id = os.getenv("YOOKASSA_SHOP_ID")
Configuration.secret_key = os.getenv("YOOKASSA_SECRET_KEY")


# Состояния для процесса оплаты
class PaymentStates(StatesGroup):
    WAITING_AMOUNT = State()
    CONFIRM_PAYMENT = State()
    WAITING_RECEIPT = State()


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
    async def handle_direct_transfer(callback: types.CallbackQuery, state: FSMContext):
        """Обработка выбора прямого перевода с ожиданием подтверждения от преподавателя"""
        try:
            from datetime import datetime
            # Получаем данные из состояния
            data = await state.get_data()
            target_user_id = data.get('target_user_id')  # ID ребенка
            subject_id = data.get('subject_id')
            amount = data.get('amount')

            if not all([target_user_id, subject_id, amount]):
                await callback.answer("❌ Ошибка: недостаточно данных", show_alert=True)
                return

            from main import storage, gsheets, bot
            target_name = storage.get_user_name(target_user_id)  # Имя ребенка
            from config import SUBJECTS
            subject_name = SUBJECTS.get(subject_id, f"Предмет {subject_id}")

            # Ищем самозанятого с наименьшим балансом
            self_employed_info = {}
            teacher_id = None
            if gsheets:
                self_employed_info = gsheets.get_self_employed_with_lowest_balance(amount)
                if self_employed_info and self_employed_info.get('remaining_limit', 0) < amount:
                    await callback.answer(
                        f"❌ Превышен лимит самозанятого!\n"
                        f"Доступно: {self_employed_info.get('remaining_limit', 0):.2f} руб.\n"
                        f"Требуется: {amount:.2f} руб.\n\n"
                        f"Пожалуйста, выберите другого преподавателя или уменьшите сумму.",
                        show_alert=True
                    )
                    return
                # Ищем ID преподавателя по имени
                teacher_id = await PaymentHandlers._find_teacher_id_by_name(self_employed_info.get('name', ''))

            # Сохраняем данные платежа в состоянии для подтверждения
            payment_data = {
                'target_user_id': target_user_id,  # ID ребенка
                'target_user_name': target_name,  # Имя ребенка
                'subject_id': subject_id,
                'subject_name': subject_name,
                'amount': amount,
                'teacher_id': teacher_id,
                'teacher_name': self_employed_info.get('name', ''),
                'parent_user_id': callback.from_user.id,  # ID родителя для уведомлений
                'created_at': datetime.now().isoformat()
            }

            await state.update_data(payment_data=payment_data)

            # Формируем сообщение для пользователя с ВСЕМИ данными преподавателя
            message_text = (
                "💳 *Прямой перевод преподавателю*\n\n"
                f"👤 Для: {target_name}\n"
                f"📚 Предмет: {subject_name}\n"
                f"💰 Сумма: {amount:.2f} руб.\n\n"
            )

            # ДОБАВЛЯЕМ ВСЕ КОНТАКТНЫЕ ДАННЫЕ ПРЕПОДАВАТЕЛЯ
            if self_employed_info and self_employed_info.get('name'):
                message_text += f"👨‍🏫 Преподаватель: *{self_employed_info['name']}*\n"

                # Добавляем телефон, если есть
                if self_employed_info.get('phone'):
                    message_text += f"📞 Телефон: {self_employed_info['phone']}\n"

                # Добавляем номер карты, если есть
                if self_employed_info.get('card_number'):
                    message_text += f"💳 Карта: {self_employed_info['card_number']}\n"

                # Добавляем банк, если есть
                if self_employed_info.get('bank'):
                    message_text += f"🏦 Банк: {self_employed_info['bank']}\n"

                message_text += "\n"  # Пустая строка для разделения
            else:
                message_text += "👨‍🏫 Преподаватель: *не назначен*\n\n"

            message_text += (
                "📋 *Инструкции:*\n"
                "1. Переведите деньги преподавателю\n"
                "2. 📸 Сделайте скриншот или фото чека перевода\n"
                "3. Отправьте чек в этот чат\n"
                "4. Преподаватель подтвердит получение\n"
                "5. После подтверждения баланс будет пополнен\n\n"
                "⏳ Ожидайте подтверждения от преподавателя"
            )

            # Кнопки
            keyboard_buttons = [
                [types.InlineKeyboardButton(
                    text="🔄 Новый платеж",
                    callback_data="new_payment"
                )],
                [types.InlineKeyboardButton(
                    text="📊 Проверить баланс",
                    callback_data="finance_start"
                )]
            ]

            keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)

            await callback.message.edit_text(
                message_text,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )

            # УБИРАЕМ отправку уведомления преподавателю здесь - оно отправится только после загрузки чека
            # Переходим в состояние ожидания чека
            await state.set_state(PaymentStates.WAITING_RECEIPT)

            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка в handle_direct_transfer: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    @staticmethod
    async def _notify_teacher_about_payment(teacher_id: int, student_name: str, subject_name: str, amount: float,
                                            student_user_id: int, parent_user_id: int):
        """Уведомляет преподавателя о новом платеже"""
        try:
            from main import bot

            message = (
                "💰 *НОВЫЙ ПЛАТЕЖ ТРЕБУЕТ ПОДТВЕРЖДЕНИЯ*\n\n"
                f"👤 Ученик: {student_name} (ID: {student_user_id})\n"
                f"📚 Предмет: {subject_name}\n"
                f"💸 Сумма: {amount:.2f} руб.\n\n"
                "✅ *Подтвердите получение денег:*"
            )

            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(
                    text="✅ Деньги получены",
                    callback_data=f"teacher_confirm_{student_user_id}_{amount}_{parent_user_id}"
                )],
                [types.InlineKeyboardButton(
                    text="❌ Деньги не получены",
                    callback_data=f"teacher_reject_{student_user_id}_{amount}_{parent_user_id}"
                )]
            ])

            await bot.send_message(
                teacher_id,
                message,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )

            logger.info(
                f"Уведомление отправлено преподавателю {teacher_id} о платеже для ученика {student_user_id} ({student_name}) от родителя {parent_user_id}")

        except Exception as e:
            logger.error(f"Ошибка уведомления преподавателя: {e}")

    @staticmethod
    async def _notify_teacher_about_payment_with_receipt(teacher_id: int, payment_data: Dict[str, Any],
                                                         file_id: str, file_type: str, payment_id: int):
        """Уведомляет преподавателя о новом платеже с чеком"""
        try:
            from main import bot

            message = (
                "💰 *НОВЫЙ ПЛАТЕЖ С ЧЕКОМ ТРЕБУЕТ ПОДТВЕРЖДЕНИЯ*\n\n"
                f"👤 Ученик: {payment_data['target_user_name']} (ID: {payment_data['target_user_id']})\n"
                f"📚 Предмет: {payment_data['subject_name']}\n"
                f"💸 Сумма: {payment_data['amount']:.2f} руб.\n"
                f"🆔 ID платежа: {payment_id}\n\n"
                "📎 Чек перевода прикреплен ниже\n\n"
                "✅ *Подтвердите получение денег:*"
            )

            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text="✅ Деньги получены",
                        callback_data=f"teacher_confirm_{payment_id}"
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text="❌ Деньги не получены",
                        callback_data=f"teacher_reject_{payment_id}"
                    )
                ]
            ])

            if file_type == "photo":
                await bot.send_photo(
                    teacher_id,
                    file_id,
                    caption=message,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            else:
                await bot.send_document(
                    teacher_id,
                    file_id,
                    caption=message,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )

            logger.info(f"Уведомление с чеком отправлено преподавателю {teacher_id}, payment_id: {payment_id}")

        except Exception as e:
            logger.error(f"Ошибка уведомления преподавателя с чеком: {e}")

    @staticmethod
    async def _notify_admin_about_payment_with_receipt(payment_data: dict, file_id: str, file_type: str):
        """Уведомляет администратора о платеже с чеком (если преподаватель не найден)"""
        try:
            from main import bot

            message = (
                "💰 *ПЛАТЕЖ С ЧЕКОМ - ПРЕПОДАВАТЕЛЬ НЕ НАЙДЕН*\n\n"
                f"👤 Ученик: {payment_data['target_user_name']} (ID: {payment_data['target_user_id']})\n"
                f"👨‍👩‍👧‍👦 Родитель: {payment_data.get('parent_user_name', 'Не указан')} (ID: {payment_data['parent_user_id']})\n"
                f"📚 Предмет: {payment_data['subject_name']}\n"
                f"💸 Сумма: {payment_data['amount']:.2f} руб.\n\n"
                "⚠️ Требуется ручная обработка платежа!"
            )

            # Отправляем администраторам
            for admin_id in ADMIN_IDS:
                try:
                    if file_type == "photo":
                        await bot.send_photo(
                            admin_id,
                            file_id,
                            caption=message,
                            parse_mode="Markdown"
                        )
                    else:
                        await bot.send_document(
                            admin_id,
                            file_id,
                            caption=message,
                            parse_mode="Markdown"
                        )
                except Exception as e:
                    logger.error(f"Ошибка отправки уведомления администратору {admin_id}: {e}")

        except Exception as e:
            logger.error(f"Ошибка уведомления администратора: {e}")

    @staticmethod
    async def _notify_teacher_about_payment(teacher_id: int, student_name: str, subject_name: str, amount: float,
                                            student_user_id: int, parent_user_id: int):
        """Уведомляет преподавателя о новом платеже"""
        try:
            from main import bot

            message = (
                "💰 *НОВЫЙ ПЛАТЕЖ ТРЕБУЕТ ПОДТВЕРЖДЕНИЯ*\n\n"
                f"👤 Ученик: {student_name} (ID: {student_user_id})\n"
                f"📚 Предмет: {subject_name}\n"
                f"💸 Сумма: {amount:.2f} руб.\n\n"
                "✅ *Подтвердите получение денег:*"
            )

            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [
                    types.InlineKeyboardButton(
                        text="✅ Деньги получены",
                        callback_data=f"teacher_confirm_{student_user_id}_{amount}_{parent_user_id}"
                    )
                ],
                [
                    types.InlineKeyboardButton(
                        text="❌ Деньги не получены",
                        callback_data=f"teacher_reject_{student_user_id}_{amount}_{parent_user_id}"
                    )
                ]
            ])

            await bot.send_message(
                teacher_id,
                message,
                reply_markup=keyboard,
                parse_mode="Markdown"
            )

            logger.info(
                f"Уведомление отправлено преподавателю {teacher_id} о платеже для ученика {student_user_id} ({student_name}) от родителя {parent_user_id}")

        except Exception as e:
            logger.error(f"Ошибка уведомления преподавателя: {e}")

    @staticmethod
    async def handle_receipt_upload(message: types.Message, state: FSMContext):
        """Обрабатывает загрузку чека перевода с сохранением в БД"""
        try:
            if not (message.photo or message.document):
                await message.answer("❌ Пожалуйста, отправьте скриншот или фото чека перевода.")
                return

            # Получаем данные платежа из состояния
            data = await state.get_data()
            payment_data = data.get('payment_data', {})

            if not payment_data:
                await message.answer("❌ Ошибка: данные платежа не найдены")
                await state.clear()
                return

            # Получаем информацию о файле
            file_id = None
            file_type = None
            file_data = {}

            if message.photo:
                file_id = message.photo[-1].file_id
                file_type = "photo"
                file_data = {
                    "file_id": file_id,
                    "file_unique_id": message.photo[-1].file_unique_id,
                    "width": message.photo[-1].width,
                    "height": message.photo[-1].height,
                    "file_size": message.photo[-1].file_size
                }
            elif message.document:
                file_id = message.document.file_id
                file_type = "document"
                file_data = {
                    "file_id": file_id,
                    "file_unique_id": message.document.file_unique_id,
                    "file_name": message.document.file_name,
                    "mime_type": message.document.mime_type,
                    "file_size": message.document.file_size
                }

            if not file_id:
                await message.answer("❌ Не удалось получить файл")
                return

            # Сохраняем контент в базу данных
            content_id = await db.save_content(
                added_by=message.from_user.id,
                content_type=file_type,
                file_data=file_data
            )

            # Сохраняем платеж с привязкой к контенту
            payment_id = await db.save_payment_with_content(
                from_user_id=message.from_user.id,
                to_user_id=payment_data.get('teacher_id'),
                content_id=content_id,
                amount=payment_data['amount'],
                subject_id=payment_data['subject_id'],
                target_user_id=payment_data['target_user_id']
            )

            await message.answer("✅ Чек получен и сохранен! Отправляем уведомление преподавателю...")

            # Уведомляем преподавателя
            teacher_id = payment_data.get('teacher_id')
            if teacher_id:
                await PaymentHandlers._notify_teacher_about_payment_with_receipt(
                    teacher_id, payment_data, file_id, file_type, payment_id
                )
                await message.answer("✅ Чек отправлен преподавателю. Ожидайте подтверждения.")
            else:
                await message.answer("⚠️ Преподаватель не найден. Обратитесь к администратору.")

            await state.clear()

        except Exception as e:
            logger.error(f"Ошибка обработки чека: {e}")
            await message.answer("❌ Произошла ошибка при обработке чека")
            await state.clear()

    @staticmethod
    async def handle_teacher_payment_confirmation(callback: types.CallbackQuery):
        """Обработка подтверждения платежа преподавателем с обновлением БД"""
        try:
            # Сразу отвечаем на callback чтобы избежать таймаута
            await callback.answer("⏳ Обрабатываю подтверждение...")

            # Извлекаем данные из callback_data: teacher_confirm_{payment_id}
            payment_id = int(callback.data.replace("teacher_confirm_", ""))
            logger.info(f"=== НАЧАЛО ОБРАБОТКИ ПОДТВЕРЖДЕНИЯ payment_id: {payment_id} ===")

            # Получаем данные платежа из БД
            payment = await db.get_payment_with_content(payment_id)

            if not payment:
                await callback.message.answer("❌ Платеж не найден")
                return

            # Проверяем статус платежа
            if payment.get('status') == 'confirmed':
                await callback.message.answer("ℹ️ Этот платеж уже был подтвержден ранее")
                return

            # Обновляем статус в БД
            await db.update_payment_status(payment_id, "confirmed", True)

            # Получаем данные для записи в Google Sheets
            student_user_id = payment['target_user_id']
            amount = float(payment['amount'])
            subject_id = payment['subject_id']
            teacher_id = callback.from_user.id

            from main import storage, bot

            # Получаем информацию о студенте и родителе
            student_name = storage.get_user_name(student_user_id)
            parent_user_id = payment['from_user_id']
            parent_name = storage.get_user_name(parent_user_id)

            # Получаем имя преподавателя
            teacher_name = storage.get_user_name(teacher_id)

            # Записываем платеж в Google Sheets
            success_student = await PaymentHandlers._write_payment_to_sheets(
                student_user_id, amount, subject_id
            )

            success_teacher = await PaymentHandlers._write_teacher_payment_to_sheets(
                teacher_id, amount
            )

            if success_student and success_teacher:
                # Обновляем выплаты для самозанятого
                success_payment_update = False
                try:
                    from main import gsheets
                    if gsheets and teacher_name:
                        success_payment_update = gsheets.update_self_employed_payment(teacher_name, amount)
                except Exception as e:
                    logger.error(f"Ошибка обновления выплат: {e}")

                # Уведомляем РОДИТЕЛЯ
                try:
                    from config import SUBJECTS
                    subject_name = SUBJECTS.get(subject_id, f"Предмет {subject_id}")

                    parent_message = (
                        "✅ *Платеж подтвержден преподавателем!*\n\n"
                        f"👤 Для ребенка: {student_name}\n"
                        f"📚 Предмет: {subject_name}\n"
                        f"💰 Сумма: {amount:.2f} руб.\n"
                        f"📊 Деньги зачислены на баланс ребенка!\n"
                        f"🎉 Услуга активирована!"
                    )

                    await bot.send_message(
                        parent_user_id,
                        parent_message,
                        parse_mode="Markdown"
                    )
                    logger.info(f"Уведомление о подтверждении платежа отправлено родителю {parent_user_id}")

                except Exception as e:
                    logger.error(f"Не удалось отправить уведомление родителю {parent_user_id}: {e}")

                # Сообщение преподавателю
                confirmation_message = (
                    f"✅ *Платеж подтвержден!*\n\n"
                    f"👤 Ученик: {student_name}\n"
                    f"👨‍👩‍👧‍👦 Родитель: {parent_name}\n"
                    f"💰 Сумма: {amount:.2f} руб.\n"
                    f"📊 Деньги записаны в таблицу\n"
                )

                if success_payment_update:
                    confirmation_message += f"💰 Выплата {amount:.2f} руб. добавлена к вашему балансу\n\n"
                else:
                    confirmation_message += f"⚠️ Ошибка обновления выплат (сообщите администратору)\n\n"

                confirmation_message += f"Родитель уведомлен о пополнении баланса."

                # Отправляем новое сообщение
                await callback.message.answer(
                    confirmation_message,
                    parse_mode="Markdown"
                )

                # Удаляем клавиатуру с исходного сообщения
                try:
                    await callback.message.edit_reply_markup(reply_markup=None)
                except:
                    pass

            else:
                await callback.message.answer("❌ Ошибка записи платежа в таблицу")

            logger.info(f"=== ЗАВЕРШЕНИЕ ОБРАБОТКИ ПОДТВЕРЖДЕНИЯ payment_id: {payment_id} ===")

        except Exception as e:
            logger.error(f"Ошибка подтверждения платежа преподавателем: {e}")
            await callback.message.answer("❌ Произошла ошибка при подтверждении платежа")

    @staticmethod
    async def handle_teacher_payment_rejection(callback: types.CallbackQuery):
        """Обработка отклонения платежа преподавателем"""
        try:
            # Извлекаем данные из callback_data: teacher_reject_{payment_id}
            payment_id = int(callback.data.replace("teacher_reject_", ""))
            logger.info(f"Отклонение платежа ID: {payment_id}")

            # Получаем данные платежа из БД
            payment = await db.get_payment_with_content(payment_id)

            if not payment:
                await callback.answer("❌ Платеж не найден", show_alert=True)
                return

            # Обновляем статус в БД
            await db.update_payment_status(payment_id, "rejected", False)

            from main import storage, bot

            # Получаем информацию о студенте и родителе
            student_user_id = payment['target_user_id']
            student_name = storage.get_user_name(student_user_id)
            parent_user_id = payment['from_user_id']
            amount = payment['amount']

            # Уведомляем РОДИТЕЛЯ
            try:
                parent_message = (
                    "❌ *Проблема с платежом*\n\n"
                    f"👤 Для ребенка: {student_name}\n"
                    f"💰 Сумма: {amount:.2f} руб.\n\n"
                    f"Преподаватель не подтвердил получение денег.\n"
                    f"Пожалуйста, проверьте:\n"
                    f"• Правильность реквизитов\n"
                    f"• Статус перевода в банке\n"
                    f"• Свяжитесь с администратором\n\n"
                    f"📞 Контакт: +79001372727"
                )

                await bot.send_message(
                    parent_user_id,
                    parent_message,
                    parse_mode="Markdown"
                )
                logger.info(f"Уведомление об отклонении платежа отправлено родителю {parent_user_id}")

            except Exception as e:
                logger.error(f"Не удалось отправить уведомление родителю {parent_user_id}: {e}")

            # Сообщение преподавателю - ОТПРАВЛЯЕМ НОВОЕ СООБЩЕНИЕ
            rejection_message = (
                f"❌ *Платеж отклонен*\n\n"
                f"👤 Ученик: {student_name}\n"
                f"💰 Сумма: {amount:.2f} руб.\n\n"
                f"Родитель уведомлен о проблеме с платежом."
            )

            await callback.message.answer(
                rejection_message,
                parse_mode="Markdown"
            )

            # Удаляем клавиатуру с исходного сообщения
            try:
                await callback.message.edit_reply_markup(reply_markup=None)
            except:
                pass  # Игнорируем ошибку если не удалось удалить клавиатуру

            await callback.answer("❌ Платеж отклонен")

        except Exception as e:
            logger.error(f"Ошибка отклонения платежа: {e}")
            logger.error(f"Трассировка: {traceback.format_exc()}")
            await callback.answer("❌ Произошла ошибка при отклонении платежа", show_alert=True)
    @staticmethod
    async def handle_debug_self_employed(callback: types.CallbackQuery):
        """Отладочная функция для проверки данных самозанятых"""
        try:
            from main import gsheets
            if not gsheets:
                await callback.answer("❌ Google Sheets не доступен", show_alert=True)
                return

            self_employed_info = gsheets.get_self_employed_with_lowest_balance(0)

            if not self_employed_info:
                await callback.answer("❌ Нет данных самозанятых", show_alert=True)
                return

            message = (
                f"👨‍🏫 Самозанятый с наименьшим балансом:\n"
                f"Имя: {self_employed_info.get('name', 'Не указано')}\n"
                f"Баланс: {self_employed_info.get('balance', 0):.2f} руб.\n"
                f"Карта: {self_employed_info.get('card_number', 'Не указана')}\n"
                f"Банк: {self_employed_info.get('bank', 'Не указан')}\n"
                f"Телефон: {self_employed_info.get('phone', 'Не указан')}"
            )

            await callback.answer(message, show_alert=True)

        except Exception as e:
            logger.error(f"Ошибка в debug_self_employed: {e}")
            await callback.answer("❌ Ошибка отладки", show_alert=True)

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

            # Сохраняем сумму в состоянии для дальнейшей оплаты
            await state.update_data(amount=amount)

            # Переходим к выбору способа оплаты (новый этап)
            from main import storage
            target_name = storage.get_user_name(target_user_id)
            from config import SUBJECTS
            subject_name = SUBJECTS.get(subject_id, f"Предмет {subject_id}")

            # Клавиатура с выбором способа оплаты
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(
                    text="💳 Оплатить через ЮKassa",
                    callback_data="confirm_yookassa_payment"
                )],
                [types.InlineKeyboardButton(
                    text="🔄 Сделать перевод напрямую",
                    callback_data="direct_transfer"
                )],
                [types.InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data="cancel_payment"
                )]
            ])

            await message.answer(
                f"💳 *Выберите способ оплаты:*\n\n"
                f"👤 Для: {target_name}\n"
                f"📚 Предмет: {subject_name}\n"
                f"💰 Сумма: {amount:.2f} руб.\n\n"
                f"*Варианты оплаты:*\n"
                f"• 💳 ЮKassa - онлайн оплата картой\n"
                f"• 🔄 Прямой перевод - на карту администратора",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )
            # Устанавливаем состояние для ожидания выбора способа оплаты
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

            if not amount:
                await callback.message.edit_text("❌ Ошибка: сумма не найдена")
                await state.clear()
                return

            from main import storage
            target_name = storage.get_user_name(target_user_id)
            from config import SUBJECTS
            subject_name = SUBJECTS.get(data.get('subject_id'), "Предмет")

            # Создаем клавиатуру с двумя вариантами оплаты
            keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                [types.InlineKeyboardButton(
                    text="💳 Оплатить через ЮKassa",
                    callback_data="confirm_yookassa_payment"
                )],
                [types.InlineKeyboardButton(
                    text="🔄 Сделать перевод напрямую",
                    callback_data="direct_transfer"
                )],
                [types.InlineKeyboardButton(
                    text="❌ Отменить",
                    callback_data="cancel_payment"
                )]
            ])

            await callback.message.edit_text(
                f"💳 *Выберите способ оплаты:*\n\n"
                f"👤 Для: {target_name}\n"
                f"📚 Предмет: {subject_name}\n"
                f"💰 Сумма: {amount:.2f} руб.\n\n"
                f"*Варианты оплаты:*\n"
                f"• 💳 ЮKassa - онлайн оплата картой\n"
                f"• 🔄 Прямой перевод - на карту администратора",
                reply_markup=keyboard,
                parse_mode="Markdown"
            )

        except Exception as e:
            logger.error(f"Ошибка в handle_confirm_payment: {e}")
            await callback.message.edit_text(f"❌ Ошибка при создании платежа: {str(e)}")
            await state.clear()

    @staticmethod
    async def handle_yookassa_payment(callback: types.CallbackQuery, state: FSMContext):
        """Создание платежа через ЮKassa после выбора этого способа"""
        try:
            data = await state.get_data()
            amount = data.get('amount')
            target_user_id = data.get('target_user_id')

            if not amount:
                await callback.message.edit_text("❌ Ошибка: сумма не найдена")
                await state.clear()
                return

            # Создаем платеж в ЮKassa (существующий функционал)
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

            # Создаем кнопки (существующий функционал)
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
    async def _write_payment_to_sheets(user_id: int, amount: float, subject_id: str = None) -> bool:
        """Записывает подтвержденный платеж в Google Sheets"""
        try:
            from main import gsheets, storage

            if not gsheets:
                logger.error("Google Sheets не доступен")
                return False

            # Если subject_id не указан, определяем автоматически
            if not subject_id:
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

            # Пробуем разные форматы дат для поиска
            date_formats = [
                "%d.%m.%Y",  # 05.11.2025
                "%d.%m",  # 05.11
                "%d.%m.%y",  # 05.11.25
            ]

            worksheet = gsheets._get_or_create_worksheet("Ученики бот")
            data = worksheet.get_all_values()

            if len(data) < 1:
                logger.error("Таблица 'Ученики бот' пустая")
                return False

            headers = [str(h).strip().lower() for h in data[0]]

            # Ищем финансовый столбец для текущей даты (разные форматы)
            target_col = -1

            for i in range(245, len(headers)):
                header = headers[i]
                if not header:
                    continue

                # Проверяем разные форматы дат в заголовке
                for date_format in date_formats:
                    try:
                        # Извлекаем дату из заголовка (может быть "05.11.2025 финансы" или просто "05.11.2025")
                        date_part = header.split()[0] if ' ' in header else header
                        parsed_date = datetime.strptime(date_part, date_format)

                        # Форматируем текущую дату в тот же формат для сравнения
                        current_formatted = datetime.now().strftime(date_format)
                        header_formatted = parsed_date.strftime(date_format)

                        if current_formatted == header_formatted:
                            target_col = i
                            logger.info(f"Найден финансовый столбец для даты {current_formatted}: индекс {i}")
                            break

                    except ValueError:
                        continue

                if target_col != -1:
                    break

            if target_col == -1:
                logger.error(f"Не найден финансовый столбец для текущей даты. Заголовки: {headers[245:250]}")
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
            if len(data) > target_row - 1 and len(data[target_row - 1]) > target_col:
                cell_value = data[target_row - 1][target_col].strip()
                if cell_value:
                    try:
                        # Очищаем строку от лишних символов
                        clean_value = cell_value.replace('\xa0', '').replace(' ', '').replace(',', '.')
                        import re
                        clean_value = re.sub(r'[^\d.-]', '', clean_value)

                        if clean_value:
                            current_value = float(clean_value)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Не удалось преобразовать значение '{cell_value}' в число: {e}")
                        current_value = 0.0

            # Вычисляем новое значение
            amount_float = float(amount)
            new_value = current_value + amount_float

            try:
                # Записываем новое значение в ячейку
                worksheet.update_cell(target_row, target_col + 1, f"{new_value:.2f}")

                # Получаем название предмета для логов
                from config import SUBJECTS
                subject_name = SUBJECTS.get(subject_id, f"Предмет {subject_id}")
                user_name = storage.get_user_name(user_id)

                logger.info(
                    f"💰 ПОДТВЕРЖДЕННЫЙ платеж записан в таблицу: {user_name} (ID:{user_id}), "
                    f"предмет: {subject_name} (ID:{subject_id}), "
                    f"сумма: {amount:.2f} руб., столбец: {target_col} ({headers[target_col]})"
                )

                return True
            except Exception as e:
                logger.error(f"Ошибка обновления ячейки для ученика {user_id}: {e}")
                return False

        except Exception as e:
            logger.error(f"Ошибка записи подтвержденного платежа в таблицу: {e}")
            return False

    @staticmethod
    async def _write_teacher_payment_to_sheets(user_id: int, amount: float) -> bool:
        """Записывает зарплату преподу от ученика в Google Sheets"""
        try:
            from main import gsheets, storage

            if not gsheets:
                logger.error("Google Sheets не доступен")
                return False

            from datetime import datetime

            # Пробуем разные форматы дат для поиска
            date_formats = [
                "%d.%m.%Y",  # 05.11.2025
                "%d.%m",  # 05.11
                "%d.%m.%y",  # 05.11.25
            ]

            worksheet = gsheets._get_or_create_worksheet("Преподаватели бот")
            data = worksheet.get_all_values()

            if len(data) < 1:
                logger.error("Таблица 'Преподаватели бот' пустая")
                return False

            headers = [str(h).strip().lower() for h in data[0]]

            # Ищем финансовый столбец для текущей даты (разные форматы)
            target_col = -1

            for i in range(244, len(headers)):
                header = headers[i]
                if not header:
                    continue

                # Проверяем разные форматы дат в заголовке
                for date_format in date_formats:
                    try:
                        # Извлекаем дату из заголовка
                        date_part = header.split()[0] if ' ' in header else header
                        parsed_date = datetime.strptime(date_part, date_format)

                        # Форматируем текущую дату в тот же формат для сравнения
                        current_formatted = datetime.now().strftime(date_format)
                        header_formatted = parsed_date.strftime(date_format)

                        if current_formatted == header_formatted:
                            target_col = i
                            logger.info(f"Найден финансовый столбец для преподавателя: индекс {i}")
                            break

                    except ValueError:
                        continue

                if target_col != -1:
                    break

            if target_col == -1:
                logger.error(f"Не найден финансовый столбец для преподавателя. Заголовки: {headers[244:249]}")
                return False

            # Ищем строку пользователя
            target_row = -1
            for row_idx, row in enumerate(data[1:], start=2):
                if (len(row) > 0 and str(row[0]).strip() == str(user_id)):
                    target_row = row_idx
                    break

            if target_row == -1:
                logger.error(f"Не найдена строка для препода с user_id {user_id}")
                return False

            # Получаем текущее значение ячейки
            current_value = 0.0
            if len(data) > target_row - 1 and len(data[target_row - 1]) > target_col:
                cell_value = data[target_row - 1][target_col].strip()
                if cell_value:
                    try:
                        # Очищаем строку от лишних символов
                        clean_value = cell_value.replace('\xa0', '').replace(' ', '').replace(',', '.')
                        import re
                        clean_value = re.sub(r'[^\d.-]', '', clean_value)

                        if clean_value:
                            current_value = float(clean_value)
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Не удалось преобразовать значение '{cell_value}' в число: {e}")
                        current_value = 0.0

            # Вычисляем новое значение
            amount_float = float(amount)
            new_value = current_value + amount_float

            try:
                # Записываем новое значение в ячейку
                worksheet.update_cell(target_row, target_col + 1, f"{new_value:.2f}")

                # Получаем имя преподавателя для логов
                user_name = storage.get_user_name(user_id)

                logger.info(
                    f"💰 ПОДТВЕРЖДЕННАЯ зарплата записана в таблицу: {user_name} (ID:{user_id}), "
                    f"сумма: {amount:.2f} руб., столбец: {target_col} ({headers[target_col]})"
                )

                return True
            except Exception as e:
                logger.error(f"Ошибка обновления ячейки для преподавателя {user_id}: {e}")
                return False

        except Exception as e:
            logger.error(f"Ошибка записи подтвержденной зарплаты в таблицу: {e}")
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
        
    # payment_handlers.py - добавить в класс PaymentHandlers

    @staticmethod
    async def handle_payment_confirmation(callback: types.CallbackQuery, state: FSMContext):
        """Обработка подтверждения оплаты и уведомление преподавателя"""
        try:
            # Получаем данные из состояния
            data = await state.get_data()
            amount = data.get('amount')
            target_user_id = data.get('target_user_id')
            subject_id = data.get('subject_id')

            if not all([amount, target_user_id, subject_id]):
                await callback.answer("❌ Ошибка: недостаточно данных", show_alert=True)
                return

            from main import storage, gsheets, bot
            target_name = storage.get_user_name(target_user_id)
            from config import SUBJECTS
            subject_name = SUBJECTS.get(subject_id, f"Предмет {subject_id}")

            # Ищем самозанятого с наименьшим балансом для уведомления
            self_employed_info = {}
            if gsheets:
                self_employed_info = gsheets.get_self_employed_with_lowest_balance(amount)

            # Формируем сообщение для пользователя
            user_message = (
                "✅ *Подтверждение оплаты получено!*\n\n"
                f"👤 Для: {target_name}\n"
                f"📚 Предмет: {subject_name}\n"
                f"💰 Сумма: {amount:.2f} руб.\n\n"
                "📋 Ваш платеж передан администратору для обработки.\n"
                "💰 Баланс будет пополнен после подтверждения получения денег.\n\n"
                "📞 Контакт администратора: +79001372727"
            )

            # Отправляем сообщение пользователю
            await callback.message.edit_text(
                user_message,
                parse_mode="Markdown",
                reply_markup=types.InlineKeyboardMarkup(inline_keyboard=[
                    [types.InlineKeyboardButton(
                        text="🔄 Новый платеж",
                        callback_data="new_payment"
                    )],
                    [types.InlineKeyboardButton(
                        text="📊 Проверить баланс",
                        callback_data="finance_start"
                    )]
                ])
            )

            # Уведомляем администратора о новом платеже
            admin_message = (
                "💰 *НОВЫЙ ПРЯМОЙ ПЛАТЕЖ*\n\n"
                f"👤 Ученик: {target_name} (ID: {target_user_id})\n"
                f"📚 Предмет: {subject_name}\n"
                f"💸 Сумма: {amount:.2f} руб.\n"
            )

            if self_employed_info and self_employed_info.get('name'):
                admin_message += f"👨‍🏫 Преподаватель: {self_employed_info['name']}\n\n"
            else:
                admin_message += "👨‍🏫 Преподаватель: не определен\n\n"

            admin_message += (
                "⚠️ Требуется подтверждение получения денег!\n"
                "💰 После подтверждения пополните баланс ученика."
            )

            # ID администратора (замените на реальный ID)
            # ADMIN_ID = [973231400]  # Замените на реальный ID администратора
            
            try:
                for i in range(len(ADMIN_IDS)):
                    await bot.send_message(
                        ADMIN_IDS[i],
                        admin_message,
                        parse_mode="Markdown"
                    )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления администратору: {e}")

            # Уведомляем преподавателя (если найден и есть контактные данные)
            if self_employed_info and self_employed_info.get('name'):
                # Ищем ID преподавателя по имени
                teacher_id = await PaymentHandlers._find_teacher_id_by_name(self_employed_info['name'])
                
                if teacher_id:
                    teacher_message = (
                        "💰 *УВЕДОМЛЕНИЕ О ПЛАТЕЖЕ*\n\n"
                        f"На ваш баланс должно было поступить *{amount:.2f} рублей*\n\n"
                        f"👤 От ученика: {target_name}\n"
                        f"📚 По предмету: {subject_name}\n\n"
                        "💳 После получения денег подтвердите оплату администратору."
                    )

                    try:
                        await bot.send_message(
                            teacher_id,
                            teacher_message,
                            parse_mode="Markdown"
                        )
                        logger.info(f"Уведомление отправлено преподавателю {self_employed_info['name']} (ID: {teacher_id})")
                    except Exception as e:
                        logger.error(f"Ошибка отправки уведомления преподавателю: {e}")

            await state.clear()
            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка в handle_payment_confirmation: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    @staticmethod
    async def _find_teacher_id_by_name(teacher_name: str) -> int:
        """Находит ID преподавателя по имени"""
        try:
            from main import gsheets
            
            if not gsheets:
                return None
                
            # Получаем данные из листа преподавателей
            worksheet = gsheets._get_or_create_worksheet("Преподаватели бот")
            data = worksheet.get_all_values()
            
            if len(data) < 2:
                return None
                
            # Ищем преподавателя по имени (столбец B, индекс 1)
            for row in data[1:]:  # Пропускаем заголовок
                if len(row) > 1 and row[1].strip() == teacher_name:
                    # Возвращаем user_id из столбца A (индекс 0)
                    if row[0] and row[0].strip().isdigit():
                        return int(row[0].strip())
                        
            return None
            
        except Exception as e:
            logger.error(f"Ошибка поиска ID преподавателя: {e}")
            return None