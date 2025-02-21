from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
from datetime import datetime, timedelta
import uuid
import asyncio
import random
from typing import List, Dict
from tortoise import fields, models,Tortoise
from tortoise.contrib.fastapi import register_tortoise
from fastapi import HTTPException
from pydantic import BaseModel, Field, validator



# Tortoise 模型定义
class User(models.Model):
    id = fields.CharField(pk=True, max_length=36)  # 使用客户端ID作为主键
    username = fields.CharField(max_length=50, unique=True)
    points = fields.IntField(default=0)
    created_at = fields.DatetimeField(auto_now_add=True)
    updated_at = fields.DatetimeField(auto_now=True)

    def __str__(self):
        return f"Points:{self.points}, created_at:{self.created_at}, updated_at:{self.updated_at}"

class Task(models.Model):
    id = fields.CharField(pk=True, max_length=36)
    name = fields.CharField(max_length=255)
    duration = fields.IntField()
    reward = fields.IntField()
    status = fields.CharField(max_length=20, default='pending')  # pending/in_progress/completed
    client_id = fields.CharField(max_length=36, null=True)
    started_at = fields.DatetimeField(null=True)
    completed_at = fields.DatetimeField(null=True)
    created_at = fields.DatetimeField(auto_now_add=True)
    
    def __str__(self):
        return f"Task:{self.name}, reward:{self.reward}, status:{self.status}, client_id:{self.client_id}"

class Result(models.Model):
    id = fields.IntField(pk=True)
    task = fields.ForeignKeyField('models.Task', related_name='results')
    result_data = fields.JSONField()
    created_at = fields.DatetimeField(auto_now_add=True)

class Withdrawal(models.Model):
    id = fields.IntField(pk=True)
    user = fields.ForeignKeyField('models.User', related_name='withdrawals')
    amount = fields.IntField()
    status = fields.CharField(max_length=20, default='pending')  # pending/completed/failed
    created_at = fields.DatetimeField(auto_now_add=True)

# 初始化FastAPI
app = FastAPI()

# 数据库配置
DB_CONFIG = {
    "connections": {
        "default": "sqlite://db.sqlite3"  # 连接名称必须与下方对应
    },
    "apps": {
        "models": {  # 此名称需要与模型 Meta 中的 app 对应
            "models": ["main"],  # 假设你的 Task 模型在 main.py 中
            "default_connection": "default",  # 关键配置
        }
    },
    "routers": []
}


register_tortoise(
    app,
    config=DB_CONFIG,
    generate_schemas=True,  # 自动创建表
    add_exception_handlers=True,
)

class TaskManager:
    def __init__(self):
        self.clients = {}  # 当前连接的客户端

    def get_idle_clients(self):
        return [client_id for client_id in self.clients if not any(t["client_id"] == client_id for t in self.in_progress
.values())]

    async def generate_tasks(self, count=1000):
        new_tasks = [{
            "id": str(uuid.uuid4()),
            "name": f"Task-{i}",
            "duration": random.randint(1, 3),
            "reward": random.randint(10, 100)
        } for i in range(count)]
        
        # 批量创建任务
        await Task.bulk_create([
            Task(**task) for task in new_tasks
        ])

    async def get_pending_tasks_count(self):
        return await Task.filter(status='pending').count()

    async def get_total_tasks_count(self):
        return await Task.all().count()

    async def assign_task(self, client_id):
        # 使用原子操作获取并锁定一个任务
        task = await Task.filter(status='pending').first().select_for_update()
        if task:
            task.status = 'in_progress'
            task.client_id = client_id
            task.started_at = datetime.now()
            await task.save()
            
            print("Assigned task", task.id, "to client", client_id)

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

    async def complete_task(self, task_id, result_data):
        task = await Task.get(id=task_id)
        task.status = 'completed'
        task.completed_at = datetime.now()
        await task.save()
        
        # 创建结果记录
        await Result.create(task=task, result_data={
            'data': result_data
        })
        
        # 更新用户积分（使用原子更新）
        user, _ = await User.get_or_create(id=task.client_id)
        user.points += task.reward
        await user.save()
        
        # 返回更新后的积分
        return user.points

    async def send_to_client(self, client_id, message):
        if client_id in self.clients:
            await self.clients[client_id].send_text(json.dumps(message))

task_manager = TaskManager()

class ConnectionManager:
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        task_manager.clients[client_id] = websocket
        await self.send_initial_data(websocket, client_id)
        await self.try_assign_task(client_id)

    async def send_initial_data(self, websocket, client_id):
        user_points = (await User.get_or_create(id=client_id))[0].points
        await websocket.send_text(json.dumps({
            "event": "init",
            "data": {
                "online_clients": len(task_manager.clients),
                "total_tasks": await task_manager.get_pending_tasks_count(),
                "points": user_points
            }
        }))

    async def try_assign_task(self, client_id):
        if client_id in task_manager.clients:
            assigned = await task_manager.assign_task(client_id)
            if not assigned:
                await task_manager.send_to_client(client_id, {"event": "waiting"})

    def disconnect(self, client_id: str):
        if client_id in task_manager.clients:
            del task_manager.clients[client_id]

manager = ConnectionManager()


from pydantic import BaseModel


# 添加请求体模型
class RegisterRequest(BaseModel):
    username: str

@app.post("/register")
async def register(request: RegisterRequest):
    username = request.username
    # 用户名格式验证
    if len(username) < 4 or len(username) > 20:
        raise HTTPException(400, "用户名长度需在4-20个字符之间")
    
    if not username.isalnum():
        raise HTTPException(400, "用户名只能包含字母和数字")
    
    # 检查用户名唯一性
    if await User.exists(username=username):
        raise HTTPException(400, "用户名已被占用")
    
    # 生成客户端ID
    client_id = str(uuid.uuid4())
    
    # 创建用户
    await User.create(
        id=client_id,
        username=username,
        points=0
    )
    
    return {
        "client_id": client_id,
        "username": username,
        "message": "注册成功，请妥善保管您的客户端ID"
    }

@app.get("/user/{client_id}")
async def get_user_info(client_id: str):
    user = await User.get_or_none(id=client_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    
    return {
        "username": user.username,
        "points": user.points,
        "created_at": user.created_at
    }


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    # 验证客户端ID是否存在
    if not await User.exists(id=client_id):
        await websocket.close(code=1008)
        return
    
    await manager.connect(websocket, client_id)
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message["event"] == "task_complete":
                task_id = message["data"]["task_id"]
                result = message["data"]["result"]

                print(f'Client {client_id} completed task {task_id} with result {result}')
                
                # 更新任务状态和用户积分
                new_points = await task_manager.complete_task(task_id, result)
                
                # 广播更新
                await websocket.send_text(json.dumps({
                    "event": "points_update",
                    "data": {"points": new_points}
                }))

                await websocket.send_text(json.dumps({
                    "event": "task_count",
                    "data": {"total_tasks":await task_manager.get_pending_tasks_count()}
                }))
                
                # 尝试分配新任务
                await manager.try_assign_task(client_id)
                
    except WebSocketDisconnect:
        manager.disconnect(client_id)

@app.get("/results")
async def get_results(page: int = 1, per_page: int = 10):
    results = await Result.all().offset((page-1)*per_page).limit(per_page).values(
        "id", "result_data", "created_at",
        task_id="task__id",
        task_name="task__name"
    )
    return results

@app.get("/rank")
async def get_rank(page: int = 1, per_page: int = 10):
    users = await User.all().order_by('-points').offset((page-1)*per_page).limit(per_page).values(
        "username", "points"
    )
    return users

# 定义任务创建模型
class TaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    duration: int = Field(..., gt=0)
    reward: int = Field(..., gt=0)
    id: str = None  # 可选字段

    @validator('id', pre=True, always=True)
    def set_id(cls, v):
        return v or str(uuid.uuid4())

    @validator('name')
    def validate_name(cls, v):
        if not v.isprintable():
            raise ValueError("包含非法字符")
        return v.strip()

class TaskList(BaseModel):
    tasks: List[TaskCreate]

# 批量创建任务端点
@app.post("/add_tasks")
async def add_tasks(task_list: TaskList):
    try:
        # 转换数据并验证唯一性
        task_data = [t.dict() for t in task_list.tasks]
        existing_ids = await Task.filter(id__in=[t['id'] for t in task_data]).values_list('id', flat=True)
        
        # 过滤重复ID
        unique_tasks = [t for t in task_data if t['id'] not in existing_ids]
        
        if not unique_tasks:
            return {"message": "No new tasks added", "duplicates": len(task_data) - len(unique_tasks)}
        
        # 分块批量插入（每1000条一个批次）
        chunk_size = 1000
        for i in range(0, len(unique_tasks), chunk_size):
            await Task.bulk_create(
                [Task(**task) for task in unique_tasks[i:i+chunk_size]],
                batch_size=chunk_size
            )
        
        return {
            "message": f"Added {len(unique_tasks)} tasks",
            "duplicates": len(task_data) - len(unique_tasks)
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"任务创建失败: {str(e)}"
        )

@app.post("/withdraw")
async def create_withdrawal(client_id: str, amount: int):
    user = await User.get(id=client_id)
    if user.points < amount:
        return JSONResponse({"error": "Insufficient points"}, status_code=400)
    
    # 原子操作：扣减积分并创建提现记录
    user.points -= amount
    await user.save()
    
    withdrawal = await Withdrawal.create(
        user=user,
        amount=amount,
        status='pending'
    )
    return {"message": "Withdrawal request created", "id": withdrawal.id}

# 定时任务：处理超时任务
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

async def task_scheduler():
    while True:
        await asyncio.sleep(5)

        idle_clients = task_manager.get_idle_clients()
        while idle_clients and task_manager.assign_task(idle_clients.pop(0)):
            pass

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(task_scheduler())
    asyncio.create_task(check_timeout_tasks())


# Web页面
@app.get("/")
async def get():
    return HTMLResponse("""
        <html>
        <head>
            <title>Auto Task System</title>
            <style>
                /* 新增认证相关样式 */
                .auth-container {
                    max-width: 400px;
                    margin: 50px auto;
                    padding: 20px;
                    background: #f8f9fa;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }

                .auth-form {
                    display: none;
                }

                .auth-form.active {
                    display: block;
                }

                .form-group {
                    margin-bottom: 15px;
                }

                .form-group label {
                    display: block;
                    margin-bottom: 5px;
                }

                .form-group input {
                    width: 100%;
                    padding: 8px;
                    border: 1px solid #ddd;
                    border-radius: 4px;
                }

                .auth-switch {
                    text-align: center;
                    margin-top: 15px;
                }

                .auth-switch a {
                    color: #007bff;
                    cursor: pointer;
                }

                .error-message {
                    color: #dc3545;
                    margin-top: 10px;
                }

                /* 原有样式保持不变 */
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
            <!-- 认证界面 -->
            <div id="auth-container" class="auth-container">
                <!-- 注册表单 -->
                <div id="register-form" class="auth-form">
                    <h2>用户注册</h2>
                    <div class="form-group">
                        <label>用户名：</label>
                        <input type="text" id="username" placeholder="4-20位字母数字">
                    </div>
                    <button onclick="register()">立即注册</button>
                    <div class="auth-switch">
                        已有账号？<a onclick="showLogin()">立即登录</a>
                    </div>
                    <div id="register-error" class="error-message"></div>
                </div>

                <!-- 登录表单 -->
                <div id="login-form" class="auth-form">
                    <h2>系统登录</h2>
                    <div class="form-group">
                        <label>客户端ID：</label>
                        <input type="text" id="client-id" placeholder="输入您的客户端ID">
                    </div>
                    <button onclick="login()">立即登录</button>
                    <div class="auth-switch">
                        没有账号？<a onclick="showRegister()">立即注册</a>
                    </div>
                    <div id="login-error" class="error-message"></div>
                </div>
            </div>

            <!-- 主界面（默认隐藏） -->
            <div id="main-interface" style="display: none;">
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
                let ws = null;
                let currentTask = null;
                let clientId = localStorage.getItem('client_id');

                // 初始化检查本地存储
                (function init() {
                    if (clientId) {
                        checkClientId(clientId).then(valid => {
                            if (valid) connectWebSocket(clientId);
                            else showLogin();
                        });
                    } else {
                        showRegister();
                    }
                })();

                // 显示注册表单
                function showRegister() {
                    document.getElementById('login-form').classList.remove('active');
                    document.getElementById('register-form').classList.add('active');
                }

                // 显示登录表单
                function showLogin() {
                    document.getElementById('register-form').classList.remove('active');
                    document.getElementById('login-form').classList.add('active');
                }

                // 注册逻辑
                async function register() {
                    const username = document.getElementById('username').value;
                    const errorElement = document.getElementById('register-error');
                        
                    if (!/^[a-zA-Z0-9]{4,20}$/.test(username)) {
                        errorElement.textContent = '用户名格式不正确（4-20位字母数字）';
                        return;
                    }

                    try {
                        const response = await fetch('/register', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({ username })
                        });

                        if (!response.ok) {
                            const error = await response.json();
                            throw new Error(error.detail);
                        }

                        const data = await response.json();
                        localStorage.setItem('client_id', data.client_id);
                        connectWebSocket(data.client_id);
                    } catch (error) {
                        errorElement.textContent = error.message;
                    }
                }

                // 登录逻辑
                async function login() {
                    const clientId = document.getElementById('client-id').value;
                    const errorElement = document.getElementById('login-error');

                    try {
                        const valid = await checkClientId(clientId);
                        if (!valid) throw new Error('无效的客户端ID');
                        
                        localStorage.setItem('client_id', clientId);
                        connectWebSocket(clientId);
                    } catch (error) {
                        errorElement.textContent = error.message;
                    }
                }

                // 验证客户端ID有效性
                async function checkClientId(clientId) {
                    try {
                        const response = await fetch(`/user/${clientId}`);
                        return response.ok;
                    } catch {
                        return false;
                    }
                }

                // 建立WebSocket连接
                function connectWebSocket(clientId) {
                    // 隐藏认证界面显示主界面
                    document.getElementById('auth-container').style.display = 'none';
                    document.getElementById('main-interface').style.display = 'block';

                    // 建立WebSocket连接
                    ws = new WebSocket(`ws://${location.host}/ws/${clientId}`);
                    
                    // 原有WebSocket消息处理逻辑
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
                                document.getElementById('task-count').textContent = msg.data.total_tasks;
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
                }

                // 保持原有任务处理逻辑不变
                        
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
                            <div class="client-id">${item.username}</div>
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