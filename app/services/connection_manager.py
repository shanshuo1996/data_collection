from fastapi import WebSocket
from app.models.models import User
from app.services.task_manager import TaskManager
import json

class ConnectionManager:
    def __init__(self, task_manager: TaskManager):
        self.task_manager = task_manager

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.task_manager.clients[client_id] = websocket
        await self.send_initial_data(websocket, client_id)
        await self.try_assign_task(client_id)

    async def send_initial_data(self, websocket: WebSocket, client_id: str):
        user_points = (await User.get_or_create(id=client_id))[0].points
        user = await User.get_or_none(id=client_id)

        await websocket.send_text(json.dumps({
            "event": "init",
            "data": {
                "online_clients": len(self.task_manager.clients),
                "total_tasks": await self.task_manager.get_pending_tasks_count(),
                "points": user_points,
                "username": user.username
            }
        }))

    async def try_assign_task(self, client_id: str):
        if client_id in self.task_manager.clients:
            assigned = await self.task_manager.assign_task(client_id)
            if not assigned:
                await self.task_manager.send_to_client(client_id, {"event": "waiting"})

    def disconnect(self, client_id: str):
        if client_id in self.task_manager.clients:
            del self.task_manager.clients[client_id] 