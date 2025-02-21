from tortoise import fields, models
from datetime import datetime

class User(models.Model):
    id = fields.CharField(pk=True, max_length=36)
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
    data = fields.JSONField(null=True)  # 存储任务相关数据
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
    status = fields.CharField(max_length=20, default='pending')
    created_at = fields.DatetimeField(auto_now_add=True) 