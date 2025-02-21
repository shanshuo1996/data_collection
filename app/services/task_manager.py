import random
import uuid
from datetime import datetime
from typing import Dict, Any
from fastapi import WebSocket
import json
from app.models.models import Task, User, Result

class TaskManager:
    def __init__(self):
        self.clients: Dict[str, WebSocket] = {}

    def get_idle_clients(self):
        return [client_id for client_id in self.clients]

    async def generate_tasks(self, count=1000):
        new_tasks = [{
            "id": str(uuid.uuid4()),
            "name": f"Task-{i}",
            "duration": random.randint(1, 3),
            "reward": random.randint(10, 100)
        } for i in range(count)]
        
        await Task.bulk_create([
            Task(**task) for task in new_tasks
        ])

    async def get_pending_tasks_count(self):
        return await Task.filter(status='pending').count()

    async def get_total_tasks_count(self):
        return await Task.all().count()

    async def assign_task(self, client_id: str) -> bool:
        task = await Task.filter(status='pending').first().select_for_update()
        if task:
            task.status = 'in_progress'
            task.client_id = client_id
            task.started_at = datetime.now()
            await task.save()
            
            await self.send_to_client(client_id, {
                "event": "new_task",
                "data": {
                    "id": task.id,
                    "name": task.name,
                    "duration": task.duration,
                    "reward": task.reward
                }
            })
            return True
        return False

    async def complete_task(self, task_id: str, result_data: Any):
        task = await Task.get(id=task_id)
        task.status = 'completed'
        task.completed_at = datetime.now()
        await task.save()
        
        await Result.create(task=task, result_data={'data': result_data})
        
        user, _ = await User.get_or_create(id=task.client_id)
        user.points += task.reward
        await user.save()
        
        return user.points

    async def send_to_client(self, client_id: str, message: Dict):
        if client_id in self.clients:
            await self.clients[client_id].send_text(json.dumps(message)) 