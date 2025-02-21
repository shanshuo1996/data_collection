from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
from datetime import datetime, timedelta
import asyncio

from app.models.models import Task, User
from app.services.task_manager import TaskManager
from app.core.instances import task_manager, connection_manager

router = APIRouter()

@router.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    # 验证客户端ID是否存在
    if not await User.exists(id=client_id):
        await websocket.close(code=1008)
        return
    
    await connection_manager.connect(websocket, client_id)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message["event"] == "task_complete":
                task_id = message["data"]["task_id"]
                result = message["data"]["result"]
                
                # 更新任务状态和用户积分
                new_points = await task_manager.complete_task(task_id, result)
                
                # 广播更新
                await websocket.send_text(json.dumps({
                    "event": "points_update",
                    "data": {"points": new_points}
                }))

                await websocket.send_text(json.dumps({
                    "event": "task_count",
                    "data": {"total_tasks": await task_manager.get_pending_tasks_count()}
                }))
                
                # 尝试分配新任务
                await connection_manager.try_assign_task(client_id)
                
    except WebSocketDisconnect:
        connection_manager.disconnect(client_id)

async def check_timeout_tasks():
    while True:
        await asyncio.sleep(60)
        timeout_threshold = datetime.now() - timedelta(minutes=5)
        
        # 查找超时任务
        timeout_tasks = await Task.filter(
            status='in_progress',
            started_at__lte=timeout_threshold
        )
        
        for task in timeout_tasks:
            task.status = 'pending'
            task.client_id = None
            task.started_at = None
            await task.save()

async def task_scheduler(task_manager: TaskManager):
    while True:
        await asyncio.sleep(5)
        idle_clients = task_manager.get_idle_clients()
        for client_id in idle_clients:
            await task_manager.assign_task(client_id) 