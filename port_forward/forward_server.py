import asyncio
from collections import deque
import time

class TunnelManager:
    def __init__(self):
        self.connections = deque()
        self.max_pool_size = 300
        self.lock = asyncio.Lock()

    async def add_tunnel(self, reader, writer):
        async with self.lock:
            # 清理无效连接
            self.connections = deque([(r,w) for r,w in self.connections if not w.is_closing()])
            
            if len(self.connections) < self.max_pool_size:
                self.connections.append((reader, writer))
                print(f"当前隧道池大小：{len(self.connections)}")
            else:
                writer.close()
                print("连接池已满，拒绝新连接")

    async def get_tunnel(self):
        async with self.lock:
            while len(self.connections) > 0:
                reader, writer = self.connections.popleft()
                if not writer.is_closing():
                    return reader, writer
            raise ConnectionError("没有可用隧道连接")

tunnel_mgr = TunnelManager()

async def handle_tunnel(reader, writer):
    """处理隧道连接"""
    try:
        peername = writer.get_extra_info('peername')
        print(f"新隧道连接来自：{peername}")
        await tunnel_mgr.add_tunnel(reader, writer)
        
        # 保持连接活性并监听数据
        while True:
            await asyncio.sleep(0.1)

            
    except Exception as e:
        print(f"隧道错误：{e}")
    finally:
        writer.close()

async def proxy_handler(reader, writer):
    """处理代理请求"""
    try:
        print("收到新代理请求")
        tunnel_reader, tunnel_writer = await tunnel_mgr.get_tunnel()
        
        # 创建双向管道
        pipe1 = pipe_data(reader, tunnel_writer)
        pipe2 = pipe_data(tunnel_reader, writer)
        await asyncio.gather(pipe1, pipe2)
        
    except Exception as e:
        print(f"代理处理失败：{e}")
    finally:
        writer.close()


async def pipe_data(src_reader, dst_writer, label=""):
    """支持半关闭的数据管道"""
    try:
        while True:
            data = await src_reader.read(4096)
            if not data:
                print(f"{label} 对端关闭写入，发送EOF")
                await dst_writer.drain()
                dst_writer.write_eof()  # 发送EOF而非直接关闭
                break
                
            print(f"{label} 转发 {len(data)} 字节")
            dst_writer.write(data)
            await dst_writer.drain()
            
    except ConnectionResetError:
        print(f"{label} 连接被重置，紧急关闭")
        dst_writer.close()
    except Exception as e:
        print(f"{label} 管道错误: {str(e)}")
    finally:
        # 仅关闭写入方向，保留读取能力
        if dst_writer.can_write_eof():
            dst_writer.write_eof()

async def main():
    # 启动隧道服务器（50000端口）
    tunnel_server = await asyncio.start_server(
        handle_tunnel,
        '0.0.0.0',
        50000,
        reuse_port=True
    )
    
    # 启动代理服务器（1081端口）
    proxy_server = await asyncio.start_server(
        proxy_handler,
        '0.0.0.0',
        1081,
        reuse_port=True
    )
    
    async with tunnel_server, proxy_server:
        print("服务端已在 50000 和 1081 端口启动")
        await asyncio.gather(
            tunnel_server.serve_forever(),
            proxy_server.serve_forever()
        )

if __name__ == '__main__':
    asyncio.run(main())