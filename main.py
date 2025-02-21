from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
from datetime import datetime
import uuid
import asyncio
import random
from typing import List, Dict


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class TaskManager:
    def __init__(self):
        self.pending_tasks = []
        self.in_progress = {}
        self.clients = {}
        self.user_points = {}

    def add_task(self, task):
        self.pending_tasks.append(task)

    def generate_tasks(self, count=1000):
        new_tasks = [{
            "id": str(uuid.uuid4()),
            "name": f"Task-{i}",
            "duration": random.randint(1, 3),
            "reward": random.randint(10, 100)
        } for i in range(count)]
        self.pending_tasks.extend(new_tasks)
        random.shuffle(self.pending_tasks)

    def get_idle_clients(self):
        return [client_id for client_id in self.clients if not any(t["client_id"] == client_id for t in self.in_progress
.values())]

    async def assign_task(self, client_id):
        if self.pending_tasks and client_id in self.clients:
            task = self.pending_tasks.pop()
            self.in_progress[task['id']] = {
                "client_id": client_id,
                "task": task,
                "start_time": datetime.now()
            }
            await self.send_to_client(client_id, {
                "event": "new_task",
                "data": task
            })
            return True
        return False

    async def send_to_client(self, client_id, message):
        if client_id in self.clients:
            await self.clients[client_id].send_text(json.dumps(message))

    def total_tasks(self):
        return len(self.pending_tasks) + len(self.in_progress)

task_manager = TaskManager()

task_manager.generate_tasks()

results = []


@app.post("/add_tasks")
async def add_tasks(tasks: List[Dict]):
    for task in tasks:
        task_manager.add_task(task)
    
    return {"message": f"Added {len(tasks)} tasks"}

@app.get("/results")
async def get_results(page: int = 1, per_page: int = 10):
    start = (page - 1) * per_page
    end = start + per_page > len(results) and len(results) or start + per_page
    return results[start:end]

@app.get("/rank")
async def get_rank(page: int = 1, per_page: int = 10):
    clients = task_manager.user_points
    sorted_clients = dict(sorted(clients.items(), key=lambda x: x[1], reverse=True))
    start = (page - 1) * per_page
    end = start + per_page > len(sorted_clients) and len(sorted_clients) or start + per_page
    results = [{"client_id": k, "points": v} for k, v in list(sorted_clients.items())[start:end]]
    return results[start:end]


@app.get("/generate-tasks")
async def generate_tasks():
    task_manager.generate_tasks()
    # 广播任务总数更新
    await manager.broadcast({
        "event": "task_count",
        "data": task_manager.total_tasks()
    })
    # 立即分配任务给空闲客户端
    for client_id in list(task_manager.clients.keys()):
        if not any(t["client_id"] == client_id for t in task_manager.in_progress.values()):
            await task_manager.assign_task(client_id)
    return {"message": "1000 tasks generated"}

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict = {}

    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        task_manager.clients[client_id] = websocket
        await self.broadcast_online_count()
        await self.send_initial_data(websocket)
        await self.try_assign_task(client_id)

    async def send_initial_data(self, websocket):
        await websocket.send_text(json.dumps({
            "event": "init",
            "data": {
                "online_clients": len(self.active_connections),
                "total_tasks": task_manager.total_tasks()
            }
        }))

    async def try_assign_task(self, client_id):
        if client_id in self.active_connections:
            assigned = await task_manager.assign_task(client_id)
            if not assigned:
                await task_manager.send_to_client(client_id, {
                    "event": "waiting"
                })

    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
        if client_id in task_manager.clients:
            del task_manager.clients[client_id]
        asyncio.create_task(self.broadcast_online_count())

    async def broadcast_online_count(self):
        await self.broadcast({
            "event": "online_count",
            "data": len(self.active_connections)
        })

    async def broadcast(self, message):
        message_str = json.dumps(message)
        for conn in self.active_connections.values():
            await conn.send_text(message_str)

manager = ConnectionManager()

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await manager.connect(websocket, client_id)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            print(f"Received message: {message}")
            
            if message["event"] == "task_complete":
                task_id = message["data"]["task_id"]
                result = message["data"]["result"]
                results.append({
                    "task_id": task_id,
                    "result": result
                })

                if task_id in task_manager.in_progress:
                    task = task_manager.in_progress[task_id]["task"]
                    task_manager.user_points[client_id] = task_manager.user_points.get(client_id, 0) + task["reward"]
                    del task_manager.in_progress[task_id]
                    # 广播任务总数更新
                    await manager.broadcast({
                        "event": "task_count",
                        "data": task_manager.total_tasks()
                    })
                    await manager.try_assign_task(client_id)
                    await websocket.send_text(json.dumps({
                        "event": "points_update",
                        "data": {"points": task_manager.user_points[client_id]}
                    }))
    except WebSocketDisconnect:
        manager.disconnect(client_id)


async def task_scheduler():
    while True:
        await asyncio.sleep(5)

        idle_clients = task_manager.get_idle_clients()
        while idle_clients and task_manager.assign_task(idle_clients.pop(0)):
            pass

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(task_scheduler())


@app.get("/")
async def get():
    return HTMLResponse("""
    <html>
        <head>
            <title>Auto Task System</title>
            <style>
                body { font-family: Arial, sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
                #status { padding: 10px; margin: 10px 0; border: 1px solid #ddd; }
                .task { background: #f5f5f5; padding: 15px; margin: 10px 0; border-radius: 5px; }
                .progress-bar { height: 20px; background: #eee; border-radius: 10px; overflow: hidden; }
                .progress { height: 100%; background: #4CAF50; transition: width 0.3s ease; }
                #stats { background: #f8f9fa; padding: 15px; border-radius: 5px; margin: 10px 0; }
                #stats p { margin: 5px 0; }
            </style>
        </head>
        <body>
            <h1>Auto Task System</h1>
            <div id="stats">
                <p>Online Workers: <span id="online-count">0</span></p>
                <p>Total Tasks: <span id="task-count">0</span></p>
                <p>My Points: <span id="points">0</span></p>
            </div>
            <div id="current-task"></div>
            <div id="rankings" style="margin-top: 20px;">
                <h2>Worker Rankings</h2>
                <div id="rank-list"></div>
            </div>
            <style>
                #rankings {
                    background: #f8f9fa;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                
                .rank-item {
                    display: flex;
                    justify-content: space-between;
                    padding: 10px;
                    margin: 5px 0;
                    background: white;
                    border-radius: 4px;
                    transition: transform 0.2s;
                }
                
                .rank-item:hover {
                    transform: translateX(5px);
                    box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                }
                
                .rank-position {
                    width: 40px;
                    text-align: center;
                    font-weight: bold;
                    color: #666;
                }
                
                .client-id {
                    flex-grow: 1;
                    margin: 0 15px;
                    font-family: monospace;
                    color: #333;
                }
                
                .points {
                    width: 80px;
                    text-align: right;
                    color: #2c3e50;
                    font-weight: bold;
                }
            </style>
            
            <script>
                const clientId = `client_${Math.random().toString(36).substr(2, 9)}`;
                const ws = new WebSocket(`ws://${location.host}/ws/${clientId}`);
                var currentTask = null;
                
                ws.onmessage = (event) => {
                    const msg = JSON.parse(event.data);
                    switch(msg.event) {
                        case 'init':
                            document.getElementById('online-count').textContent = msg.data.online_clients;
                            document.getElementById('task-count').textContent = msg.data.total_tasks;
                            break;
                            
                        case 'online_count':
                            document.getElementById('online-count').textContent = msg.data;
                            break;
                            
                        case 'task_count':
                            document.getElementById('task-count').textContent = msg.data;
                            break;
                            
                        case 'new_task':
                            showTask(msg.data);
                            currentTask = msg.data;
                            startAutoComplete(msg.data.duration);
                            break;
                            
                        case 'points_update':
                            document.getElementById('points').textContent = msg.data.points;
                            break;
                            
                        case 'waiting':
                            document.getElementById('current-task').innerHTML = 
                                '<div class="task">Waiting for new tasks...</div>';
                            break;
                    }
                };

                function showTask(task) {
                    document.getElementById('current-task').innerHTML = `
                        <div class="task">
                            <h3>${task.name}</h3>
                            <p>Duration: ${task.duration}s</p>
                            <p>Reward: ${task.reward} points</p>
                            <div class="progress-bar">
                                <div class="progress" style="width: 0%"></div>
                            </div>
                        </div>
                    `;
                }

                function startAutoComplete(duration) {
                    const progressBar = document.querySelector('.progress');
                    let width = 0;
                    const interval = setInterval(() => {
                        width += 10 / duration;
                        progressBar.style.width = `${width}%`;
                        
                        if (width >= 100) {
                            clearInterval(interval);
                            ws.send(JSON.stringify({
                                event: "task_complete",
                                data: { task_id: currentTask.id, result: generateRandomHash() }
                            }));
                        }
                    }, 100);
                }
                
                function generateRandomHash() {
                    const array = new Uint8Array(16);
                    crypto.getRandomValues(array);
                    return Array.from(array, 
                        byte => byte.toString(16).padStart(2, '0')).join('');
                }
                        
                // 初始化获取排行榜
                fetchRankings();
                setInterval(fetchRankings, 30000); // 30秒刷新一次

                async function fetchRankings() {
                    try {
                        const response = await fetch('/rank');
                        const rankings = await response.json();
                        renderRankings(rankings);
                    } catch (error) {
                        console.error('Failed to fetch rankings:', error);
                    }
                }

                function renderRankings(data) {
                    const container = document.getElementById('rank-list');
                    const items = data.map((item, index) => `
                        <div class="rank-item">
                            <div class="rank-position">#${index + 1}</div>
                            <div class="client-id">${item.client_id}</div>
                            <div class="points">${item.points} pts</div>
                        </div>
                    `).join('');
                    
                    container.innerHTML = `
                        <div style="margin-bottom: 10px; color: #666; font-size: 0.9em;">
                            Total Workers: ${data.length}
                        </div>
                        ${items}
                    `;
                }
            </script>
        </body>
    </html>
    """)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)