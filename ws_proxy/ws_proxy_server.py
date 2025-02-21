import asyncio
import socket
import uuid
from aiohttp import web
import logging

from socks5_server.socks5Server import Socks5Server

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('WSProxy')


server = Socks5Server()
        

async def websocket_handler(request):
    proxy = request.app['proxy']
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    try:
        # 处理WebSocket消息
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                conn_id, cmd, data = msg.data.split('|', 2)
                session = proxy.sessions.get(conn_id)
                if not session:
                    continue
                
                if cmd == 'CONNECT_OK':
                    # 建立到目标服务器的连接
                    addr, port = data.split(':')
                    session.target_reader, session.target_writer = await asyncio.open_connection(addr, port)
                    
                    # 发送SOCKS响应
                    reply = b'\x05\x00\x00\x01'  # IPv4
                    reply += socket.inet_aton('0.0.0.0')  # Bind address
                    reply += b'\x00\x00'  # Bind port
                    session.writer.write(reply)
                    await session.writer.drain()
                    
                    # 启动数据转发
                    asyncio.create_task(proxy.forward_data(session))
                    
                elif cmd == 'DATA':
                    session.target_writer.write(data.encode())
                    await session.target_writer.drain()
                    
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
    finally:
        await ws.close()
    return ws

async def forward_data(self, session):
    try:
        while True:
            data = await session.target_reader.read(4096)
            if not data:
                break
            await session.ws.send_str(f"{session.conn_id}|DATA|{data.decode()}")
    except Exception as e:
        logger.error(f"Forward data error: {str(e)}")
    finally:
        session.target_writer.close()

async def init_app():
    app = web.Application()
    socks_server = await asyncio.start_server(
        server.handle_client, 
        '0.0.0.0', 
        1080,
        reuse_port=True
    )
    async with socks_server:
        await socks_server.serve_forever()

    app.add_routes([web.get('/ws', websocket_handler)])
    return app

if __name__ == '__main__':
    app = asyncio.run(init_app())
    web.run_app(app, port=8080)