import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.v1.routers import api_router
from app.db.session import engine
from app.db.base import Base
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings 
from dotenv import load_dotenv
load_dotenv()

app = FastAPI(title="Vibes Inventory API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    # Base.metadata.create_all(bind=engine)    #only for inital develoment testing only
    pass

if os.getenv("USE_S3", "false").lower() == "false":
    os.makedirs("uploads/wastage", exist_ok=True)
    app.mount(
        "/static/uploads",
        StaticFiles(directory="uploads"),
        name="uploads"
    )

app.include_router(api_router, prefix="/api/v1")
