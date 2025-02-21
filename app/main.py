from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from tortoise.contrib.fastapi import register_tortoise
import asyncio

from app.core.config import DB_CONFIG
from app.core.instances import task_manager
from app.api import endpoints, websocket

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时运行
    asyncio.create_task(websocket.task_scheduler(task_manager))
    asyncio.create_task(websocket.check_timeout_tasks())
    yield
    # 关闭时运行
    pass

app = FastAPI(lifespan=lifespan)

# 注册路由
app.include_router(endpoints.router)
app.include_router(websocket.router)

# 注册数据库
register_tortoise(
    app,
    config=DB_CONFIG,
    generate_schemas=True,
    add_exception_handlers=True,
)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True) 