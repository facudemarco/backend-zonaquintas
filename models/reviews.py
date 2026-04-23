from typing import Optional

from pydantic import BaseModel, Field


class ReviewCreate(BaseModel):
    booking_id: str
    stars: int = Field(ge=1, le=5)
    review_text: Optional[str] = None
