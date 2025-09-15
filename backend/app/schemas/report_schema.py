from pydantic import BaseModel
from typing import Optional, List, Dict
from datetime import date

class ReportParams(BaseModel):
    date: Optional[date] = None
    week: Optional[int] = None
    month: Optional[int] = None
    year: Optional[int] = None
    from_date: Optional[date] = None
    to_date: Optional[date] = None
    employee_id: Optional[int] = None
    object_id: Optional[int] = None

class DailyReport(BaseModel):
    date: str
    total_hours: float
    total_formatted: str
    entries: List[Dict]
    is_working: bool

class WeeklyReport(BaseModel):
    week_number: int
    year: int
    week_start: str
    week_end: str
    daily_hours: Dict
    total_hours: float
    total_formatted: str

class MonthlyReport(BaseModel):
    month: int
    year: int
    month_name: str
    work_days: int
    total_hours: float
    soll_hours: float
    ueberstunden: float
    estimated_salary: float
