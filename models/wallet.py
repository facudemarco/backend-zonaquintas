from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import date

class TransactionStatus(str, Enum):
    RETENIDO = "RETENIDO"
    DISPONIBLE = "DISPONIBLE"
    ENTREGADO = "ENTREGADO"
    CANCELADO = "CANCELADO"

class Currency(str, Enum):
    ARS = "ARS"
    USD = "USD"

class TransactionCreate(BaseModel):
    owner_id: str
    amount: float
    currency: Currency
    quinta_id: Optional[str] = None
    description: Optional[str] = None
    transfer_date_estimate: Optional[date] = None
    status: TransactionStatus = TransactionStatus.RETENIDO

class TransactionStatusUpdate(BaseModel):
    status: TransactionStatus
