# 运行一个server，运行多个client


# 提交单个任务
curl -X POST http://localhost:8080/tasks \
  -H "Content-Type: application/json" \
  -d '{"command": "ping -c 4 google.com"}'

# 批量提交任务
for i in {1..10}; do
  curl -X POST http://localhost:8080/tasks \
    -d "{\"command\": \"echo Task $i && sleep 2\"}"
done

# 查询单个任务状态
curl http://localhost:8080/tasks/{task_id}

# 查看执行结果
sqlite3 tasks.db
SELECT * FROM tasks ORDER BY created_at;
