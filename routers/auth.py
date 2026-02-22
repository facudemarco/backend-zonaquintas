from fastapi import APIRouter, Response, HTTPException, Depends
from pydantic import BaseModel
from utils.security import create_access_token, get_current_user

router = APIRouter()

class LoginData(BaseModel):
    # En un sistema real de base de datos deberias usar username o email.
    user_id: str
    password: str

@router.post("/login", tags=["Auth"])
async def login(data: LoginData, response: Response):
    # Dummy authentication mapping (NO SE HASHEA LA PASSWORD AHORA MISMO)
    # Aca iría tu consulta a `engine` para verificar en MySQL si la usuaria y contrasenas matchean
    
    # if usuario no existe o la contraseña no matchea:
    #     raise HTTPException(status_code=401, detail="Credenciales invalidas")
    
    # Para el ejemplo asumo que si la contraseña no esta vacia, pasa el login exitosamente.
    if not data.password:
        raise HTTPException(status_code=400, detail="Falta contraseña")

    # Creamos el Token JWT asegurando que dure 60 dias (configurado internamente)
    token = create_access_token(data={"sub": data.user_id})

    # Guardamos en la Cookie HttpOnly usando el prefijo "Bearer "
    response.set_cookie(
        key="access_token",
        value=f"Bearer {token}",
        httponly=True,
        max_age=5184000, # 60 * 24 * 60 * 60
        samesite="lax",
        secure=False, # Si usas https ponelo en True
    )

    return {"message": "Sesion iniciada correctamente. Cookie guardada."}

@router.post("/logout", tags=["Auth"])
async def logout(response: Response):
    response.delete_cookie("access_token")
    return {"message": "Sesion cerrada correctamente."}

@router.get("/me", tags=["Auth"])
async def protect_route(current_user: str = Depends(get_current_user)):
    return {"message": f"Estas logueado bajo la identidad {current_user}"}
