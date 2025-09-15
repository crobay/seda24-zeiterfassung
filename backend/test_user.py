from app.db.database import SessionLocal
from app.models.models import User, Employee
from jose import jwt
import os
from dotenv import load_dotenv

load_dotenv()
db = SessionLocal()

# Matej's Token aus Browser-Console kopieren und hier einsetzen
token = input("Token aus Browser eingeben (ohne Bearer): ")

try:
    payload = jwt.decode(token, os.getenv("SECRET_KEY"), algorithms=["HS256"])
    email = payload.get("sub")
    print(f"Token Email: {email}")
    
    user = db.query(User).filter(User.email == email).first()
    if user:
        print(f"User ID: {user.id}, Email: {user.email}")
        
        employee = db.query(Employee).filter(Employee.user_id == user.id).first()
        if employee:
            print(f"Employee: {employee.first_name} {employee.last_name}, Pers.Nr: {employee.personal_nr}")
        else:
            print("KEIN EMPLOYEE GEFUNDEN!")
    else:
        print("USER NICHT GEFUNDEN!")
except Exception as e:
    print(f"ERROR: {e}")
