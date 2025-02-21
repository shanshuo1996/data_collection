from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
import uuid
from typing import List

from app.models.models import User, Task, Result, Withdrawal
from app.schemas.schemas import RegisterRequest, TaskList
from app.templates.index import get_html_template
from app.core.instances import task_manager

router = APIRouter()

@router.post("/register")
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

@router.get("/user/{client_id}")
async def get_user_info(client_id: str):
    user = await User.get_or_none(id=client_id)
    if not user:
        raise HTTPException(404, "用户不存在")
    
    return {
        "username": user.username,
        "points": user.points,
        "created_at": user.created_at
    }

@router.get("/results")
async def get_results(page: int = 1, per_page: int = 10):
    # 获取总记录数
    total_count = await Result.all().count()
    
    # 获取当前页数据
    results = await Result.all().offset((page-1)*per_page).limit(per_page).values(
        "id", "result_data", "created_at",
        task_id="task__id",
        task_name="task__name"
    )
    
    # 计算是否还有更多数据
    has_more = (page * per_page) < total_count
    
    return {
        "results": results,
        "has_more": has_more
    }

@router.get("/rank")
async def get_rank(page: int = 1, per_page: int = 10):
    users = await User.all().order_by('-points').offset((page-1)*per_page).limit(per_page).values(
        "username", "points"
    )
    return users

@router.post("/add_tasks")
async def add_tasks(task_list: TaskList):
    try:
        task_data = [t.dict() for t in task_list.tasks]
        existing_ids = await Task.filter(id__in=[t['id'] for t in task_data]).values_list('id', flat=True)
        
        unique_tasks = [t for t in task_data if t['id'] not in existing_ids]
        
        if not unique_tasks:
            return {"message": "No new tasks added", "duplicates": len(task_data) - len(unique_tasks)}
        
        chunk_size = 1000
        for i in range(0, len(unique_tasks), chunk_size):
            await Task.bulk_create(
                [Task(**task) for task in unique_tasks[i:i+chunk_size]],
                batch_size=chunk_size
            )
        
        # 广播任务数量更新给所有客户端
        total_tasks = await task_manager.get_pending_tasks_count()
        for client_id in task_manager.clients:
            await task_manager.send_to_client(client_id, {
                "event": "task_count",
                "data": {"total_tasks": total_tasks}
            })

        # 尝试分配任务
        assigned_count = await task_manager.try_assign_tasks()
        
        return {
            "message": f"Added {len(unique_tasks)} tasks",
            "duplicates": len(task_data) - len(unique_tasks),
            "assigned_clients": assigned_count
        }
    
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"任务创建失败: {str(e)}"
        )

@router.post("/withdraw")
async def create_withdrawal(client_id: str, amount: int):
    user = await User.get(id=client_id)
    if user.points < amount:
        return JSONResponse({"error": "Insufficient points"}, status_code=400)
    
    user.points -= amount
    await user.save()
    
    withdrawal = await Withdrawal.create(
        user=user,
        amount=amount,
        status='pending'
    )
    return {"message": "Withdrawal request created", "id": withdrawal.id}

@router.get("/")
async def get_index():
    return HTMLResponse(get_html_template()) 