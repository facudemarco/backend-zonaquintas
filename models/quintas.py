from pydantic import BaseModel, Field
from typing import Optional
from fastapi import Form

class QuintaCreate(BaseModel):
    title: str
    address: str
    latitude: float
    length: float
    city: str
    guests: int
    bedrooms: int
    bathrooms: int
    environments: str
    beds: int
    price: float
    description: Optional[str] = None
    owner_id: str
    currency_price: str
    created_at: Optional[str] = None
    a_a: Optional[bool] = False
    medical_kit: Optional[bool] = False
    wire: Optional[bool] = False
    kitchen: Optional[bool] = False
    cutlery: Optional[bool] = False
    parking: Optional[bool] = False
    home_stove: Optional[bool] = False
    refrigerator: Optional[bool] = False
    jacuzzi: Optional[bool] = False
    kids_games: Optional[bool] = False
    washing_machine: Optional[bool] = False
    blankets: Optional[bool] = False
    grill: Optional[bool] = False
    pool: Optional[bool] = False
    playroom: Optional[bool] = False
    camera_clothes: Optional[bool] = False
    bed_sheets: Optional[bool] = False
    dryer: Optional[bool] = False
    towels: Optional[bool] = False
    tv: Optional[bool] = False
    wifi: Optional[bool] = False
    visits: Optional[int] = 0
    crockery: Optional[bool] = False



class QuintaUpdate(BaseModel):
    title: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    length: Optional[float] = None
    city: Optional[str] = None
    guests: Optional[int] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    environments: Optional[str] = None
    beds: Optional[int] = None
    price: Optional[float] = None
    description: Optional[str] = None
    owner_id: Optional[str] = None
    currency_price: Optional[str] = None
    a_a: Optional[bool] = None
    medical_kit: Optional[bool] = None
    wire: Optional[bool] = None
    kitchen: Optional[bool] = None
    cutlery: Optional[bool] = None
    parking: Optional[bool] = None
    home_stove: Optional[bool] = None
    refrigerator: Optional[bool] = None
    jacuzzi: Optional[bool] = None
    kids_games: Optional[bool] = None
    washing_machine: Optional[bool] = None
    blankets: Optional[bool] = None
    grill: Optional[bool] = None
    pool: Optional[bool] = None
    playroom: Optional[bool] = None
    camera_clothes: Optional[bool] = None
    bed_sheets: Optional[bool] = None
    dryer: Optional[bool] = None
    towels: Optional[bool] = None
    tv: Optional[bool] = None
    wifi: Optional[bool] = None
    visits: Optional[int] = None
    crockery: Optional[bool] = None


