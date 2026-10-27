from sqlalchemy import Column, Integer, BigInteger, String, DateTime, Float, Boolean, ForeignKey, Enum, Text, Date, Time, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from app.db.database import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    OBJEKTLEITER = "objektleiter"
    MITARBEITER = "mitarbeiter"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    password_hash = Column(String)
    role = Column(Enum(UserRole), default=UserRole.MITARBEITER)
    category = Column(String, default='C')
    is_active = Column(Boolean, default=True)
    must_change_password = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

    employee = relationship("Employee", back_populates="user", uselist=False)


class Employee(Base):
    __tablename__ = "employees"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    personal_nr = Column(String, unique=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    kuerzel = Column(String)
    hourly_rate_standard = Column(Float, default=15.00)
    hourly_rate_window = Column(Float, default=20.00)
    hourly_rate_basic = Column(Float, default=20.00)
    monthly_amount = Column(Float, default=556.00)
    total_hours_since_start = Column(Float, default=0.0)
    start_hours = Column(Float, default=0.0)
    hourly_rate = Column(Float, default=15.50)
    address = Column(Text)
    gps_required = Column(Boolean, default=True)
    tracking_mode = Column(String(1), default='C')
    auto_stamp = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    # V3.0 Felder
    push_channel = Column(String(20), default='browser')
    telegram_chat_id = Column(BigInteger, nullable=True)
    zeitkonto_aktiv = Column(Boolean, default=False)
    gender = Column(String(1), default='M')
    # Vertragliche Arbeitstage: kommaseparierte Wochentage, Python-Konvention (0=Mo..6=So)
    # Beispiel: "0,1,2,3,4" = Mo-Fr, "0,2,4" = Mo/Mi/Fr, NULL = nicht konfiguriert
    work_days_profile = Column(String(20), nullable=True)
    # Durchschnittliche Arbeitstage pro Woche (fuer Abrufkraefte ohne feste Wochentage)
    # Wenn gesetzt, wird dieser Wert fuer die Urlaubstage-Zaehlung verwendet statt Wochentagsprofil
    avg_work_days_per_week = Column(Float, nullable=True)
    enforce_min_duration = Column(Boolean, default=False)

    user = relationship("User", back_populates="employee")
    time_entries = relationship("TimeEntry", back_populates="employee")
    schedules = relationship("Schedule", foreign_keys="[Schedule.employee_id]", back_populates="employee")
    warnings = relationship("Warning", back_populates="employee")
    corrections = relationship("CorrectionRequest", back_populates="employee")

    @property
    def hourly_rate_calc(self):
        return self.hourly_rate_standard if hasattr(self, 'hourly_rate_standard') else 15.00


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    billing_type = Column(String, default="monthly")
    monthly_rate = Column(Float)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

    objects = relationship("Object", back_populates="customer")


class Object(Base):
    __tablename__ = "objects"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"))
    name = Column(String, index=True)
    address = Column(String)
    gps_lat = Column(Float)
    gps_lng = Column(Float)
    radius_m = Column(Integer, default=100)
    cleaning_type = Column(String)
    is_active = Column(Boolean, default=True)
    start_time = Column(Time)
    end_time = Column(Time)
    monthly_amount_netto = Column(Float, nullable=True)
    ip_prefix = Column(String(32), nullable=True)  # Netz-Erkennung: Praefix der Objekt-Standleitung
    created_at = Column(DateTime, default=datetime.now)

    customer = relationship("Customer", back_populates="objects")
    time_entries = relationship("TimeEntry", back_populates="object")
    schedules = relationship("Schedule", back_populates="object")


class TimeEntry(Base):
    __tablename__ = "time_entries"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    custom_object_name = Column(String, nullable=True)
    object_id = Column(Integer, ForeignKey("objects.id"))
    check_in = Column(DateTime)
    check_out = Column(DateTime, nullable=True)
    service_type = Column(String, default='Unterhaltsreinigung')
    hourly_rate = Column(Float, default=15.50)
    billed_hours = Column(Float, nullable=True)
    gps_lat = Column(Float, nullable=True)
    gps_lng = Column(Float, nullable=True)
    photo_url = Column(String, nullable=True)
    is_manual_entry = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    schedule_id = Column(Integer, ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True)
    client_id = Column(String(36), nullable=True)
    overdue_notified = Column(Boolean, default=False)
    server_received_at = Column(DateTime, nullable=True)
    client_ip = Column(String(45), nullable=True)  # erkannte Client-IP beim Stempeln (Journal)
    created_at = Column(DateTime, default=datetime.now)

    employee = relationship("Employee", back_populates="time_entries")
    object = relationship("Object", back_populates="time_entries")
    corrections = relationship("CorrectionRequest", back_populates="time_entry")


class Schedule(Base):
    __tablename__ = "schedules"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    object_id = Column(Integer, ForeignKey("objects.id"))
    weekday = Column(Integer)
    date = Column(Date, index=True)
    start_time = Column(Time)
    end_time = Column(Time)
    planned_hours = Column(Float)
    status = Column(String(20), default="normal")
    replacement_for = Column(Integer, nullable=True)
    notes = Column(Text, nullable=True)
    # V3.0 Felder
    is_driver = Column(Boolean, default=False)
    is_last_shift_of_month = Column(Boolean, default=False)
    partner_schedule_id = Column(Integer, ForeignKey("schedules.id", ondelete="SET NULL"), nullable=True)
    original_planned_hours = Column(Float, nullable=True)
    original_end_time = Column(Time, nullable=True)
    no_stamp_notified = Column(Boolean, default=False)
    no_stamp_ma_notified = Column(Boolean, default=False)

    employee = relationship("Employee")
    object = relationship("Object")


class BreakEntry(Base):
    __tablename__ = "break_entries"

    id = Column(Integer, primary_key=True, index=True)
    time_entry_id = Column(Integer, ForeignKey("time_entries.id"))
    start_time = Column(DateTime)
    end_time = Column(DateTime, nullable=True)
    is_paid = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

    time_entry = relationship("TimeEntry")


class Warning(Base):
    __tablename__ = "warnings"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    warning_type = Column(String)
    description = Column(Text)
    is_resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    employee = relationship("Employee", back_populates="warnings")
    resolver = relationship("User", foreign_keys=[resolved_by])


class CorrectionRequest(Base):
    __tablename__ = "correction_requests"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    time_entry_id = Column(Integer, ForeignKey("time_entries.id"))
    correction_type = Column(String)
    old_value = Column(String)
    new_value = Column(String)
    reason = Column(Text)
    status = Column(String, default="pending")
    admin_response = Column(Text, nullable=True)
    processed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    employee = relationship("Employee", back_populates="corrections")
    time_entry = relationship("TimeEntry", back_populates="corrections")
    processor = relationship("User", foreign_keys=[processed_by])


class EmployeeObjectHours(Base):
    __tablename__ = "employee_object_hours"

    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    object_id = Column(Integer, ForeignKey("objects.id"))
    custom_hours = Column(Float)
    created_at = Column(DateTime, default=datetime.now)


class CustomerHours(Base):
    __tablename__ = "customer_hours"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), unique=True)
    default_hours = Column(Float, nullable=False)
    cleaning_type = Column(String, default='unterhalt')
    created_at = Column(DateTime, default=datetime.now)

    customer = relationship("Customer")


class SpecialRule(Base):
    __tablename__ = "special_rules"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    customer_id = Column(Integer, ForeignKey("customers.id"))
    special_hours = Column(Float)
    special_rate = Column(Float, nullable=True)
    note = Column(String)
    active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

    employee = relationship("Employee")
    customer = relationship("Customer")


class KmDistance(Base):
    __tablename__ = "km_distances"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    object_id = Column(Integer, ForeignKey("objects.id"))
    distance_km = Column(Float)
    rate_per_km = Column(Float, default=0.30)
    created_at = Column(DateTime, default=datetime.now)


# ========== V3.0 ORM-Modelle fuer bestehende Raw-SQL-Tabellen ==========

class KmDailyEntry(Base):
    __tablename__ = "km_daily_entries"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    object_id = Column(Integer, ForeignKey("objects.id"), nullable=True)
    time_entry_id = Column(Integer, ForeignKey("time_entries.id"), nullable=True)
    date = Column(Date, nullable=False, index=True)
    distance_km = Column(Float, default=0.0)
    amount = Column(Float, default=0.0)
    is_billable = Column(Boolean, default=False)
    is_longest_trip = Column(Boolean, default=False)
    custom_object_name = Column(String(255), nullable=True)

    employee = relationship("Employee")
    object = relationship("Object")


class VacationEntitlement(Base):
    __tablename__ = "vacation_entitlements"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    year = Column(Integer, nullable=False)
    days_entitled = Column(Float, default=0)
    days_taken = Column(Float, default=0)
    days_remaining = Column(Float, default=0)
    vacation_rate = Column(Float, default=15.50)

    employee = relationship("Employee")


class ObjectStandardTime(Base):
    __tablename__ = "object_standard_times_v2"
    __table_args__ = {'extend_existing': True}

    id = Column(Integer, primary_key=True, index=True)
    object_id = Column(Integer, ForeignKey("objects.id"), nullable=False)
    start_time = Column(Time, nullable=True)
    end_time = Column(Time, nullable=True)
    standard_hours = Column(Float, nullable=True)
    weekday = Column(Integer, nullable=True)  # 0=Mo, 1=Di, ..., 6=So

    object = relationship("Object")


# ========== V3.0 NEUE MODELLE ==========

class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    endpoint = Column(Text, nullable=False)
    p256dh_key = Column(Text, nullable=False)
    auth_key = Column(Text, nullable=False)
    user_agent = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)
    last_used_at = Column(DateTime, nullable=True)

    employee = relationship("Employee")


class PushNotification(Base):
    __tablename__ = "push_notifications"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    notification_type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    body = Column(Text, nullable=True)
    payload = Column(Text, nullable=True)
    channel = Column(String(20), default='browser')
    status = Column(String(20), default='pending')
    response_status = Column(String(20), nullable=True)
    response_data = Column(Text, nullable=True)
    schedule_id = Column(Integer, ForeignKey("schedules.id"), nullable=True)
    expires_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    responded_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    employee = relationship("Employee")
    schedule = relationship("Schedule")


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(Integer, nullable=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    details = Column(Text, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.now, index=True)

    user = relationship("User", foreign_keys=[user_id])


class MonthlyConfirmation(Base):
    __tablename__ = "monthly_confirmations"
    __table_args__ = (
        UniqueConstraint('employee_id', 'year', 'month', name='uq_monthly_confirmation'),
    )

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    status = Column(String(20), default='pending')
    total_hours = Column(Float, nullable=True)
    total_km = Column(Float, nullable=True)
    confirmed_at = Column(DateTime, nullable=True)
    sent_at = Column(DateTime, nullable=True)
    dispute_reason = Column(Text, nullable=True)
    push_notification_id = Column(Integer, ForeignKey("push_notifications.id"), nullable=True)
    last_shift_override = Column(Date, nullable=True)
    confirmed_by = Column(String(20), nullable=True)  # 'admin' oder 'employee'
    created_at = Column(DateTime, default=datetime.now)

    employee = relationship("Employee")


class EmployeeObjectAssignment(Base):
    __tablename__ = "employee_object_assignments"
    __table_args__ = (
        UniqueConstraint('employee_id', 'object_id', name='uq_emp_obj_assignment'),
    )

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    object_id = Column(Integer, ForeignKey("objects.id"), nullable=False)
    role = Column(String(30), default='mitarbeiter')
    is_driver = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    valid_from = Column(Date, nullable=True)
    valid_until = Column(Date, nullable=True)
    tracking_category = Column(String(1), default='B')
    custom_hourly_rate = Column(Float, nullable=True)
    custom_service_type = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    employee = relationship("Employee")
    object = relationship("Object")


class ShiftChangeRequest(Base):
    __tablename__ = "shift_change_requests"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    schedule_id = Column(Integer, ForeignKey("schedules.id"), nullable=True)
    request_type = Column(String(30), nullable=False)
    requested_date = Column(Date, nullable=True)
    requested_start = Column(Time, nullable=True)
    requested_end = Column(Time, nullable=True)
    swap_employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    reason = Column(Text, nullable=True)
    status = Column(String(20), default='pending')
    admin_response = Column(Text, nullable=True)
    processed_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    processed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    employee = relationship("Employee", foreign_keys=[employee_id])
    swap_employee = relationship("Employee", foreign_keys=[swap_employee_id])


class TelegramConfig(Base):
    __tablename__ = "telegram_config"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), unique=True, nullable=False)
    chat_id = Column(String(50), nullable=False)
    is_verified = Column(Boolean, default=False)
    verification_code = Column(String(10), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    employee = relationship("Employee")


class ServiceType(Base):
    __tablename__ = "service_types"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    hourly_rate = Column(Float, nullable=False)
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)


class VacationRequest(Base):
    __tablename__ = "vacation_requests"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    working_days = Column(Float, default=0)
    status = Column(String(20), default='pending')  # pending/approved/rejected
    type = Column(String(20), default='urlaub')  # urlaub/abwesenheit
    requested_at = Column(DateTime, default=datetime.now)
    decided_at = Column(DateTime, nullable=True)
    decided_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    employee = relationship("Employee")
    decider = relationship("User", foreign_keys=[decided_by])


class SickNote(Base):
    __tablename__ = "sick_notes"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    working_days = Column(Float, default=0)
    au_photo_path = Column(String(500), nullable=True)
    status = Column(String(20), default='pending')  # pending/confirmed/rejected
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    confirmed_at = Column(DateTime, nullable=True)
    confirmed_by = Column(Integer, ForeignKey("users.id"), nullable=True)

    employee = relationship("Employee")
    confirmer = relationship("User", foreign_keys=[confirmed_by])


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_employee_id = Column(Integer, ForeignKey("employees.id"), nullable=True)
    sender_admin_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    category = Column(String(50), nullable=False)  # material, reklamation, problem, sonstiges, firmen_mitteilung
    subject = Column(String(255), nullable=True)
    body = Column(Text, nullable=False)
    photo_path = Column(String(500), nullable=True)
    status = Column(String(20), default='neu')  # neu, gelesen, beantwortet
    parent_id = Column(Integer, ForeignKey("messages.id"), nullable=True)
    recipient_employee_ids = Column(Text, nullable=True)  # JSON-Array fuer Firmen-Mitteilungen
    created_at = Column(DateTime, default=datetime.now)

    sender_employee = relationship("Employee", foreign_keys=[sender_employee_id])
    sender_admin = relationship("User", foreign_keys=[sender_admin_id])
    parent = relationship("Message", remote_side=[id])


class MasterScheduleEntry(Base):
    __tablename__ = "master_schedule_entries"
    __table_args__ = (
        UniqueConstraint('employee_id', 'object_id', 'weekday', 'rhythm', name='uq_master_schedule'),
    )

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    object_id = Column(Integer, ForeignKey("objects.id"), nullable=False)
    weekday = Column(Integer, nullable=False)  # 0=Montag..6=Sonntag (Python-Mapping)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    planned_hours = Column(Float, nullable=True)
    is_driver = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    # Rhythmus: weekly, biweekly_even (gerade KW), biweekly_odd (ungerade KW), monthly
    rhythm = Column(String(20), default='weekly')
    # Fuer monthly: welche Woche im Monat (1-4, -1=letzte)
    month_week = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    employee = relationship("Employee")
    object = relationship("Object")


class CustomerRevenue(Base):
    __tablename__ = "customer_revenues"
    __table_args__ = (
        UniqueConstraint('object_id', 'year', 'month', name='uq_customer_revenue'),
    )

    id = Column(Integer, primary_key=True, index=True)
    object_id = Column(Integer, ForeignKey("objects.id"), nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    revenue = Column(Float, default=0.0)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    object = relationship("Object")
    customer = relationship("Customer")


class FinanceSetting(Base):
    __tablename__ = "finance_settings"
    id = Column(Integer, primary_key=True, index=True)
    setting_key = Column(String(100), unique=True, nullable=False)
    setting_value = Column(String(255))
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class FixedCost(Base):
    __tablename__ = "fixed_costs"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    amount = Column(Float, default=0)
    cost_type = Column(String(10), default='monthly')  # 'monthly' oder 'yearly'
    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)


class MonthlyFixedCost(Base):
    __tablename__ = "monthly_fixed_costs"
    __table_args__ = (
        UniqueConstraint('year', 'month', 'name', name='uq_monthly_fixed_cost'),
    )
    id = Column(Integer, primary_key=True, index=True)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    name = Column(String(255), nullable=False)
    amount = Column(Float, default=0)
    sort_order = Column(Integer, default=0)


class UserObjectAssignment(Base):
    __tablename__ = "user_object_assignments"
    __table_args__ = (
        UniqueConstraint('user_id', 'object_id', name='uq_user_obj_assignment'),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    object_id = Column(Integer, ForeignKey("objects.id"), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User")
    object = relationship("Object")


class MonthlyCarryover(Base):
    __tablename__ = "monthly_carryovers"

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)
    carryover_amount = Column(Float, default=0.0)
    notes = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class Zeitkonto(Base):
    __tablename__ = "zeitkonto"
    __table_args__ = (
        UniqueConstraint('employee_id', 'year', 'month', name='uq_zeitkonto_emp_month'),
    )

    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"), nullable=False)
    year = Column(Integer, nullable=False)
    month = Column(Integer, nullable=False)

    # Ist-Stunden (auto-berechnet aus TimeEntries)
    ist_stunden_normal = Column(Float, default=0.0)
    ist_stunden_sonntag = Column(Float, default=0.0)
    ist_stunden_nacht = Column(Float, default=0.0)
    ist_stunden_feiertag = Column(Float, default=0.0)

    # Soll-Stunden (editierbar, Standard 140h)
    soll_stunden = Column(Float, default=140.0)

    # Berechnete Werte
    uebertrag_stunden = Column(Float, default=0.0)     # ist_normal - soll
    vortrag_stunden = Column(Float, default=0.0)        # Saldo vom Vormonat
    konto_saldo = Column(Float, default=0.0)            # vortrag + uebertrag

    # Vorschuss
    vorschuss_betrag = Column(Float, default=0.0)       # EUR

    # Status
    status = Column(String(20), default='entwurf')      # entwurf / abgeschlossen

    # Audit
    abgeschlossen_am = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    employee = relationship("Employee")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token = Column(String(64), unique=True, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
