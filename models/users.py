from pydantic import BaseModel, EmailStr
from typing import Optional, List
from datetime import date

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    phone: Optional[int] = None
    date_of_birth: Optional[date] = None
    address: Optional[str] = None
    description: Optional[str] = None
    role: Optional[str] = "user"
    owner_time: Optional[str] = None
    owner_location: Optional[str] = None
    average_opinions: Optional[float] = None
    
    # 1:N Relation arrays
    languages: Optional[List[str]] = None
    opinions: Optional[List[str]] = None
    pictures: Optional[List[str]] = None

class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    password: Optional[str] = None
    phone: Optional[int] = None
    date_of_birth: Optional[date] = None
    address: Optional[str] = None
    description: Optional[str] = None
    role: Optional[str] = None
    owner_time: Optional[str] = None
    owner_location: Optional[str] = None
    average_opinions: Optional[float] = None
    
    # 1:N Relation arrays
    languages: Optional[List[str]] = None
    opinions: Optional[List[str]] = None
    pictures: Optional[List[str]] = None
