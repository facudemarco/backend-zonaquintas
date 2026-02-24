from fastapi import FastAPI
from routers import quintas, auth, wallet
from fastapi.middleware.cors import CORSMiddleware
import os
from fastapi.staticfiles import StaticFiles

app = FastAPI(root_path="/MdpuF8KsXiRArNlHtl6pXO2XyLSJMTQ8_Zonaquintas/api")

origins = [
    "http://localhost",
    "http://localhost:3009",
    "http://localhost:3000",
    "https://zonaquintas.com",
    "https://www.zonaquintas.com",
    "http://zonaquintas.com",
    "http://www.zonaquintas.com",
]

app.add_middleware( 
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Set-Cookie"],
)

IMAGES_DIR = os.path.join(os.getcwd(), "images")
app.mount("/MdpuF8KsXiRArNlHtl6pXO2XyLSJMTQ8_Zonaquintas/api/images", StaticFiles(directory=IMAGES_DIR), name="images")

IS_PROD = os.getenv("ENV") == "production"
print(IS_PROD)

@app.get("/")
async def root():
    return {"message": "API Zona Quintas by iWeb Technology. 2025 All rights reserved."}

app.include_router(auth.router)
app.include_router(quintas.router)
app.include_router(wallet.router)