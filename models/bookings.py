from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, Field


class BookingCreate(BaseModel):
    quinta_id: str
    guest_id: str
    owner_id: str
    check_in: date
    check_out: date
    payment_type: Optional[str] = None
    guest_count: Optional[float] = None
    message: Optional[str] = None
    currency_price: Optional[str] = None
    amount: Optional[float] = None
    status: Optional[str] = "PENDIENTE"
    quinta_title: Optional[str] = None
    quinta_address: Optional[str] = None
    quinta_main_image: Optional[str] = None


class BookingStatusUpdate(BaseModel):
    status: str


class BookingPaymentCreate(BaseModel):
    payment_type: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = "PENDIENTE"
    rebill_payment_link_id: Optional[str] = None
    rebill_payment_link_url: Optional[str] = None
    rebill_transaction_id: Optional[str] = None
    payment_expire: Optional[date] = None
    paid_at: Optional[datetime] = None


class BookingPaymentUpdate(BaseModel):
    payment_type: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    status: Optional[str] = None
    rebill_payment_link_id: Optional[str] = None
    rebill_payment_link_url: Optional[str] = None
    rebill_transaction_id: Optional[str] = None
    payment_expire: Optional[date] = None
    paid_at: Optional[datetime] = Field(default=None)
