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
        self.client_states: Dict[str, str] = {}  # 新增客户端状态字典

    def get_idle_clients(self):
        return [
            client_id for client_id in self.clients 
            if self.client_states.get(client_id) != 'busy'
        ]

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
            
            # 设置客户端状态为忙碌
            self.client_states[client_id] = 'busy'
            
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
        
        # 重置客户端状态为空闲
        self.client_states[task.client_id] = 'idle'
        
        return user.points

    async def send_to_client(self, client_id: str, message: Dict):
        if client_id in self.clients:
            await self.clients[client_id].send_text(json.dumps(message))

    async def try_assign_tasks(self):
        """尝试为所有空闲客户端分配任务"""
        idle_clients = self.get_idle_clients()
        assigned_count = 0
        
        for client_id in idle_clients:
            assigned = await self.assign_task(client_id)
            if assigned:
                assigned_count += 1
            else:
                await self.send_to_client(client_id, {"event": "waiting"})
        
        return assigned_count

    async def try_assign_task(self, client_id: str):
        """尝试为单个客户端分配任务"""
        if client_id in self.get_idle_clients():
            assigned = await self.assign_task(client_id)
            if not assigned:
                await self.send_to_client(client_id, {"event": "waiting"})
            return assigned
        return False 