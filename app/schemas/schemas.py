from pydantic import BaseModel, Field, validator
from typing import List
import uuid

class RegisterRequest(BaseModel):
    username: str

class TaskCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    duration: int = Field(..., gt=0)
    reward: int = Field(..., gt=0)
    data: dict = Field(default={})  # 任务数据，默认为空字典
    id: str = None

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