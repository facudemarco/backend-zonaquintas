from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from Database.getConnection import get_db
from models.User import User
from Schemas.UserSchema import UserLogin

router = APIRouter()

async def verify_password(plain_password: str, hashed_password: str) -> bool:
    # Implement your password verification logic here
    pass

async def create_access_token(data: dict) -> str:
    # Implement your access token creation logic here
    pass

