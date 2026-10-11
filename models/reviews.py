from typing import Optional

from pydantic import BaseModel, Field, StrictInt, field_validator


class ReviewCreate(BaseModel):
    booking_id: str
    stars: StrictInt = Field(ge=1, le=5)
    review_text: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("review_text")
    @classmethod
    def normalize_text(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() or None if value is not None else None


class ReviewReportCreate(BaseModel):
    reason: str = Field(min_length=2, max_length=32)
    detail: Optional[str] = Field(default=None, max_length=1000)


class ReviewModeration(BaseModel):
    action: str
    reason: str = Field(min_length=3, max_length=1000)
