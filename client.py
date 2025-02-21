import asyncio
import websockets
import json
import random

class SchemeHandler:
    """Scheme跳转模拟器"""
    @classmethod
    async def process_scheme(cls, scheme_url, requirements):
        """模拟scheme跳转和数据采集"""
        print(f"正在跳转: {scheme_url}")
        await asyncio.sleep(random.uniform(1, 3))  # 模拟跳转耗时
        
        # 生成模拟数据
        return {
            "success": True,
            "data": {
                "scheme": scheme_url,
                "screen": "base64_screenshot",
                "elements": [
                    {"type": "text", "content": "模拟文本内容"},
                    {"type": "button", "state": "clickable"}
                ] if 'elements' in requirements else None,
                "ocr": ["模拟OCR识别结果"] if 'ocr' in requirements else None
            }
        }

async def client_loop():
    async with websockets.connect('ws://localhost:8080/ws') as ws:
        while True:
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=15)
                data = json.loads(message)
                print(data)
                
                if data["type"] == "scheme_task":
                    print(f"处理任务 {data['task_id']}")
                    result = await SchemeHandler.process_scheme(
                        data["scheme_url"], 
                        data["requirements"]
                    )
                    
                    await ws.send(json.dumps({
                        "type": "task_result",
                        "task_id": data["task_id"],
                        "success": result["success"],
                        "result": result["data"]
                    }))
                    
            except (asyncio.TimeoutError, websockets.ConnectionClosed):
                await ws.send(json.dumps({"type": "heartbeat"}))
                continue


if __name__ == '__main__':
    # 正确的新式启动方法
    asyncio.run(client_loop())