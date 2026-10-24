from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime

class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str
    role: Optional[str] = "mitarbeiter"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str = "mitarbeiter"
    user_name: str = ""
    personal_nr: str = ""
    must_change_password: bool = False

class UserResponse(UserBase):
    id: int
    role: str
    is_active: bool
    created_at: datetime
    
    class Config:
        from_attributes = True

class NewPassword(BaseModel):
    new_password: str
    old_password: Optional[str] = None

class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordReset(BaseModel):
    email: EmailStr
    code: str
    new_password: str

class PasswordResetByToken(BaseModel):
    token: str
    new_password: str