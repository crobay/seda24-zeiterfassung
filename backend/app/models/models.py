from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, ForeignKey, Enum, Text, Date, Time
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
    category = Column(String, default='C')  # NEU: A, B oder C
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    employee = relationship("Employee", back_populates="user", uselist=False)
    
    employee = relationship("Employee", back_populates="user", uselist=False)

class Employee(Base):
    __tablename__ = "employees"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True)
    personal_nr = Column(String, unique=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    kuerzel = Column(String)
    hourly_rate_standard = Column(Float, default=15.00)  # Unterhaltsreinigung
    hourly_rate_window = Column(Float, default=20.00)    # Fensterreinigung  
    hourly_rate_basic = Column(Float, default=20.00)     # Grundreinigung    monthly_amount = Column(Float, default=556.00)
# Compatibility für alte API
    hourly_rate = Column(Float, default=15.00)  # Fallback für API
    address = Column(Text)
    gps_required = Column(Boolean, default=True)
    auto_stamp = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    tracking_mode = Column(String, default="C")  # A=Auto, B=Button, C=Normal
    created_at = Column(DateTime, default=datetime.utcnow)
    
    user = relationship("User", back_populates="employee")
    time_entries = relationship("TimeEntry", back_populates="employee")
    schedules = relationship("Schedule", foreign_keys="[Schedule.employee_id]", back_populates="employee")

    warnings = relationship("Warning", back_populates="employee")
    corrections = relationship("CorrectionRequest", back_populates="employee")
# Kompatibilität für Login
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
    created_at = Column(DateTime, default=datetime.utcnow)
    
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
    created_at = Column(DateTime, default=datetime.utcnow)
    
    customer = relationship("Customer", back_populates="objects")
    time_entries = relationship("TimeEntry", back_populates="object")
    schedules = relationship("Schedule", back_populates="object")

class TimeEntry(Base):
    __tablename__ = "time_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    object_id = Column(Integer, ForeignKey("objects.id"))
    check_in = Column(DateTime)
    check_out = Column(DateTime, nullable=True)
    service_type = Column(String, default='Unterhaltsreinigung')
    hourly_rate = Column(Float, default=15.00)
    gps_lat = Column(Float, nullable=True)
    gps_lng = Column(Float, nullable=True)
    photo_url = Column(String, nullable=True)
    is_manual_entry = Column(Boolean, default=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    employee = relationship("Employee", back_populates="time_entries")
    object = relationship("Object", back_populates="time_entries")
    corrections = relationship("CorrectionRequest", back_populates="time_entry")

class Schedule(Base):
    __tablename__ = "schedules"
    
    id = Column(Integer, primary_key=True, index=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    object_id = Column(Integer, ForeignKey("objects.id"))
    weekday = Column(Integer)
    start_time = Column(Time)
    end_time = Column(Time)
    planned_hours = Column(Float)
    
    employee = relationship("Employee")
    object = relationship("Object")

class BreakEntry(Base):
    __tablename__ = "break_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    time_entry_id = Column(Integer, ForeignKey("time_entries.id"))
    start_time = Column(DateTime)
    end_time = Column(DateTime, nullable=True)
    is_paid = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
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
    created_at = Column(DateTime, default=datetime.utcnow)
    
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
    created_at = Column(DateTime, default=datetime.utcnow)
    
    employee = relationship("Employee", back_populates="corrections")
    time_entry = relationship("TimeEntry", back_populates="corrections")
    processor = relationship("User", foreign_keys=[processed_by])

class EmployeeObjectHours(Base):
    __tablename__ = "employee_object_hours"
    
    id = Column(Integer, primary_key=True)
    employee_id = Column(Integer, ForeignKey("employees.id"))
    object_id = Column(Integer, ForeignKey("objects.id"))
    custom_hours = Column(Float)  # Individuelle Stunden für MA an diesem Objekt
    created_at = Column(DateTime, default=datetime.utcnow)
    tracking_mode = Column(String(1), default='C')

# Am Ende der models.py hinzufügen:

class CustomerHours(Base):
    __tablename__ = "customer_hours"
    
    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), unique=True)
    default_hours = Column(Float, nullable=False)
    cleaning_type = Column(String, default='unterhalt')
    created_at = Column(DateTime, default=datetime.utcnow)
    
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
    created_at = Column(DateTime, default=datetime.utcnow)
    
    employee = relationship("Employee")
    customer = relationship("Customer")

# Und in der Customer Klasse ergänzen:
# hours = relationship("CustomerHours", back_populates="customer", uselist=False)