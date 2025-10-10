# materials_manager.py
import logging
from datetime import datetime
from typing import Dict, List, Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from oauth2client.service_account import ServiceAccountCredentials
import os

logger = logging.getLogger(__name__)


class MaterialsManager:
    def __init__(self, gsheets_manager, credentials_file: str, spreadsheet_id: str):
        self.gsheets = gsheets_manager
        self.credentials_file = credentials_file
        self.spreadsheet_id = spreadsheet_id
        self.drive_service = None
        self.docs_service = None
        self._init_services()

    def _init_services(self):
        """Инициализация Google Drive и Docs API"""
        try:
            scope = [
                'https://www.googleapis.com/auth/drive',
                'https://www.googleapis.com/auth/documents',
                'https://www.googleapis.com/auth/drive.file'
            ]
            creds = ServiceAccountCredentials.from_json_keyfile_name(
                self.credentials_file, scope)

            self.drive_service = build('drive', 'v3', credentials=creds)
            self.docs_service = build('docs', 'v1', credentials=creds)
            logger.info("Google Drive и Docs API инициализированы")
        except Exception as e:
            logger.error(f"Ошибка инициализации Google API: {e}")

    def get_student_lesson_info(self, user_id: int, subject_id: str, target_date: str) -> Dict[str, any]:
        """Получает информацию о занятии ученика"""
        try:
            from shedule_app.GoogleParser import GoogleSheetsDataLoader

            loader = GoogleSheetsDataLoader(self.credentials_file, self.spreadsheet_id, target_date)
            topic = loader.get_student_topic_by_user_id(str(user_id), target_date, str(subject_id))

            return {
                'lesson_number': 1,  # Упрощенно
                'topic': topic or "Тема не определена",
                'subject_name': self._get_subject_name(subject_id)
            }
        except Exception as e:
            logger.error(f"Ошибка получения информации о занятии: {e}")
            return {
                'lesson_number': 1,
                'topic': "Тема не определена",
                'subject_name': self._get_subject_name(subject_id)
            }

    def get_qualification_materials(self, subject_id: str) -> Optional[str]:
        """Получает материалы по предмету"""
        try:
            if hasattr(self.gsheets, 'qual_links') and subject_id in self.gsheets.qual_links:
                doc_url = self.gsheets.qual_links[subject_id]
                return f"Ссылка на материалы: {doc_url}"
            return "Материалы не найдены"
        except Exception as e:
            logger.error(f"Ошибка получения материалов: {e}")
            return None

    def create_combined_materials_document(self, target_date: str) -> str:
        """Создает реальный Google документ с материалами"""
        try:
            # Создаем новый Google документ
            doc_title = f"Материалы для занятий на {target_date}"

            document = self.docs_service.documents().create(body={
                'title': doc_title
            }).execute()

            doc_id = document['documentId']
            logger.info(f"Создан документ с ID: {doc_id}")

            # Подготавливаем содержимое
            requests = self._prepare_document_requests(target_date)

            if requests:
                # Добавляем содержимое в документ
                self.docs_service.documents().batchUpdate(
                    documentId=doc_id,
                    body={'requests': requests}
                ).execute()

            # Делаем документ доступным для чтения
            self.drive_service.permissions().create(
                fileId=doc_id,
                body={'type': 'anyone', 'role': 'reader'},
                fields='id'
            ).execute()

            # Возвращаем реальную ссылку
            doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"
            logger.info(f"Документ создан: {doc_url}")

            return doc_url

        except HttpError as e:
            logger.error(f"Google API error: {e}")
            return f"Ошибка Google API: {e}"
        except Exception as e:
            logger.error(f"Ошибка создания документа: {e}")
            return f"Ошибка: {str(e)}"

    def _prepare_document_requests(self, target_date: str) -> List[Dict]:
        """Подготавливает запросы для наполнения документа"""
        requests = []

        # Добавляем заголовок
        requests.append({
            'insertText': {
                'location': {'index': 1},
                'text': f"📚 Материалы для занятий\nДата: {target_date}\n\n"
            }
        })

        # Добавляем тестовое содержимое
        current_index = len(f"📚 Материалы для занятий\nДата: {target_date}\n\n") + 1

        test_content = (
            "Это тестовый документ с материалами.\n\n"
            "🎓 Ученик: Иван Иванов\n"
            "📖 Предмет: Математика\n"
            "🔢 Занятие №1\n"
            "📌 Тема: Алгебраические уравнения\n"
            "📝 Материалы: Ссылка на материалы: https://example.com\n"
            "==================================================\n\n"
            "🎓 Ученик: Мария Петрова\n"
            "📖 Предмет: Физика\n"
            "🔢 Занятие №2\n"
            "📌 Тема: Законы Ньютона\n"
            "📝 Материалы: Ссылка на материалы: https://example.com\n"
            "==================================================\n\n"
            "Документ сгенерирован автоматически.\n"
            f"Дата генерации: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        )

        requests.append({
            'insertText': {
                'location': {'index': current_index},
                'text': test_content
            }
        })

        return requests

    def _get_subject_name(self, subject_id: str) -> str:
        """Получает название предмета по ID"""
        from config import SUBJECTS
        return SUBJECTS.get(subject_id, f"Предмет {subject_id}")