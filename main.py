from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.routes import router
from app.utils.config import settings

app = FastAPI(title="Voice Agent")

# Static mounts
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# API routes
app.include_router(router)