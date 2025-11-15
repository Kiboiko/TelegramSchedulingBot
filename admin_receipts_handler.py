# admin_receipts_handler.py
from aiogram import types, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
import logging
from datetime import datetime, date
from typing import List, Dict, Any
from database import db

logger = logging.getLogger(__name__)


class AdminReceiptStates(StatesGroup):
    SELECT_VIEW_MODE = State()
    SELECT_DATE = State()
    SELECT_USER = State()
    VIEW_RECEIPTS_BY_DATE = State()
    VIEW_RECEIPTS_BY_USER = State()
    VIEW_USER_RECEIPTS_DATES = State()


class AdminReceiptsHandler:
    """Обработчик просмотра чеков для администратора"""

    @staticmethod
    async def handle_admin_receipts_start(message: types.Message, state: FSMContext):
        """Начало процесса просмотра чеков - выбор режима"""
        try:
            builder = InlineKeyboardBuilder()

            builder.add(types.InlineKeyboardButton(
                text="📅 Просмотреть чеки по дате",
                callback_data="admin_receipt_mode_date"
            ))
            builder.add(types.InlineKeyboardButton(
                text="👤 Просмотреть чеки пользователя",
                callback_data="admin_receipt_mode_user"
            ))
            builder.add(types.InlineKeyboardButton(
                text="❌ Закрыть",
                callback_data="admin_receipt_close"
            ))
            builder.adjust(1)

            await message.answer(
                "🔍 *Выберите режим просмотра чеков:*\n\n"
                "• 📅 *По дате* - выбрать дату и посмотреть все чеки за этот день\n"
                "• 👤 *По пользователю* - выбрать пользователя и посмотреть его чеки",
                reply_markup=builder.as_markup(),
                parse_mode="Markdown"
            )
            await state.set_state(AdminReceiptStates.SELECT_VIEW_MODE)

        except Exception as e:
            logger.error(f"Ошибка начала просмотра чеков: {e}")
            await message.answer("❌ Произошла ошибка")

    @staticmethod
    async def handle_view_mode_selection(callback: types.CallbackQuery, state: FSMContext):
        """Обработка выбора режима просмотра"""
        try:
            logger.info(f"Обработка handle_view_mode_selection: {callback.data}")

            if callback.data == "admin_receipt_mode_date":
                logger.info("Выбран режим по дате")
                await callback.message.edit_text(
                    "📅 Выберите дату для просмотра чеков:",
                    reply_markup=AdminReceiptsHandler.generate_receipts_calendar()
                )
                await state.set_state(AdminReceiptStates.SELECT_DATE)

            elif callback.data == "admin_receipt_mode_user":
                logger.info("Выбран режим по пользователю")
                await AdminReceiptsHandler._show_users_list(callback, state)

            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка выбора режима: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    @staticmethod
    async def _show_users_list(callback: types.CallbackQuery, state: FSMContext):
        """Показывает список пользователей, которые присылали чеки"""
        try:
            # Получаем всех пользователей, которые когда-либо присылали чеки
            all_receipts = await db.get_all_receipts()

            # Собираем уникальных пользователей
            users_dict = {}
            for receipt in all_receipts:
                user_id = receipt.get('from_user_id')
                if user_id and user_id not in users_dict:
                    # Получаем имя пользователя из storage
                    from main import storage
                    user_name = storage.get_user_name(user_id)
                    users_dict[user_id] = user_name or f"Пользователь {user_id}"

            if not users_dict:
                await callback.message.edit_text(
                    "❌ Нет пользователей с чеками",
                    reply_markup=InlineKeyboardBuilder().add(
                        types.InlineKeyboardButton(
                            text="🔙 Назад",
                            callback_data="admin_receipt_back_to_modes"
                        )
                    ).as_markup()
                )
                return

            builder = InlineKeyboardBuilder()

            for user_id, user_name in users_dict.items():
                builder.add(types.InlineKeyboardButton(
                    text=f"👤 {user_name} (ID: {user_id})",
                    callback_data=f"admin_receipt_select_user_{user_id}"
                ))

            builder.add(types.InlineKeyboardButton(
                text="🔙 Назад",
                callback_data="admin_receipt_back_to_modes"
            ))
            builder.adjust(1)

            await callback.message.edit_text(
                f"👤 Выберите пользователя для просмотра чеков:\n\n"
                f"Найдено пользователей: {len(users_dict)}",
                reply_markup=builder.as_markup()
            )
            await state.set_state(AdminReceiptStates.SELECT_USER)

        except Exception as e:
            logger.error(f"Ошибка показа списка пользователей: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    @staticmethod
    async def handle_user_selection(callback: types.CallbackQuery, state: FSMContext):
        """Обработка выбора пользователя - ФИКС пустых дат"""
        try:
            user_id = int(callback.data.replace("admin_receipt_select_user_", ""))

            from main import storage
            user_name = storage.get_user_name(user_id) or f"Пользователь {user_id}"

            # Получаем ВСЕ платежи пользователя
            user_receipts = await db.get_user_payments(user_id, limit=1000)

            if not user_receipts:
                await callback.message.edit_text(
                    f"👤 {user_name}\n\n"
                    f"❌ У пользователя нет чеков",
                    reply_markup=InlineKeyboardBuilder().add(
                        types.InlineKeyboardButton(
                            text="🔙 Назад к пользователям",
                            callback_data="admin_receipt_back_to_users"
                        )
                    ).as_markup()
                )
                return

            # Собираем даты ТОЛЬКО из чеков, которые действительно существуют
            dates_dict = {}
            for receipt in user_receipts:
                payment_date = receipt.get('payment_date')
                if payment_date:
                    try:
                        if isinstance(payment_date, str):
                            payment_date = datetime.fromisoformat(payment_date.replace('Z', '+00:00'))

                        # Проверяем, что чек действительно имеет content_id (файл)
                        if receipt.get('content_id'):
                            date_str = payment_date.strftime("%Y-%m-%d")
                            date_display = payment_date.strftime("%d.%m.%Y")
                            if date_str not in dates_dict:
                                dates_dict[date_str] = {
                                    'display': date_display,
                                    'count': 1
                                }
                            else:
                                dates_dict[date_str]['count'] += 1

                    except Exception as e:
                        logger.error(f"Ошибка обработки даты чека {receipt.get('payment_id')}: {e}")
                        continue

            if not dates_dict:
                await callback.message.edit_text(
                    f"👤 {user_name}\n\n"
                    f"❌ У пользователя нет чеков с файлами",
                    reply_markup=InlineKeyboardBuilder().add(
                        types.InlineKeyboardButton(
                            text="🔙 Назад к пользователям",
                            callback_data="admin_receipt_back_to_users"
                        )
                    ).as_markup()
                )
                return

            builder = InlineKeyboardBuilder()

            # Сортируем даты по убыванию
            sorted_dates = sorted(dates_dict.items(), key=lambda x: x[0], reverse=True)

            for date_str, date_info in sorted_dates:
                builder.add(types.InlineKeyboardButton(
                    text=f"📅 {date_info['display']} ({date_info['count']} чеков)",
                    callback_data=f"admin_receipt_user_date_{user_id}_{date_str}"
                ))

            builder.add(types.InlineKeyboardButton(
                text="🔙 Назад к пользователям",
                callback_data="admin_receipt_back_to_users"
            ))
            builder.adjust(1)

            await callback.message.edit_text(
                f"👤 {user_name}\n\n"
                f"📅 Выберите дату для просмотра чеков пользователя:\n"
                f"Найдено дат с чеками: {len(dates_dict)}",
                reply_markup=builder.as_markup()
            )
            await state.set_state(AdminReceiptStates.VIEW_USER_RECEIPTS_DATES)
            await state.update_data(selected_user_id=user_id, selected_user_name=user_name)

        except Exception as e:
            logger.error(f"Ошибка выбора пользователя: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    @staticmethod
    async def handle_user_date_selection(callback: types.CallbackQuery, state: FSMContext):
        """Обработка выбора даты для конкретного пользователя"""
        try:
            data_parts = callback.data.replace("admin_receipt_user_date_", "").split("_")
            user_id = int(data_parts[0])
            date_str = "_".join(data_parts[1:])

            state_data = await state.get_data()
            user_name = state_data.get('selected_user_name', f"Пользователь {user_id}")

            # Сохраняем выбранную дату в состоянии
            await state.update_data(selected_date=date_str)

            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

            # Получаем ВСЕ чеки пользователя и фильтруем по дате
            user_receipts = await db.get_user_payments(user_id, limit=1000)

            filtered_receipts = []
            for receipt in user_receipts:
                payment_date = receipt.get('payment_date')
                if payment_date:
                    try:
                        if isinstance(payment_date, str):
                            payment_date = datetime.fromisoformat(payment_date.replace('Z', '+00:00'))

                        # Фильтруем по дате И проверяем что есть файл
                        if (payment_date.date() == target_date and
                                receipt.get('content_id') is not None):
                            filtered_receipts.append(receipt)

                    except Exception as e:
                        logger.error(f"Ошибка фильтрации чека {receipt.get('payment_id')}: {e}")
                        continue

            if not filtered_receipts:
                await callback.message.edit_text(
                    f"👤 {user_name}\n"
                    f"📅 {target_date.strftime('%d.%m.%Y')}\n\n"
                    f"❌ Нет чеков с файлами за выбранную дату",
                    reply_markup=InlineKeyboardBuilder().add(
                        types.InlineKeyboardButton(
                            text="🔙 Назад к датам",
                            callback_data=f"admin_receipt_back_to_user_dates_{user_id}"
                        )
                    ).as_markup()
                )
                return

            await AdminReceiptsHandler._show_receipts_list(
                callback,
                filtered_receipts,
                f"👤 {user_name}\n📅 {target_date.strftime('%d.%m.%Y')}\n📊 Чеков: {len(filtered_receipts)}",
                f"admin_receipt_back_to_user_dates_{user_id}"
            )

        except Exception as e:
            logger.error(f"Ошибка выбора даты пользователя: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    @staticmethod
    async def handle_date_selection(callback: types.CallbackQuery, state: FSMContext):
        """Обработка выбора даты в календаре чеков"""
        try:
            logger.info(f"Обработка handle_date_selection: {callback.data}")

            if callback.data.startswith("admin_receipt_date_"):
                date_str = callback.data.replace("admin_receipt_date_", "")
                logger.info(f"Выбрана дата: {date_str}")

                year, month, day = map(int, date_str.split("-"))
                selected_date = datetime(year, month, day).date()

                # Сохраняем выбранную дату в состоянии
                await state.update_data(selected_date=date_str)

                # Показываем пользователей, которые отправляли чеки за эту дату
                await AdminReceiptsHandler._show_users_for_date(callback, state)

            elif callback.data.startswith("admin_receipt_calendar_change_"):
                # Обработка смены месяца в календаре чеков
                date_str = callback.data.replace("admin_receipt_calendar_change_", "")
                year, month = map(int, date_str.split("-"))

                await callback.message.edit_reply_markup(
                    reply_markup=AdminReceiptsHandler.generate_receipts_calendar(year, month)
                )
                await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка выбора даты: {e}")
            await callback.answer("❌ Ошибка выбора даты", show_alert=True)

    @staticmethod
    async def _show_receipts_list(callback: types.CallbackQuery, receipts: List[Dict], title: str, back_callback: str):
        """Показывает список чеков - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
        try:
            logger.info(f"Показ списка чеков: {title}, чеков: {len(receipts)}, back_callback: {back_callback}")

            builder = InlineKeyboardBuilder()

            for receipt in receipts:
                payment_id = receipt.get('payment_id')
                amount = receipt.get('amount', 0)
                status = receipt.get('status', 'unknown')

                status_emoji = {
                    'pending': '⏳',
                    'confirmed': '✅',
                    'rejected': '❌'
                }.get(status, '❓')

                builder.add(types.InlineKeyboardButton(
                    text=f"{status_emoji} Чек #{payment_id} - {amount:.2f} руб.",
                    callback_data=f"admin_receipt_view_{payment_id}"
                ))

            builder.add(types.InlineKeyboardButton(
                text="🔙 Назад",
                callback_data=back_callback
            ))
            builder.adjust(1)

            await callback.message.edit_text(
                f"{title}\n\n"
                f"Найдено чеков: {len(receipts)}",
                reply_markup=builder.as_markup()
            )

        except Exception as e:
            logger.error(f"Ошибка показа списка чеков: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    @staticmethod
    async def handle_back_to_modes(callback: types.CallbackQuery, state: FSMContext):
        """Возврат к выбору режима просмотра"""
        await AdminReceiptsHandler.handle_admin_receipts_start(callback.message, state)
        try:
            await callback.message.delete()
        except:
            pass

    @staticmethod
    async def handle_back_to_users(callback: types.CallbackQuery, state: FSMContext):
        """Возврат к списку пользователей"""
        await AdminReceiptsHandler._show_users_list(callback, state)

    @staticmethod
    async def handle_back_to_user_dates(callback: types.CallbackQuery, state: FSMContext):
        """Возврат к датам пользователя - ИСПРАВЛЕННАЯ ВЕРСИЯ"""
        try:
            # Получаем user_id из состояния, а не из callback_data
            state_data = await state.get_data()
            user_id = state_data.get('selected_user_id')

            if not user_id:
                logger.error("user_id не найден в состоянии")
                await AdminReceiptsHandler.handle_back_to_users(callback, state)
                return

            logger.info(f"Возврат к датам пользователя {user_id}")

            from main import storage
            user_name = storage.get_user_name(user_id) or f"Пользователь {user_id}"

            # Получаем чеки пользователя
            user_receipts = await db.get_user_payments(user_id, limit=1000)

            dates_dict = {}
            for receipt in user_receipts:
                payment_date = receipt.get('payment_date')
                if payment_date:
                    try:
                        if isinstance(payment_date, str):
                            payment_date = datetime.fromisoformat(payment_date.replace('Z', '+00:00'))

                        if receipt.get('content_id'):
                            date_str = payment_date.strftime("%Y-%m-%d")
                            date_display = payment_date.strftime("%d.%m.%Y")
                            if date_str not in dates_dict:
                                dates_dict[date_str] = {
                                    'display': date_display,
                                    'count': 1
                                }
                            else:
                                dates_dict[date_str]['count'] += 1

                    except Exception as e:
                        logger.error(f"Ошибка обработки даты чека: {e}")
                        continue

            if not dates_dict:
                await callback.message.edit_text(
                    f"👤 {user_name}\n\n"
                    f"❌ У пользователя нет чеков с файлами",
                    reply_markup=InlineKeyboardBuilder().add(
                        types.InlineKeyboardButton(
                            text="🔙 Назад к пользователям",
                            callback_data="admin_receipt_back_to_users"
                        )
                    ).as_markup()
                )
                return

            builder = InlineKeyboardBuilder()
            sorted_dates = sorted(dates_dict.items(), key=lambda x: x[0], reverse=True)

            for date_str, date_info in sorted_dates:
                builder.add(types.InlineKeyboardButton(
                    text=f"📅 {date_info['display']} ({date_info['count']} чеков)",
                    callback_data=f"admin_receipt_user_date_{user_id}_{date_str}"
                ))

            builder.add(types.InlineKeyboardButton(
                text="🔙 Назад к пользователям",
                callback_data="admin_receipt_back_to_users"
            ))
            builder.adjust(1)

            await callback.message.edit_text(
                f"👤 {user_name}\n\n"
                f"📅 Выберите дату для просмотра чеков пользователя:",
                reply_markup=builder.as_markup()
            )
            await state.set_state(AdminReceiptStates.VIEW_USER_RECEIPTS_DATES)

        except Exception as e:
            logger.error(f"Ошибка возврата к датам пользователя: {e}")
            await callback.answer("❌ Ошибка возврата", show_alert=True)

    # Остальные методы остаются без изменений...
    @staticmethod
    async def handle_receipt_view(callback: types.CallbackQuery, state: FSMContext):
        """Просмотр конкретного чека"""
        try:
            payment_id = int(callback.data.replace("admin_receipt_view_", ""))
            payment = await db.get_payment_with_file(payment_id)

            if not payment:
                await callback.answer("❌ Чек не найден", show_alert=True)
                return

            from main import storage

            message_text = (
                f"📋 *Информация о чеке* #{payment_id}\n\n"
                f"👤 *Пользователь:* {storage.get_user_name(payment['from_user_id'])} (ID: {payment['from_user_id']})\n"
                f"💰 *Сумма:* {payment['amount']:.2f} руб.\n"
                f"📅 *Дата:* {payment['payment_date'].strftime('%d.%m.%Y %H:%M')}\n"
                f"📊 *Статус:* {payment['status']}\n"
            )

            if payment.get('target_user_id'):
                message_text += f"🎯 *Для пользователя:* {storage.get_user_name(payment['target_user_id'])} (ID: {payment['target_user_id']})\n"

            if payment.get('subject_id'):
                from config import SUBJECTS
                subject_name = SUBJECTS.get(payment['subject_id'], f"Предмет {payment['subject_id']}")
                message_text += f"📚 *Предмет:* {subject_name}\n"

            keyboard_buttons = []

            if payment.get('file_id'):
                if payment.get('content_type') == 'photo':
                    await callback.message.answer_photo(
                        payment['file_id'],
                        caption=message_text,
                        parse_mode="Markdown"
                    )
                else:
                    await callback.message.answer_document(
                        payment['file_id'],
                        caption=message_text,
                        parse_mode="Markdown"
                    )
            else:
                await callback.message.answer(message_text, parse_mode="Markdown")

            # Кнопки действий (БЕЗ КНОПКИ ОБНОВЛЕНИЯ)
            if payment['status'] == 'pending':
                keyboard_buttons.append([
                    types.InlineKeyboardButton(
                        text="✅ Подтвердить получение",
                        callback_data=f"admin_receipt_confirm_{payment_id}"
                    )
                ])
                keyboard_buttons.append([
                    types.InlineKeyboardButton(
                        text="❌ Отклонить",
                        callback_data=f"admin_receipt_reject_{payment_id}"
                    )
                ])

            keyboard_buttons.append([
                types.InlineKeyboardButton(
                    text="🔙 Назад к списку",
                    callback_data="admin_receipt_back_to_list"
                )
            ])

            keyboard = types.InlineKeyboardMarkup(inline_keyboard=keyboard_buttons)
            await callback.message.answer("Действия:", reply_markup=keyboard)

            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка просмотра чека: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    # Остальные методы (handle_receipt_confirm, handle_receipt_reject и т.д.) остаются без изменений
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
    async def handle_receipt_refresh(callback: types.CallbackQuery, state: FSMContext):
        """Обновление информации о чеке"""
        try:
            payment_id = int(callback.data.replace("admin_receipt_refresh_", ""))

            # Получаем обновленные данные
            payment = await db.get_payment_with_file(payment_id)

            if not payment:
                await callback.answer("❌ Чек не найден", show_alert=True)
                return

            # Удаляем старое сообщение и показываем обновленное
            try:
                await callback.message.delete()
            except:
                pass

            # Заново показываем чек с обновленной информацией
            await AdminReceiptsHandler.handle_receipt_view(callback, state)

            await callback.answer("✅ Информация обновлена")

        except Exception as e:
            logger.error(f"Ошибка обновления чека: {e}")
            await callback.answer("❌ Ошибка при обновлении", show_alert=True)

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
    def generate_receipts_calendar(year=None, month=None):
        """Генерирует календарь для просмотра чеков (на основе вашего рабочего календаря)"""
        from datetime import datetime, timedelta
        from aiogram import types
        from aiogram.utils.keyboard import InlineKeyboardBuilder

        now = datetime.now()
        if year is None:
            year = now.year
        if month is None:
            month = now.month

        builder = InlineKeyboardBuilder()

        # Заголовок с месяцем и годом
        month_name = datetime(year, month, 1).strftime("%B %Y")
        builder.row(types.InlineKeyboardButton(
            text=month_name,
            callback_data="admin_receipt_ignore"
        ))

        # Дни недели
        week_days = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]
        builder.row(*[
            types.InlineKeyboardButton(text=day, callback_data="admin_receipt_ignore")
            for day in week_days
        ])

        # Генерация дней месяца
        first_day = datetime(year, month, 1)
        start_weekday = first_day.weekday()  # 0-6 (пн-вс)
        days_in_month = (datetime(year, month + 1, 1) - first_day).days if month < 12 else 31

        buttons = []
        # Пустые кнопки для дней предыдущего месяца
        for _ in range(start_weekday):
            buttons.append(types.InlineKeyboardButton(
                text=" ",
                callback_data="admin_receipt_ignore"
            ))

        # Кнопки дней текущего месяца - ВСЕ ДАТЫ ДОСТУПНЫ для чеков
        for day in range(1, days_in_month + 1):
            current_date = datetime(year, month, day).date()

            # Для чеков ВСЕ даты активны, включая прошедшие
            buttons.append(types.InlineKeyboardButton(
                text=str(day),
                callback_data=f"admin_receipt_date_{year}-{month}-{day}"
            ))

            # Перенос строки после каждого воскресенья
            if (day + start_weekday) % 7 == 0 or day == days_in_month:
                builder.row(*buttons)
                buttons = []

        # Кнопки навигации
        prev_month = month - 1 if month > 1 else 12
        prev_year = year if month > 1 else year - 1
        next_month = month + 1 if month < 12 else 1
        next_year = year if month < 12 else year + 1

        nav_buttons = []

        # Всегда показываем кнопку "назад" для навигации
        nav_buttons.append(types.InlineKeyboardButton(
            text="⬅️",
            callback_data=f"admin_receipt_calendar_change_{prev_year}-{prev_month}"
        ))

        # Всегда показываем кнопку "вперед"
        nav_buttons.append(types.InlineKeyboardButton(
            text="➡️",
            callback_data=f"admin_receipt_calendar_change_{next_year}-{next_month}"
        ))

        builder.row(*nav_buttons)

        return builder.as_markup()

    @staticmethod
    async def handle_back_to_list(callback: types.CallbackQuery, state: FSMContext):
        """Возврат к списку чеков - РАБОЧАЯ ВЕРСИЯ"""
        try:
            logger.info("Обработка handle_back_to_list")

            # Получаем данные из состояния
            state_data = await state.get_data()

            # Проверяем контекст по данным состояния
            if state_data.get('selected_user_id') and state_data.get('selected_date'):
                # Это был просмотр чеков конкретного пользователя за дату
                # Возвращаемся к списку дат этого пользователя
                user_id = state_data['selected_user_id']
                await AdminReceiptsHandler.handle_back_to_user_dates(callback, state)

            elif state_data.get('selected_date') and not state_data.get('selected_user_id'):
                # Это был просмотр чеков по дате (все пользователи)
                # Возвращаемся к списку пользователей за эту дату
                await AdminReceiptsHandler._show_users_for_date(callback, state)

            else:
                # Fallback - возвращаем к выбору режима
                await AdminReceiptsHandler.handle_back_to_modes(callback, state)

        except Exception as e:
            logger.error(f"Ошибка возврата к списку: {e}")
            await callback.answer("❌ Ошибка возврата", show_alert=True)

    @staticmethod
    async def _show_users_for_date(callback: types.CallbackQuery, state: FSMContext):
        """Показывает пользователей, которые отправляли чеки за выбранную дату"""
        try:
            state_data = await state.get_data()
            date_str = state_data.get('selected_date')

            if not date_str:
                await callback.answer("❌ Не найдена информация о дате", show_alert=True)
                return

            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

            # Получаем все чеки за выбранную дату
            receipts = await db.get_payments_by_date(target_date)

            if not receipts:
                builder = InlineKeyboardBuilder()
                builder.add(types.InlineKeyboardButton(
                    text="🔙 Назад к датам",
                    callback_data="admin_receipt_back_to_dates"
                ))

                await callback.message.edit_text(
                    f"📅 {target_date.strftime('%d.%m.%Y')}\n\n"
                    f"❌ Нет чеков за выбранную дату",
                    reply_markup=builder.as_markup()
                )
                return

            # Собираем уникальных пользователей
            users_dict = {}
            for receipt in receipts:
                user_id = receipt.get('from_user_id')
                if user_id and user_id not in users_dict:
                    from main import storage
                    user_name = storage.get_user_name(user_id) or f"Пользователь {user_id}"
                    users_dict[user_id] = user_name

            if not users_dict:
                builder = InlineKeyboardBuilder()
                builder.add(types.InlineKeyboardButton(
                    text="🔙 Назад к датам",
                    callback_data="admin_receipt_back_to_dates"
                ))

                await callback.message.edit_text(
                    f"📅 {target_date.strftime('%d.%m.%Y')}\n\n"
                    f"❌ Не удалось определить пользователей",
                    reply_markup=builder.as_markup()
                )
                return

            builder = InlineKeyboardBuilder()

            for user_id, user_name in users_dict.items():
                # Считаем количество чеков этого пользователя за дату
                user_receipts_count = sum(1 for r in receipts if r.get('from_user_id') == user_id)

                builder.add(types.InlineKeyboardButton(
                    text=f"👤 {user_name} ({user_receipts_count} чеков)",
                    callback_data=f"admin_receipt_user_for_date_{user_id}_{date_str}"
                ))

            builder.add(types.InlineKeyboardButton(
                text="🔙 Назад к датам",
                callback_data="admin_receipt_back_to_dates"
            ))
            builder.adjust(1)

            await callback.message.edit_text(
                f"📅 {target_date.strftime('%d.%m.%Y')}\n\n"
                f"👥 Пользователи, отправлявшие чеки:\n"
                f"Найдено пользователей: {len(users_dict)}",
                reply_markup=builder.as_markup()
            )

        except Exception as e:
            logger.error(f"Ошибка показа пользователей за дату: {e}")
            await callback.answer("❌ Ошибка", show_alert=True)

    @staticmethod
    async def handle_user_for_date_selection(callback: types.CallbackQuery, state: FSMContext):
        """Обработка выбора пользователя для просмотра его чеков за дату"""
        try:
            data_parts = callback.data.replace("admin_receipt_user_for_date_", "").split("_")
            user_id = int(data_parts[0])
            date_str = "_".join(data_parts[1:])

            from main import storage
            user_name = storage.get_user_name(user_id) or f"Пользователь {user_id}"

            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

            # Получаем все чеки за выбранную дату
            all_receipts = await db.get_payments_by_date(target_date)

            # Фильтруем чеки только этого пользователя
            user_receipts = [r for r in all_receipts if r.get('from_user_id') == user_id]

            if not user_receipts:
                builder = InlineKeyboardBuilder()
                builder.add(types.InlineKeyboardButton(
                    text="🔙 Назад к пользователям",
                    callback_data=f"admin_receipt_back_to_users_for_date_{date_str}"
                ))

                await callback.message.edit_text(
                    f"👤 {user_name}\n"
                    f"📅 {target_date.strftime('%d.%m.%Y')}\n\n"
                    f"❌ Нет чеков этого пользователя за выбранную дату",
                    reply_markup=builder.as_markup()
                )
                return

            # Сохраняем данные в состоянии для кнопки "Назад"
            await state.update_data(
                selected_user_id=user_id,
                selected_user_name=user_name,
                selected_date=date_str
            )

            await AdminReceiptsHandler._show_receipts_list(
                callback,
                user_receipts,
                f"👤 {user_name}\n📅 {target_date.strftime('%d.%m.%Y')}\n📊 Чеков: {len(user_receipts)}",
                "admin_receipt_back_to_list"
            )

        except Exception as e:
            logger.error(f"Ошибка выбора пользователя для даты: {e}")
            await callback.answer("❌ Произошла ошибка", show_alert=True)

    @staticmethod
    async def handle_back_to_users_for_date(callback: types.CallbackQuery, state: FSMContext):
        """Возврат к списку пользователей за дату"""
        try:
            # Получаем date_str из callback_data
            date_str = callback.data.replace("admin_receipt_back_to_users_for_date_", "")

            # Сохраняем дату в состоянии
            await state.update_data(selected_date=date_str)

            # Показываем пользователей за эту дату
            await AdminReceiptsHandler._show_users_for_date(callback, state)

        except Exception as e:
            logger.error(f"Ошибка возврата к пользователям за дату: {e}")
            await callback.answer("❌ Ошибка возврата", show_alert=True)

    @staticmethod
    async def _show_user_receipts_for_date(callback: types.CallbackQuery, state: FSMContext, user_id: int):
        """Показывает чеки пользователя за выбранную дату"""
        try:
            state_data = await state.get_data()
            date_str = state_data.get('selected_date')
            user_name = state_data.get('selected_user_name', f"Пользователь {user_id}")

            if not date_str:
                await callback.answer("❌ Не найдена информация о дате", show_alert=True)
                return

            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()

            # Получаем чеки пользователя за эту дату
            all_receipts = await db.get_all_receipts()
            user_receipts = []

            for receipt in all_receipts:
                if receipt.get('from_user_id') == user_id:
                    payment_date = receipt.get('payment_date')
                    if payment_date:
                        if isinstance(payment_date, str):
                            payment_date = datetime.fromisoformat(payment_date.replace('Z', '+00:00'))
                        if payment_date.date() == target_date and receipt.get('content_id'):
                            user_receipts.append(receipt)

            await AdminReceiptsHandler._show_receipts_list(
                callback,
                user_receipts,
                f"👤 {user_name}\n📅 {target_date.strftime('%d.%m.%Y')}",
                f"admin_receipt_back_to_user_dates_{user_id}"
            )

        except Exception as e:
            logger.error(f"Ошибка показа чеков пользователя: {e}")
            await callback.answer("❌ Ошибка", show_alert=True)

    @staticmethod
    async def _show_receipts_for_selected_date(callback: types.CallbackQuery, state: FSMContext):
        """Показывает чеки за выбранную дату"""
        try:
            state_data = await state.get_data()
            date_str = state_data.get('selected_date')

            if not date_str:
                await callback.answer("❌ Не найдена информация о дате", show_alert=True)
                return

            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
            receipts = await db.get_payments_by_date(target_date)

            await AdminReceiptsHandler._show_receipts_list(
                callback,
                receipts,
                f"📅 {target_date.strftime('%d.%m.%Y')}",
                "admin_receipt_back_to_dates"
            )

        except Exception as e:
            logger.error(f"Ошибка показа чеков по дате: {e}")
            await callback.answer("❌ Ошибка", show_alert=True)

    @staticmethod
    async def handle_back_to_dates(callback: types.CallbackQuery, state: FSMContext):
        """Возврат к выбору даты"""
        try:
            logger.info("Обработка handle_back_to_dates")

            await callback.message.edit_text(
                "📅 Выберите дату для просмотра чеков:",
                reply_markup=AdminReceiptsHandler.generate_receipts_calendar()
            )
            await state.set_state(AdminReceiptStates.SELECT_DATE)

        except Exception as e:
            logger.error(f"Ошибка возврата к датам: {e}")
            await callback.answer("❌ Ошибка возврата к датам", show_alert=True)

    @staticmethod
    def _get_back_to_dates_keyboard():
        """Генерирует клавиатуру для возврата к датам"""
        builder = InlineKeyboardBuilder()

        builder.row(types.InlineKeyboardButton(
            text="🔙 Назад к датам",
            callback_data="admin_receipt_back_to_dates"
        ))

        return builder.as_markup()