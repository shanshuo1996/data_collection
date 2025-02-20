import asyncio
import websockets
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('ProxyClient')

class TunnelClient:
    def __init__(self, server_uri):
        self.server_uri = server_uri
        self.connections = {}
    
    async def run(self):
        async with websockets.connect(self.server_uri) as ws:
            while True:
                try:
                    msg = await ws.recv()
                    if '|CONNECT|' in msg:
                        await self._handle_connect(ws, msg)
                    elif '|DATA|' in msg:
                        await self._handle_data(msg)
                except websockets.ConnectionClosed:
                    logger.error("WebSocket connection closed")
                    break

    async def _handle_connect(self, ws, msg):
        conn_id, _, addr_port = msg.split('|', 2)
        addr, port = addr_port.split(':')
        
        try:
            # 连接真实服务器
            reader, writer = await asyncio.open_connection(addr, int(port))
            self.connections[conn_id] = (reader, writer)
            await ws.send(f"{conn_id}|CONNECT_OK|{addr}:{port}")
            
            # 启动数据转发
            asyncio.create_task(self._forward_to_ws(conn_id, reader, ws))
        except Exception as e:
            await ws.send(f"{conn_id}|CONNECT_ERR|{str(e)}")
            logger.error(f"Connect failed: {str(e)}")

    async def _handle_data(self, msg):
        conn_id, _, data = msg.split('|', 2)
        if conn_id in self.connections:
            writer = self.connections[conn_id][1]
            writer.write(data.encode())
            await writer.drain()

    async def _forward_to_ws(self, conn_id, reader, ws):
        try:
            while True:
                data = await reader.read(4096)
                if not data:
                    break
                await ws.send(f"{conn_id}|DATA|{data.decode()}")
        except Exception as e:
            logger.error(f"Forward error: {str(e)}")
        finally:
            del self.connections[conn_id]

if __name__ == '__main__':
    client = TunnelClient('ws://localhost:8080/ws')
    asyncio.get_event_loop().run_until_complete(client.run())