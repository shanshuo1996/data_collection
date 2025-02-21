# Auto Task System

一个自动化任务处理系统，支持用户注册、任务分发、积分奖励等功能。

## 功能特点

- 用户注册和身份验证
- 实时任务分发
- 自动任务完成
- 积分奖励系统
- 实时排行榜
- WebSocket 实时通信

## 安装部署

1. 克隆项目
```bash
git clone https://github.com/shanshuo1996/data_collection
cd auto-task-system
```

2. 安装依赖
```bash
pip install -r requirements.txt
```

3. 启动服务
```bash
python run.py
```

## API 文档

### 用户相关

#### 注册用户
- **POST** `/register`
- **请求体**:
```json
{
    "username": "string"  // 4-20位字母数字
}
```
- **响应**:
```json
{
    "client_id": "string",
    "username": "string"
}
```

#### 获取用户信息
- **GET** `/user/{client_id}`
- **响应**:
```json
{
    "username": "string",
    "points": "integer",
    "client_id": "string"
}
```

### 任务相关

#### 获取排行榜
- **GET** `/rank`
- **响应**:
```json
[
    {
        "username": "string",
        "points": "integer"
    }
]
```

#### 提现积分
- **POST** `/withdraw`
- **请求体**:
```json
{
    "client_id": "string",
    "amount": "integer"
}
```
- **响应**:
```json
{
    "message": "string",
    "id": "string"
}
```

### WebSocket 接口

#### 连接 WebSocket
- **WebSocket** `/ws/{client_id}`

#### WebSocket 事件类型

1. **初始化事件 (init)**
```json
{
    "event": "init",
    "data": {
        "online_clients": "integer",
        "total_tasks": "integer",
        "points": "integer",
        "username": "string"
    }
}
```

2. **新任务事件 (new_task)**
```json
{
    "event": "new_task",
    "data": {
        "id": "string",
        "name": "string",
        "duration": "integer",
        "reward": "integer"
    }
}
```

3. **积分更新事件 (points_update)**
```json
{
    "event": "points_update",
    "data": {
        "points": "integer"
    }
}
```

4. **在线人数更新 (online_count)**
```json
{
    "event": "online_count",
    "data": "integer"
}
```

5. **任务完成提交**
```json
{
    "event": "task_complete",
    "data": {
        "task_id": "string",
        "result": "string"
    }
}
```

### 批量添加任务示例

```bash
# 添加2个跳转任务
curl -X POST http://localhost:8000/add_tasks \
  -H "Content-Type: application/json" \
  -d '{
    "tasks": [
      {
        "name": "跳转任务-1",
        "duration": 2,
        "reward": 50,
        "data": {
          "scheme": "snssdk1128://user/profile/12345"
        }
      },
      {
        "name": "跳转任务-2",
        "duration": 3,
        "reward": 50,
        "data": {
          "scheme": "snssdk1128://user/profile/23456"
        }
      }
    ]
  }'
```

或者使用 for 循环批量生成：

```bash
for i in {1..10}; do
  user_id=$((RANDOM % 90000 + 10000))
  curl -X POST http://localhost:8000/add_tasks \
    -H "Content-Type: application/json" \
    -d "{
      \"tasks\": [{
        \"id\": \"task-$i\",
        \"name\": \"跳转任务-$i\",
        \"duration\": $((RANDOM % 5 + 1)),
        \"reward\": 50,
        \"data\": {
          \"scheme\": \"snssdk1128://user/profile/$user_id\"
        }
      }]
    }"
done
```

这个命令会：
1. 创建10个随机的跳转任务
2. 每个任务持续1-5秒不等
3. 每个任务奖励50积分
4. 每个任务包含跳转scheme和对应的curl命令

## 开发环境要求

- Python 3.7+
- FastAPI
- WebSocket 支持
- SQLAlchemy (数据库ORM)

## 许可证

MIT License

## 贡献指南

欢迎提交 Issue 和 Pull Request。在提交 PR 之前，请确保：

1. 代码符合 PEP 8 规范
2. 添加了必要的测试
3. 更新了相关文档
