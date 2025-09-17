from dataclasses import dataclass
from datetime import date, time
from typing import List, Optional

@dataclass
class Booking:
    id: int
    user_id: int
    user_name: str
    user_role: str
    booking_type: str
    date: date
    start_time: time
    end_time: time
    subject: Optional[str] = None
    subjects: Optional[List[str]] = None
    created_at: str = ""

@dataclass
class User:
    user_id: int
    user_name: str
    roles: List[str]
    teacher_subjects: Optional[List[str]] = None
    available_subjects: Optional[List[str]] = None