from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import date

class UserRegister(BaseModel):
    name: Optional[str] = None # Legacy mapping might use this contextually
    email: EmailStr
    password: str
    phone: Optional[int] = None
    date_of_birth: Optional[date] = None
    address: Optional[str] = None
    description: Optional[str] = None
    role: Optional[str] = "user"

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    phone: Optional[int] = None
    date_of_birth: Optional[date] = None
    address: Optional[str] = None
    description: Optional[str] = None
    role: Optional[str] = None
