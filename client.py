import asyncio
import websockets
import json
import subprocess

async def execute_command(command):
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=10
        )
        return True, result.stdout.decode()
    except Exception as e:
        return False, str(e)

async def handle_tasks():
    async with websockets.connect('ws://localhost:8080/ws') as ws:
        while True:
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=5)
                data = json.loads(message)
                if data['type'] == 'task':
                    success, output = await execute_command(data['command'])
                    await ws.send(json.dumps({
                        "type": "result",
                        "task_id": data['task_id'],
                        "success": success,
                        "output": output
                    }))
            except (asyncio.TimeoutError, websockets.ConnectionClosed):
                continue

if __name__ == '__main__':
    asyncio.run(handle_tasks())