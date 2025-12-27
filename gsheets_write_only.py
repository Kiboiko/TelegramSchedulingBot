# gsheets_write_only.py
import logging
from gsheets_manager import GoogleSheetsManager

logger = logging.getLogger(__name__)


class WriteOnlyGoogleSheetsManager(GoogleSheetsManager):
    """Google Sheets менеджер только для записи (без чтения)"""

    def __init__(self, credentials_file: str, spreadsheet_id: str):
        super().__init__(credentials_file, spreadsheet_id)
        self.read_only_mode = False  # Можем читать, но не будем

    def get_bookings_from_sheet(self, sheet_name: str, is_teacher: bool) -> List[Dict[str, Any]]:
        """ПЕРЕОПРЕДЕЛЯЕМ: возвращаем пустой список, чтобы бот не читал из Google Sheets"""
        logger.debug(f"Write-only mode: пропускаем чтение из {sheet_name}")
        return []

    def sync_from_gsheets_to_json(self, storage):
        """ПЕРЕОПРЕДЕЛЯЕМ: отключаем синхронизацию из Google Sheets"""
        logger.debug("Write-only mode: отключена синхронизация из Google Sheets")
        return False

    def get_user_name(self, user_id: int) -> str:
        """ПЕРЕОПРЕДЕЛЯЕМ: всегда возвращаем пустую строку"""
        return ""

    def get_user_roles(self, user_id: int) -> List[str]:
        """ПЕРЕОПРЕДЕЛЯЕМ: всегда возвращаем пустой список"""
        return []

    def get_user_data(self, user_id: int) -> dict:
        """ПЕРЕОПРЕДЕЛЯЕМ: всегда возвращаем пустой словарь"""
        return {}

    # Добавьте переопределения для других методов чтения по мере необходимости