from app.db.database import SessionLocal
from app.models.models import User, Employee
from app.core.security import get_password_hash
from datetime import datetime

db = SessionLocal()

admin = User(
    email="admin@seda24.de",
    password_hash=get_password_hash("admin123"),
    role="admin",
    is_active=True
)
db.add(admin)
db.commit()
db.refresh(admin)

admin_emp = Employee(
    user_id=admin.id,
    personal_nr="999",
    first_name="Admin",
    last_name="SEDA24",
    hourly_rate=0.00
)
db.add(admin_emp)
db.commit()

print("✅ ADMIN ANGELEGT!")
print("Login: admin@seda24.de / admin123")

db.close()
