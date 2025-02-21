from app.services.task_manager import TaskManager
from app.services.connection_manager import ConnectionManager

task_manager = TaskManager()
connection_manager = ConnectionManager(task_manager) 