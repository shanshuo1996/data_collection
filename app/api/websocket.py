from fastapi import APIRouter, WebSocket
from app.services.websocket_service import WebSocketService

router = APIRouter()

@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await WebSocketService.handle_connection(websocket, client_id) 