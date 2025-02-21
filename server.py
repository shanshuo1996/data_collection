from aiohttp import web
import uuid
import json
import asyncio
from datetime import datetime

tasks = {}
task_queue = asyncio.Queue()
active_clients = set()

class TaskStatus:
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

async def submit_task(request):
    """提交scheme跳转任务"""
    data = await request.json()
    
    task = {
        "task_id": str(uuid.uuid4()),
        "scheme_url": data["scheme_url"],    # 示例：snssdk1128://poi/detail?id=xxx
        "data_requirements": data.get("data_requirements", []),  # 需要采集的数据类型
        "status": TaskStatus.PENDING,
        "created_at": datetime.now().isoformat(),
        "retries": 0,
        "max_retries": 3
    }
    
    tasks[task["task_id"]] = task
    await task_queue.put(task)
    return web.json_response({"task_id": task["task_id"]}, status=201)

async def websocket_handler(request):
    """客户端连接处理"""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    active_clients.add(ws)
    
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                await handle_client_message(ws, json.loads(msg.data))
    finally:
        active_clients.discard(ws)
    return ws


async def get_available_client():
    """获取可用客户端"""
    while True:
        for ws in active_clients:
            return ws  # 简单实现，实际应使用更智能的调度
        await asyncio.sleep(1)

        
async def handle_client_message(ws, data):
    """处理客户端上报"""
    if data["type"] == "task_result":
        task = tasks.get(data["task_id"])
        if task:
            task["status"] = TaskStatus.COMPLETED if data["success"] else TaskStatus.FAILED
            task["result"] = data.get("result")
            task["completed_at"] = datetime.now().isoformat()

async def task_dispatcher():
    """任务分发器"""
    while True:
        client_ws = await get_available_client()
        task = await task_queue.get()
        
        task["status"] = TaskStatus.PROCESSING
        task["retries"] += 1
        
        await client_ws.send_json({
            "type": "scheme_task",
            "task_id": task["task_id"],
            "scheme_url": task["scheme_url"],
            "requirements": task["data_requirements"]
        })
        
        asyncio.create_task(
            monitor_task_timeout(task, client_ws)
        )

async def monitor_task_timeout(task, ws):
    """任务超时监控"""
    try:
        await asyncio.wait_for(
            wait_for_task_completion(task["task_id"]),
            timeout=20
        )
    except asyncio.TimeoutError:
        if task["retries"] < task["max_retries"]:
            await task_queue.put(task)
        else:
            task["status"] = TaskStatus.FAILED

async def wait_for_task_completion(task_id):
    """等待任务完成"""
    while tasks[task_id]["status"] == TaskStatus.PROCESSING:
        await asyncio.sleep(0.5)

app = web.Application()
app.router.add_post('/tasks', submit_task)
app.router.add_get('/ws', websocket_handler)

if __name__ == '__main__':
    asyncio.get_event_loop().create_task(task_dispatcher())
    web.run_app(app, port=8080)