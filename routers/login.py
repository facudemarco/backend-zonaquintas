from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session
from Database.getConnection import get_db
from models.User import User
from Schemas.UserSchema import UserLogin
from utils.auth import verify_password, create_access_token

router = APIRouter()

@router.post("/login")
async def login(user_credentials: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == user_credentials.email).first()
    if not user or not await verify_password(user_credentials.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    access_token = create_access_token(data={"sub": user.email})
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/protected-route")
async def protected_route(current_user: User = Depends(get_db)):
    return {"message": f"Hello, {current_user.email}. You have accessed a protected route!"}

@router.post("/logout")
async def logout():
    
    return {"message": "Successfully logged out"}