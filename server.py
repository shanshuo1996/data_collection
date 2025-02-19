import asyncio
import aiosqlite
from aiohttp import web
import uuid
import json
from datetime import datetime
from collections import deque

# 全局存储
tasks = {}
task_queue = deque()
in_progress = {}
idle_clients = set()
MAX_RETRIES = 3
TASK_TIMEOUT = 30

class Task:
    def __init__(self, command):
        self.task_id = str(uuid.uuid4())
        self.command = command
        self.status = "pending"
        self.retries = 0
        self.created_at = datetime.now()
        self.completed_at = None
        self.client_id = None

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    client_id = str(uuid.uuid4())
    print(f"Client {client_id} connected")
    
    idle_clients.add(ws)
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                data = json.loads(msg.data)
                if data['type'] == 'result':
                    await handle_task_result(ws, data)
    finally:
        idle_clients.discard(ws)
        print(f"Client {client_id} disconnected")
    return ws

async def handle_task_result(ws, data):
    task_id = data['task_id']
    if task_id not in in_progress:
        return
    
    task = in_progress.pop(task_id)
    task.status = "completed" if data['success'] else "failed"
    task.completed_at = datetime.now()
    task.output = data['output']
    
    # 保存到数据库
    async with aiosqlite.connect('tasks.db') as db:
        await db.execute('''
            INSERT INTO tasks VALUES 
            (?,?,?,?,?,?,?,?)
        ''', (
            task.task_id, task.command, task.status,
            task.client_id, task.output, 
            task.created_at.isoformat(),
            task.completed_at.isoformat(),
            task.retries
        ))
        await db.commit()
    
    idle_clients.add(ws)
    print(f"Task {task_id} completed")

async def submit_task(request):
    data = await request.json()
    if 'command' not in data:
        return web.json_response({"error": "Missing command"}, status=400)
    
    task = Task(data['command'])
    tasks[task.task_id] = task
    task_queue.append(task)
    return web.json_response({"task_id": task.task_id}, status=201)

async def get_task_status(request):
    task_id = request.match_info['task_id']
    if task_id not in tasks:
        return web.json_response({"error": "Task not found"}, status=404)
    
    task = tasks[task_id]
    return web.json_response({
        "task_id": task.task_id,
        "status": task.status,
        "command": task.command,
        "retries": task.retries,
        "output": getattr(task, 'output', None)
    })

async def task_scheduler():
    while True:
        await asyncio.sleep(1)
        while task_queue and idle_clients:
            task = task_queue.popleft()
            if task.retries >= MAX_RETRIES:
                task.status = "failed"
                continue
            
            ws = idle_clients.pop()
            task.client_id = id(ws)
            task.status = "in_progress"
            task.retries += 1
            
            in_progress[task.task_id] = task
            asyncio.create_task(
                send_task_with_timeout(ws, task)
            )

async def send_task_with_timeout(ws, task):
    try:
        await ws.send_json({
            "type": "task",
            "task_id": task.task_id,
            "command": task.command
        })
        await asyncio.wait_for(
            wait_for_completion(task.task_id),
            timeout=TASK_TIMEOUT
        )
    except (asyncio.TimeoutError, ConnectionError):
        handle_task_timeout(task)

async def wait_for_completion(task_id):
    while task_id in in_progress:
        await asyncio.sleep(1)

def handle_task_timeout(task):
    print(f"Task {task.task_id} timeout")
    task.status = "pending"
    task_queue.append(task)
    in_progress.pop(task.task_id, None)

async def init_db(app):
    async with aiosqlite.connect('tasks.db') as db:
        await db.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY,
                command TEXT NOT NULL,
                status TEXT NOT NULL,
                client_id TEXT,
                output TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT,
                retries INTEGER
            )
        ''')
        await db.commit()

app = web.Application()
app.router.add_get('/ws', websocket_handler)
app.router.add_post('/tasks', submit_task)
app.router.add_get('/tasks/{task_id}', get_task_status)

async def start_background_tasks(app):
    asyncio.create_task(task_scheduler())

app.on_startup.append(init_db)
app.on_startup.append(start_background_tasks)

if __name__ == '__main__':
    web.run_app(app, port=8080)