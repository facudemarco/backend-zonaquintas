from pydantic import BaseModel
from typing import Optional


class QuintaCreate(BaseModel):
    title: str
    address: str
    latitude: float
    length: float
    status: str
    payment_type: Optional[str] = None
    city: str
    guests: int
    bedrooms: int
    bathrooms: int
    environments: int
    beds: int
    price: float
    description: Optional[str] = None
    owner_id: str
    currency_price: str

    # Ropa de cama y baño
    sabanas: Optional[bool] = False
    mantas: Optional[bool] = False
    almohadas: Optional[bool] = False
    toilettes: Optional[bool] = False
    shampoo: Optional[bool] = False
    toallas: Optional[bool] = False
    secador_pelo: Optional[bool] = False
    lavarropas: Optional[bool] = False
    cambio_toallas: Optional[bool] = False

    # Cocina
    utensillos_cocina: Optional[bool] = False
    vajilla: Optional[bool] = False
    freezer: Optional[bool] = False

    # Entretenimiento / tecnología
    televisor: Optional[bool] = False
    radio: Optional[bool] = False
    tv: Optional[bool] = False
    cable: Optional[bool] = False
    internet: Optional[bool] = False
    parlantes: Optional[bool] = False

    # Confort interior
    jacuzzi: Optional[bool] = False
    playroom: Optional[bool] = False
    sofas: Optional[bool] = False

    # Exterior / deportes
    estacionamiento_techado: Optional[bool] = False
    parrilla: Optional[bool] = False
    estufa_gas: Optional[bool] = False
    hogar: Optional[bool] = False
    hamacas_paraguayas: Optional[bool] = False
    arboleda: Optional[bool] = False
    cancha_futbol: Optional[bool] = False
    piscina: Optional[bool] = False
    cancha_basquet: Optional[bool] = False
    cancha_tenis: Optional[bool] = False
    cancha_padel: Optional[bool] = False
    hamacas: Optional[bool] = False


class QuintaUpdate(BaseModel):
    title: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    length: Optional[float] = None
    status: str
    payment_type: Optional[str] = None
    city: Optional[str] = None
    guests: Optional[int] = None
    bedrooms: Optional[int] = None
    bathrooms: Optional[int] = None
    environments: Optional[int] = None
    beds: Optional[int] = None
    price: Optional[float] = None
    description: Optional[str] = None
    owner_id: Optional[str] = None
    currency_price: Optional[str] = None

    # Ropa de cama y baño
    sabanas: Optional[bool] = None
    mantas: Optional[bool] = None
    almohadas: Optional[bool] = None
    toilettes: Optional[bool] = None
    shampoo: Optional[bool] = None
    toallas: Optional[bool] = None
    secador_pelo: Optional[bool] = None
    lavarropas: Optional[bool] = None
    cambio_toallas: Optional[bool] = None

    # Cocina
    utensillos_cocina: Optional[bool] = None
    vajilla: Optional[bool] = None
    freezer: Optional[bool] = None

    # Entretenimiento / tecnología
    televisor: Optional[bool] = None
    radio: Optional[bool] = None
    tv: Optional[bool] = None
    cable: Optional[bool] = None
    internet: Optional[bool] = None
    parlantes: Optional[bool] = None

    # Confort interior
    jacuzzi: Optional[bool] = None
    playroom: Optional[bool] = None
    sofas: Optional[bool] = None

    # Exterior / deportes
    estacionamiento_techado: Optional[bool] = None
    parrilla: Optional[bool] = None
    estufa_gas: Optional[bool] = None
    hogar: Optional[bool] = None
    hamacas_paraguayas: Optional[bool] = None
    arboleda: Optional[bool] = None
    cancha_futbol: Optional[bool] = None
    piscina: Optional[bool] = None
    cancha_basquet: Optional[bool] = None
    cancha_tenis: Optional[bool] = None
    cancha_padel: Optional[bool] = None
    hamacas: Optional[bool] = None

class QuintaStatusUpdate(BaseModel):
    status: str