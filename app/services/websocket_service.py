from fastapi import WebSocket, WebSocketDisconnect
import json
from datetime import datetime, timedelta
import asyncio

from app.models.models import Task, User
from app.core.instances import task_manager, connection_manager

class WebSocketService:
    @staticmethod
    async def handle_connection(websocket: WebSocket, client_id: str):
        """处理新的WebSocket连接"""
        # 验证客户端ID是否存在
        if not await User.exists(id=client_id):
            await websocket.close(code=1008)
            return
        
        await connection_manager.connect(websocket, client_id)
        try:
            while True:
                data = await websocket.receive_text()
                await WebSocketService.handle_message(websocket, client_id, data)
        except WebSocketDisconnect:
            connection_manager.disconnect(client_id)

    @staticmethod
    async def handle_message(websocket: WebSocket, client_id: str, data: str):
        """处理WebSocket消息"""
        message = json.loads(data)
        
        if message["event"] == "task_complete":
            await WebSocketService.handle_task_complete(
                websocket, 
                client_id,
                message["data"]["task_id"],
                message["data"]["result"]
            )

    @staticmethod
    async def handle_task_complete(websocket: WebSocket, client_id: str, task_id: str, result: str):
        """处理任务完成事件"""
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

    @staticmethod
    async def check_timeout_tasks():
        """检查并处理超时任务"""
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

    @staticmethod
    async def task_scheduler():
        """任务调度器"""
        while True:
            await asyncio.sleep(5)
            await task_manager.try_assign_tasks() 