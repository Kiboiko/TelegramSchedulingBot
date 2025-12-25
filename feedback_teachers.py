# feedback_teachers.py
import json
import logging
from datetime import datetime, time, timedelta
from typing import List, Dict, Any
from aiogram import Bot, types
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

logger = logging.getLogger(__name__)


class FeedbackTeacherStates(StatesGroup):
    WAITING_FEEDBACK_REASON = State()
    WAITING_FEEDBACK_DETAILS = State()


class FeedbackTeacherManager:
    def __init__(self, storage, gsheets_manager, bot: Bot):
        self.storage = storage
        self.gsheets = gsheets_manager
        self.bot = bot
        self.feedback_file = "feedback_teachers.json"
        self.good_feedback_delay = 7  # Берем из конфига

    def load_feedback_data(self) -> List[Dict[str, Any]]:
        """Загружает данные обратной связи преподавателей из JSON"""
        try:
            with open(self.feedback_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def get_lesson_count_since_last_good_feedback(self, user_id: int) -> int:
        """Получает количество занятий с последнего отзыва 'Хорошо' для преподавателя"""
        feedback_data = self.load_feedback_data()

        # Находим последний отзыв "Хорошо" для этого преподавателя
        last_good_feedbacks = [
            f for f in feedback_data
            if (f.get('user_id') == user_id and
                f.get('rating') == 'good' and
                f.get('status') == 'completed')
        ]

        if not last_good_feedbacks:
            return 0  # Не было отзывов "Хорошо" - отправляем сразу

        # Берем самый последний отзыв "Хорошо"
        last_good_feedback = max(last_good_feedbacks, key=lambda x: x.get('responded_at', ''))

        # Получаем все занятия после этого отзыва
        all_bookings = self.storage.load()
        user_bookings = [
            b for b in all_bookings
            if (b.get('user_id') == user_id and
                b.get('user_role') == 'teacher')
        ]

        # Фильтруем занятия, которые были после последнего отзыва "Хорошо"
        last_feedback_date = datetime.fromisoformat(last_good_feedback['responded_at']).date()
        subsequent_lessons = [
            b for b in user_bookings
            if datetime.strptime(b['date'], "%Y-%m-%d").date() > last_feedback_date
        ]

        return len(subsequent_lessons)

    def should_send_feedback(self, user_id: int, date: str) -> bool:
        """Определяет, нужно ли отправлять отзыв для этого занятия преподавателю"""
        # Проверяем, не отправляли ли уже отзыв для этого занятия
        if self.check_feedback_sent(user_id, date):
            return False

        # Получаем количество занятий с последнего "Хорошо"
        lesson_count = self.get_lesson_count_since_last_good_feedback(user_id)

        # Если было "Хорошо" и прошло меньше занятий, чем delay - не отправляем
        if lesson_count > 0 and lesson_count < self.good_feedback_delay:
            return False

        return True
    def save_feedback_data(self, data: List[Dict[str, Any]]):
        """Сохраняет данные обратной связи преподавателей в JSON"""
        try:
            with open(self.feedback_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Ошибка сохранения feedback_teachers: {e}")

    def get_todays_finished_lessons(self) -> List[Dict[str, Any]]:
        """Получает список завершенных занятий преподавателей на сегодня с учетом счетчика"""
        try:
            today = datetime.now().date()
            today_str = today.strftime("%Y-%m-%d")
            bookings = self.storage.load()
            finished_lessons = []

            for booking in bookings:
                if (booking.get('user_role') == 'teacher' and
                        booking.get('date') == today_str):

                    end_time_str = booking.get('end_time', '')
                    if end_time_str:
                        try:
                            end_time = datetime.strptime(end_time_str, "%H:%M").time()
                            current_time = datetime.now().time()

                            if current_time > end_time:
                                # ИСПРАВЛЕНИЕ: используем новую логику проверки
                                if self.should_send_feedback(
                                    booking.get('user_id'),
                                    today_str
                                ):
                                    finished_lessons.append(booking)

                        except ValueError:
                            continue

            return finished_lessons

        except Exception as e:
            logger.error(f"Ошибка получения завершенных занятий преподавателей: {e}")
            return []

    def check_feedback_sent(self, user_id: int, date: str) -> bool:
        """Проверяет, была ли уже отправлена обратная связь преподавателю"""
        feedback_data = self.load_feedback_data()

        for feedback in feedback_data:
            if (feedback.get('user_id') == user_id and
                    feedback.get('date') == date):
                return True

        return False

    async def send_feedback_questions(self):
        """Отправляет вопросы обратной связи для завершенных занятий преподавателей"""
        try:
            finished_lessons = self.get_todays_finished_lessons()

            for lesson in finished_lessons:
                user_id = lesson.get('user_id')
                date_str = lesson.get('date')
                start_time = lesson.get('start_time', '')
                end_time = lesson.get('end_time', '')
                subjects = lesson.get('subjects', [])

                # Получаем название предметов
                from config import SUBJECTS
                subject_names = []
                for subject_id in subjects:
                    subject_name = SUBJECTS.get(subject_id, f"Предмет {subject_id}")
                    subject_names.append(subject_name)

                subjects_text = ", ".join(subject_names)

                # Форматируем дату
                lesson_date = datetime.strptime(date_str, "%Y-%m-%d")
                weekdays_ru = ["Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье"]
                weekday = weekdays_ru[lesson_date.weekday()]
                formatted_date = lesson_date.strftime("%d.%m.%Y")

                # Создаем клавиатуру с вариантами ответов
                keyboard = types.InlineKeyboardMarkup(inline_keyboard=[
                    [
                        types.InlineKeyboardButton(
                            text="Хорошо 👍",
                            callback_data=f"feedback_teacher_good_{date_str}"
                        )
                    ],
                    [
                        types.InlineKeyboardButton(
                            text="Могло быть лучше 🤔",
                            callback_data=f"feedback_teacher_better_{date_str}"
                        )
                    ],
                    [
                        types.InlineKeyboardButton(
                            text="Ужасно 👎",
                            callback_data=f"feedback_teacher_bad_{date_str}"
                        )
                    ]
                ])

                message_text = (
                    f"Привет! Как прошла ваша смена?\n"
                    f"📅 {formatted_date} ({weekday})\n"
                    f"⏰ {start_time}-{end_time}\n"
                    f"📚 {subjects_text}"
                )

                try:
                    await self.bot.send_message(
                        chat_id=user_id,
                        text=message_text,
                        reply_markup=keyboard
                    )
                    logger.info(f"Отправлен запрос обратной связи преподавателю {user_id}")

                    # Помечаем как отправленный
                    self.mark_feedback_sent(user_id, date_str)

                except Exception as e:
                    logger.error(f"Не удалось отправить сообщение преподавателю {user_id}: {e}")

        except Exception as e:
            logger.error(f"Ошибка отправки обратной связи преподавателям: {e}")

    def mark_feedback_sent(self, user_id: int, date: str):
        """Помечает, что запрос обратной связи был отправлен преподавателю"""
        feedback_data = self.load_feedback_data()

        feedback_record = {
            'user_id': user_id,
            'date': date,
            'sent_at': datetime.now().isoformat(),
            'status': 'request_sent'
        }

        feedback_data.append(feedback_record)
        self.save_feedback_data(feedback_data)

    def save_feedback_response(self, user_id: int, date: str,
                               rating: str, details: str = ""):
        """Сохраняет ответ обратной связи преподавателя"""
        feedback_data = self.load_feedback_data()

        # Удаляем старую запись о отправке
        feedback_data = [f for f in feedback_data if not (
                f.get('user_id') == user_id and
                f.get('date') == date and
                f.get('status') == 'request_sent'
        )]

        feedback_record = {
            'user_id': user_id,
            'date': date,
            'rating': rating,
            'details': details,
            'responded_at': datetime.now().isoformat(),
            'status': 'completed'
        }

        feedback_data.append(feedback_record)
        self.save_feedback_data(feedback_data)

        # Локальная запись — не синхронизируем отзывы преподавателей с Google Sheets
        # (teacher feedback is local-only)

    def get_user_feedbacks(self, user_id: int) -> List[Dict[str, Any]]:
        """Возвращает все завершенные отзывы для преподавателя (локально)."""
        try:
            data = self.load_feedback_data()
            user_feedbacks = [f for f in data if str(f.get('user_id')) == str(user_id) and f.get('status') == 'completed']
            # Сортируем по времени ответа (последние первыми)
            user_feedbacks.sort(key=lambda x: x.get('responded_at', ''), reverse=True)
            return user_feedbacks
        except Exception as e:
            logger.error(f"Ошибка получения отзывов преподавателя {user_id}: {e}")
            return []


    def sync_feedback_to_gsheets(self, feedback_record: Dict[str, Any]):
        """Синхронизирует обратную связь преподавателя с Google Sheets"""
        try:
            if not self.gsheets:
                logger.warning("Google Sheets manager не доступен")
                return

            required_fields = ['user_id', 'date', 'rating']
            for field in required_fields:
                if field not in feedback_record:
                    logger.error(f"Отсутствует обязательное поле {field} в feedback_record")
                    return

            # Форматируем дату занятия для поиска столбцов
            date_obj = datetime.strptime(feedback_record['date'], "%Y-%m-%d")
            formatted_date = date_obj.strftime("%d.%m.%Y")

            # Получаем данные листа "обратная связь преподаватели"
            worksheet = self.gsheets._get_or_create_worksheet("обратная связь преподаватели")
            data = worksheet.get_all_values()

            if not data:
                logger.warning("Лист 'обратная связь преподаватели' пуст")
                return

            # Находим заголовки
            headers = [h.strip().lower() for h in data[0]]

            # Ищем колонки для даты занятия
            date_col_start = -1
            date_col_end = -1

            for i, header in enumerate(headers):
                if header.startswith(formatted_date.lower()):
                    if date_col_start == -1:
                        date_col_start = i
                    else:
                        date_col_end = i
                        break

            if date_col_start == -1:
                logger.error(f"Дата {formatted_date} не найдена в заголовках обратной связи преподавателей")
                return

            # Если не нашли вторую колонку, предполагаем что следующая - для текста
            if date_col_end == -1:
                date_col_end = date_col_start + 1

            # Получаем имя преподавателя
            user_name = self.storage.get_user_name(feedback_record['user_id'])
            if not user_name:
                user_name = f"Teacher_{feedback_record['user_id']}"

            # Преобразуем рейтинг в текст
            rating_text = {
                'good': 'Хорошо',
                'better': 'Могло быть лучше',
                'bad': 'Ужасно'
            }.get(feedback_record['rating'], feedback_record['rating'])

            details_text = feedback_record.get('details', '')

            # Ищем строку с user_id
            target_row = -1

            for row_idx, row in enumerate(data[1:], start=2):  # Пропускаем заголовок
                if len(row) > 0 and str(row[0]).strip() == str(feedback_record['user_id']):
                    target_row = row_idx
                    break

            # Если не нашли, создаем новую строку
            if target_row == -1:
                # Добавляем новую строку
                new_row = [
                    feedback_record['user_id'],
                    user_name,
                    # Предметы преподавателя (можно добавить при необходимости)
                    ''
                ]

                # Добавляем пустые ячейки до нужного количества колонок
                current_cols = len(new_row)
                total_cols = len(headers)
                if current_cols < total_cols:
                    new_row.extend([''] * (total_cols - current_cols))

                worksheet.append_row(new_row)

                # Получаем номер новой строки
                data = worksheet.get_all_values()
                target_row = len(data)

                logger.info(f"Создана новая строка для преподавателя user_id {feedback_record['user_id']}")

            # Обновляем ячейки с обратной связью
            try:
                # Первая колонка даты - рейтинг
                worksheet.update_cell(target_row, date_col_start + 1, rating_text)

                # Вторая колонка даты - детали
                worksheet.update_cell(target_row, date_col_end + 1, details_text)

                logger.info(
                    f"Успешно записана обратная связь для преподавателя {feedback_record['user_id']} на дату {formatted_date}")

            except Exception as e:
                logger.error(f"Ошибка обновления ячеек обратной связи преподавателя: {e}")
                return

        except Exception as e:
            logger.error(f"Ошибка синхронизации feedback преподавателя с GSheets: {e}")

    def get_pending_feedback_for_gsheets(self) -> List[Dict[str, Any]]:
        """Получает обратную связь преподавателей, которую нужно синхронизировать с Google Sheets"""
        feedback_data = self.load_feedback_data()

        # Фильтруем завершенные отзывы, которые еще не синхронизированы
        pending_feedback = []
        for feedback in feedback_data:
            if (feedback.get('status') == 'completed' and
                    not feedback.get('synced_to_gsheets', False)):
                pending_feedback.append(feedback)

        return pending_feedback

    def mark_feedback_synced(self, user_id: int, date: str):
        """Помечает обратную связь преподавателя как синхронизированную с Google Sheets"""
        feedback_data = self.load_feedback_data()

        for feedback in feedback_data:
            if (feedback.get('user_id') == user_id and
                    feedback.get('date') == date and
                    feedback.get('status') == 'completed'):
                feedback['synced_to_gsheets'] = True
                feedback['synced_at'] = datetime.now().isoformat()
                break

        self.save_feedback_data(feedback_data)