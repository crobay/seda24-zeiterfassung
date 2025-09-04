from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import JWTError, jwt
import os
from dotenv import load_dotenv

# Wichtige Imports, die gefehlt haben
from app.db.database import get_db
from app.models.models import User, Employee
from app.schemas import user_schema as schemas
from app.core.security import verify_password, get_password_hash, create_access_token, get_current_user
from app.models.models import Schedule

# Lade Umgebungsvariablen
load_dotenv()
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")

# Definiere Router und Security Scheme
router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

@router.post("/register", response_model=schemas.UserResponse)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    hashed_password = get_password_hash(user.password)
    db_user = User(email=user.email, password_hash=hashed_password, role=user.role)
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@router.post("/login", response_model=schemas.Token)
def login(user_credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_credentials.email).first()

    if not user or not verify_password(user_credentials.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    employee = db.query(Employee).filter(Employee.user_id == user.id).first()
    access_token = create_access_token(data={"sub": user.email})
    
    user_name = f"{employee.first_name} {employee.last_name}" if employee else user.email.split('@')[0]
    personal_nr = employee.personal_nr if employee else "N/A"

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_name": user_name,
        "personal_nr": personal_nr,
        "role": user.role
    }

# get_current_user Funktion bleibt wie sie war
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token ungültig",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_exception
    
    return user

@router.get("/time-entries/my-objects-this-week")
async def get_my_scheduled_objects_this_week(
    db: Session = Depends(get_db),
# current_employee: Employee = Depends(get_current_active_employee)
):
    """
    Gibt alle geplanten Objekte für den aktuellen Mitarbeiter für den aktuellen Wochentag zurück.
    """
    # Aktueller Wochentag (Montag=0, ... Sonntag=6)
    today_weekday = datetime.now().weekday()

    schedules = db.query(Schedule).filter(
        Schedule.employee_id == current_employee.id,
        Schedule.weekday == today_weekday
    ).all()

    if not schedules:
        return []

    return schedules