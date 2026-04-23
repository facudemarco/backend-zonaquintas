from pydantic import BaseModel


class FavoriteCreate(BaseModel):
    user_id: str
    quinta_id: str
