from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.api.routes import router
from app.utils.config import settings
from fastapi import WebSocket, WebSocketDisconnect

app = FastAPI(title="Voice Agent")

# Static mounts
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# API routes
app.include_router(router)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Simple echo websocket that accepts messages and echoes them back prefixed with 'Echo:'"""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            # optional: validate/parse JSON here
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        pass
