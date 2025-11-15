import logging
from aiogram import types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from datetime import datetime, timedelta
from database import db
from config import ADMIN_IDS
import calendar
import json

logger = logging.getLogger(__name__)


class AdminReceiptStates(StatesGroup):
    SELECT_DATE = State()
    VIEW_RECEIPTS = State()


class AdminReceiptsHandler:
    """Обработчик для просмотра чеков администратором"""

    @staticmethod
    async def handle_admin_receipts_start(message: types.Message, state: FSMContext):
        """Начало процесса просмотра чеков администратором"""
        try:
            if message.from_user.id not in ADMIN_IDS:
                await message.answer("❌ Эта команда только для администраторов")
                return

            await message.answer("📋 Просмотр чеков по датам")
            await AdminReceiptsHandler._show_date_selection(message, state)

        except Exception as e:
            logger.error(f"Ошибка в handle_admin_receipts_start: {e}")
            await message.answer("❌ Произошла ошибка")

    @staticmethod
    async def _show_date_selection(message: types.Message, state: FSMContext):
        """Показывает выбор даты"""
        try:
            # Получаем все даты, в которые есть чеки
            all_receipts = await db.get_all_receipts()
            dates_with_receipts = set()

            for receipt in all_receipts:
                if receipt.get('payment_date'):
                    date_str = receipt['payment_date'].strftime("%Y-%m-%d")
                    dates_with_receipts.add(date_str)

            # Сортируем даты по убыванию
            sorted_dates = sorted(dates_with_receipts, reverse=True)

            if not sorted_dates:
                await message.answer("📭 Чеков не найдено")
                return

            keyboard = AdminReceiptsHandler._generate_dates_keyboard(sorted_dates)

            await message.answer(
                "📅 Выберите дату для просмотра чеков:",
                reply_markup=keyboard
            )
            await state.set_state(AdminReceiptStates.SELECT_DATE)

        except Exception as e:
            logger.error(f"Ошибка в _show_date_selection: {e}")
            await message.answer("❌ Ошибка при загрузке дат")

    @staticmethod
    def _generate_dates_keyboard(dates_list):
        """Генерирует клавиатуру с датами, в которые есть чеки"""
        builder = InlineKeyboardBuilder()

        for date_str in dates_list[:10]:  # Показываем последние 10 дат
            date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            display_date = date_obj.strftime("%d.%m.%Y")

            # Проверяем, сегодня ли это
            today = datetime.now().date()
            if date_obj == today:
                display_text = f"📅 Сегодня ({display_date})"
            elif date_obj == today - timedelta(days=1):
                display_text = f"📅 Вчера ({display_date})"
            else:
                display_text = f"📅 {display_date}"

            builder.add(types.InlineKeyboardButton(
                text=display_text,
                callback_data=f"admin_receipt_date_{date_str}"
            ))

        builder.add(types.InlineKeyboardButton(
            text="🔄 Показать все чеки",
            callback_data="admin_receipt_show_all"
        ))

        builder.add(types.InlineKeyboardButton(
            text="❌ Закрыть",
            callback_data="admin_receipt_close"
        ))

        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    async def handle_date_selection(callback: types.CallbackQuery, state: FSMContext):
        """Обрабатывает выбор даты"""
        try:
            if callback.data == "admin_receipt_show_all":
                await AdminReceiptsHandler._show_all_receipts(callback, state)
                return

            if callback.data == "admin_receipt_close":
                await callback.message.delete()
                await state.clear()
                return

            # Извлекаем дату из callback_data
            date_str = callback.data.replace("admin_receipt_date_", "")
            selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()

            await state.update_data(selected_date=date_str)

            # Получаем чеки за выбранную дату
            receipts = await db.get_payments_by_date(selected_date)

            if not receipts:
                await callback.message.edit_text(
                    f"📅 За {selected_date.strftime('%d.%m.%Y')} чеков не найдено",
                    reply_markup=AdminReceiptsHandler._get_back_to_dates_keyboard()
                )
            else:
                await AdminReceiptsHandler._show_receipts_list(callback, receipts, selected_date)

        except Exception as e:
            logger.error(f"Ошибка в handle_date_selection: {e}")
            try:
                await callback.answer("❌ Ошибка при выборе даты", show_alert=True)
            except:
                pass

    @staticmethod
    async def _show_all_receipts(callback: types.CallbackQuery, state: FSMContext):
        """Показывает все чеки"""
        try:
            receipts = await db.get_all_receipts()

            if not receipts:
                await callback.message.edit_text(
                    "📭 Чеков не найдено",
                    reply_markup=AdminReceiptsHandler._get_back_to_dates_keyboard()
                )
                return

            # Группируем по датам
            receipts_by_date = {}
            for receipt in receipts:
                if receipt.get('payment_date'):
                    date_str = receipt['payment_date'].strftime("%Y-%m-%d")
                    if date_str not in receipts_by_date:
                        receipts_by_date[date_str] = []
                    receipts_by_date[date_str].append(receipt)

            # Показываем первую дату
            if receipts_by_date:
                first_date = list(receipts_by_date.keys())[0]
                selected_date = datetime.strptime(first_date, "%Y-%m-%d").date()
                await state.update_data(selected_date=first_date)
                await AdminReceiptsHandler._show_receipts_list(callback, receipts_by_date[first_date], selected_date)

        except Exception as e:
            logger.error(f"Ошибка в _show_all_receipts: {e}")
            try:
                await callback.answer("❌ Ошибка", show_alert=True)
            except:
                pass

    @staticmethod
    async def _get_receipts_for_date(date: datetime.date):
        """Получает все чеки за указанную дату"""
        try:
            return await db.get_payments_by_date(date)
        except Exception as e:
            logger.error(f"Ошибка в _get_receipts_for_date: {e}")
            return []

    @staticmethod
    async def _show_receipts_list(callback: types.CallbackQuery, receipts: list, selected_date: datetime.date):
        """Показывает список чеков за выбранную дату"""
        try:
            from main import storage

            message_text = f"📅 Чеки за {selected_date.strftime('%d.%m.%Y')}:\n\n"

            for i, receipt in enumerate(receipts, 1):
                # Получаем информацию о пользователях
                from_user_name = storage.get_user_name(receipt['from_user_id'])
                target_user_name = storage.get_user_name(receipt['target_user_id']) if receipt.get(
                    'target_user_id') else "Не указан"

                status_emoji = "✅" if receipt.get('status') == 'confirmed' else "⏳" if receipt.get(
                    'status') == 'pending' else "❌"

                # Проверяем наличие файла
                has_file = "📎" if receipt.get('file_id') else "❌"

                message_text += (
                    f"{i}. {has_file} Чек #{receipt['payment_id']}\n"
                    f"   👤 От: {from_user_name}\n"
                    f"   🎯 Для: {target_user_name}\n"
                    f"   💰 Сумма: {receipt.get('amount', 0):.2f} руб.\n"
                    f"   📊 Статус: {status_emoji} {receipt.get('status', 'unknown')}\n\n"
                )

            keyboard = AdminReceiptsHandler._get_receipts_list_keyboard(receipts, selected_date)

            await callback.message.edit_text(
                message_text,
                reply_markup=keyboard
            )

        except Exception as e:
            logger.error(f"Ошибка в _show_receipts_list: {e}")
            try:
                await callback.answer("❌ Ошибка при загрузке чеков", show_alert=True)
            except:
                pass

    @staticmethod
    def _get_receipts_list_keyboard(receipts: list, selected_date: datetime.date):
        """Генерирует клавиатуру для списка чеков"""
        builder = InlineKeyboardBuilder()

        # Кнопки для каждого чека
        for receipt in receipts:
            status_emoji = "✅" if receipt.get('status') == 'confirmed' else "📄"
            has_file_emoji = "📎" if receipt.get('file_id') else "❌"
            builder.add(types.InlineKeyboardButton(
                text=f"{has_file_emoji} {status_emoji} Чек #{receipt['payment_id']}",
                callback_data=f"admin_receipt_view_{receipt['payment_id']}"
            ))

        # Кнопки управления
        builder.row(types.InlineKeyboardButton(
            text="🔄 Обновить список",
            callback_data=f"admin_receipt_refresh_{selected_date.strftime('%Y-%m-%d')}"
        ))

        builder.row(types.InlineKeyboardButton(
            text="🔙 Назад к датам",
            callback_data="admin_receipt_back_to_dates"
        ))

        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    async def handle_receipt_view(callback: types.CallbackQuery, state: FSMContext):
        """Показывает конкретный чек"""
        try:
            payment_id = int(callback.data.replace("admin_receipt_view_", ""))

            # Получаем информацию о платеже с файлом
            payment = await db.get_payment_with_file(payment_id)

            if not payment:
                try:
                    await callback.answer("❌ Чек не найден", show_alert=True)
                except:
                    pass
                return

            from main import storage

            # Получаем информацию о пользователях
            from_user_name = storage.get_user_name(payment['from_user_id'])
            target_user_name = storage.get_user_name(payment['target_user_id']) if payment.get(
                'target_user_id') else "Не указан"
            to_user_name = storage.get_user_name(payment['to_user_id']) if payment.get('to_user_id') else "Не назначен"

            status_emoji = "✅" if payment.get('status') == 'confirmed' else "⏳" if payment.get(
                'status') == 'pending' else "❌"

            message_text = (
                f"📄 *Детали чека* #{payment_id}\n\n"
                f"💳 *ID платежа:* {payment_id}\n"
                f"👤 *От пользователя:* {from_user_name} (ID: {payment['from_user_id']})\n"
                f"🎯 *Для ученика:* {target_user_name} (ID: {payment['target_user_id']})\n"
                f"👨‍🏫 *Преподаватель:* {to_user_name} (ID: {payment['to_user_id']})\n"
                f"💰 *Сумма:* {payment['amount']:.2f} руб.\n"
                f"📚 *Предмет:* {payment.get('subject_id', 'Не указан')}\n"
                f"📊 *Статус:* {status_emoji} {payment.get('status', 'unknown')}\n"
                f"📅 *Дата:* {payment['payment_date'].strftime('%d.%m.%Y %H:%M')}\n"
            )

            keyboard = AdminReceiptsHandler._get_receipt_view_keyboard(payment_id, payment.get('status'))

            # Отправляем сообщение с деталями
            await callback.message.edit_text(
                message_text,
                parse_mode="Markdown",
                reply_markup=keyboard
            )

            # Отправляем сам чек (фото или документ)
            file_sent = await AdminReceiptsHandler._send_receipt_file(callback, payment)

            if not file_sent:
                # Если не удалось отправить файл, покажем отладочную информацию
                debug_info = await AdminReceiptsHandler._get_debug_info(payment)
                await callback.message.answer(f"🔍 Отладочная информация:\n{debug_info}")

        except Exception as e:
            logger.error(f"Ошибка в handle_receipt_view: {e}")
            try:
                await callback.answer("❌ Ошибка при загрузке чека", show_alert=True)
            except:
                pass

    @staticmethod
    async def _send_receipt_file(callback: types.CallbackQuery, payment: dict) -> bool:
        """Отправляет файл чека"""
        try:
            file_id = payment.get('file_id')
            content_type = payment.get('content_type')

            logger.info(f"Попытка отправить файл: type={content_type}, file_id={file_id}")

            if not file_id:
                await callback.message.answer("❌ Файл чека не найден в базе данных")
                return False

            if content_type == 'photo':
                await callback.message.answer_photo(
                    file_id,
                    caption="📎 Прикрепленный чек"
                )
                return True
            elif content_type == 'document':
                await callback.message.answer_document(
                    file_id,
                    caption="📎 Прикрепленный чек"
                )
                return True
            else:
                await callback.message.answer("❌ Неизвестный тип контента")
                return False

        except Exception as e:
            logger.error(f"Ошибка отправки файла: {e}")
            await callback.message.answer(f"❌ Ошибка отправки файла: {str(e)}")
            return False

    @staticmethod
    async def _get_debug_info(payment: dict) -> str:
        """Получает отладочную информацию о платеже"""
        try:
            debug_info = []

            debug_info.append(f"Payment ID: {payment.get('payment_id')}")
            debug_info.append(f"Content ID: {payment.get('content_id')}")
            debug_info.append(f"Content Type: {payment.get('content_type')}")
            debug_info.append(f"File ID: {payment.get('file_id')}")
            debug_info.append(f"Has content_data: {bool(payment.get('content_data'))}")

            if payment.get('content_data'):
                try:
                    data_dict = json.loads(payment['content_data'])
                    debug_info.append(f"Content data keys: {list(data_dict.keys())}")
                    debug_info.append(f"Full content_data: {payment['content_data']}")
                except Exception as e:
                    debug_info.append(f"Error parsing content_data: {e}")

            return "\n".join(debug_info)

        except Exception as e:
            return f"Error getting debug info: {e}"

    @staticmethod
    def _get_receipt_view_keyboard(payment_id: int, status: str):
        """Генерирует клавиатуру для просмотра чека"""
        builder = InlineKeyboardBuilder()

        # Только для неподтвержденных платежей показываем кнопки подтверждения
        if status != 'confirmed':
            builder.row(types.InlineKeyboardButton(
                text="✅ Подтвердить платеж",
                callback_data=f"admin_receipt_confirm_{payment_id}"
            ))

            builder.row(types.InlineKeyboardButton(
                text="❌ Отклонить платеж",
                callback_data=f"admin_receipt_reject_{payment_id}"
            ))

        builder.row(types.InlineKeyboardButton(
            text="🔙 Назад к списку",
            callback_data="admin_receipt_back_to_list"
        ))

        builder.adjust(1)
        return builder.as_markup()

    @staticmethod
    async def handle_receipt_refresh(callback: types.CallbackQuery, state: FSMContext):
        """Обновляет список чеков"""
        try:
            date_str = callback.data.replace("admin_receipt_refresh_", "")
            selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()

            receipts = await AdminReceiptsHandler._get_receipts_for_date(selected_date)

            if not receipts:
                await callback.message.edit_text(
                    f"📅 За {selected_date.strftime('%d.%m.%Y')} чеков не найдено",
                    reply_markup=AdminReceiptsHandler._get_back_to_dates_keyboard()
                )
            else:
                await AdminReceiptsHandler._show_receipts_list(callback, receipts, selected_date)

            try:
                await callback.answer("✅ Список обновлен")
            except:
                pass

        except Exception as e:
            logger.error(f"Ошибка в handle_receipt_refresh: {e}")
            try:
                await callback.answer("❌ Ошибка обновления", show_alert=True)
            except:
                pass

    @staticmethod
    async def handle_receipt_confirm(callback: types.CallbackQuery):
        """Подтверждает платеж администратором"""
        try:
            payment_id = int(callback.data.replace("admin_receipt_confirm_", ""))

            # Обновляем статус платежа
            await db.update_payment_status(payment_id, "confirmed", True)

            await callback.answer("✅ Платеж подтвержден")

            # Возвращаемся к списку чеков
            data = await callback.state.get_data()
            date_str = data.get('selected_date')
            if date_str:
                selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                receipts = await AdminReceiptsHandler._get_receipts_for_date(selected_date)
                await AdminReceiptsHandler._show_receipts_list(callback, receipts, selected_date)

        except Exception as e:
            logger.error(f"Ошибка в handle_receipt_confirm: {e}")
            try:
                await callback.answer("❌ Ошибка подтверждения", show_alert=True)
            except:
                pass

    @staticmethod
    async def handle_receipt_reject(callback: types.CallbackQuery):
        """Отклоняет платеж администратором"""
        try:
            payment_id = int(callback.data.replace("admin_receipt_reject_", ""))

            # Обновляем статус платежа
            await db.update_payment_status(payment_id, "rejected", False)

            await callback.answer("❌ Платеж отклонен")

            # Возвращаемся к списку чеков
            data = await callback.state.get_data()
            date_str = data.get('selected_date')
            if date_str:
                selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                receipts = await AdminReceiptsHandler._get_receipts_for_date(selected_date)
                await AdminReceiptsHandler._show_receipts_list(callback, receipts, selected_date)

        except Exception as e:
            logger.error(f"Ошибка в handle_receipt_reject: {e}")
            try:
                await callback.answer("❌ Ошибка отклонения", show_alert=True)
            except:
                pass

    @staticmethod
    async def handle_back_to_list(callback: types.CallbackQuery, state: FSMContext):
        """Возвращает к списку чеков"""
        try:
            data = await state.get_data()
            date_str = data.get('selected_date')

            if date_str:
                selected_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                receipts = await AdminReceiptsHandler._get_receipts_for_date(selected_date)

                if not receipts:
                    await callback.message.edit_text(
                        f"📅 За {selected_date.strftime('%d.%m.%Y')} чеков не найдено",
                        reply_markup=AdminReceiptsHandler._get_back_to_dates_keyboard()
                    )
                else:
                    await AdminReceiptsHandler._show_receipts_list(callback, receipts, selected_date)
            else:
                await AdminReceiptsHandler._show_date_selection(callback.message, state)

        except Exception as e:
            logger.error(f"Ошибка в handle_back_to_list: {e}")
            try:
                await callback.answer("❌ Ошибка", show_alert=True)
            except:
                pass

    @staticmethod
    async def handle_back_to_dates(callback: types.CallbackQuery, state: FSMContext):
        """Возвращает к выбору даты"""
        try:
            await AdminReceiptsHandler._show_date_selection(callback.message, state)
        except Exception as e:
            logger.error(f"Ошибка в handle_back_to_dates: {e}")
            try:
                await callback.answer("❌ Ошибка", show_alert=True)
            except:
                pass

    @staticmethod
    def _get_back_to_dates_keyboard():
        """Генерирует клавиатуру для возврата к датам"""
        builder = InlineKeyboardBuilder()

        builder.row(types.InlineKeyboardButton(
            text="🔙 Назад к датам",
            callback_data="admin_receipt_back_to_dates"
        ))

        return builder.as_markup()