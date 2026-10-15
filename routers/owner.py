"""Self-service owner overview. No owner ID is accepted from the client."""
from fastapi import APIRouter, Depends
from Database.getConnection import engine
from utils.security import get_current_user
from services.owner_overview import build_owner_overview

router = APIRouter(prefix="/owner", tags=["Owner"])

@router.get("/overview")
def overview(user_id: str = Depends(get_current_user)):
    return build_owner_overview(engine, user_id)
