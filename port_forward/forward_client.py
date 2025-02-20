import asyncio
from socks5_server.socks5Server import Socks5Server

class TunnelManager:
    def __init__(self):
        self.active_connections = {}
        self.lock = asyncio.Lock()
    
    async def add_connection(self, tunnel_reader, tunnel_writer, local_reader, local_writer):
        """注册完整的双向连接"""
        async with self.lock:
            conn_id = id(tunnel_writer)
            self.active_connections[conn_id] = {
                'tunnel': (tunnel_reader, tunnel_writer),
                'local': (local_reader, local_writer),
                'tasks': []
            }
            return conn_id
    
    async def remove_connection(self, conn_id):
        """清理连接资源"""
        async with self.lock:
            if conn_id in self.active_connections:
                # 关闭所有writer
                for side in ['tunnel', 'local']:
                    writer = self.active_connections[conn_id][side][1]
                    if not writer.is_closing():
                        writer.close()
                        await writer.wait_closed()
                
                # 取消所有任务
                for task in self.active_connections[conn_id]['tasks']:
                    task.cancel()
                
                del self.active_connections[conn_id]

tunnel_mgr = TunnelManager()

async def bridge_traffic(tunnel_reader, tunnel_writer, local_reader, local_writer):
    """建立双向数据桥接"""
    try:
        # 创建转发任务
        task1 = asyncio.create_task(pipe_data(tunnel_reader, local_writer, "Tunnel->Local"))
        task2 = asyncio.create_task(pipe_data(local_reader, tunnel_writer, "Local->Tunnel"))
        
        # 注册任务到连接管理器
        conn_id = await tunnel_mgr.add_connection(tunnel_reader, tunnel_writer, local_reader, local_writer)
        print(f"新连接注册成功（ID: {conn_id}）")
        tunnel_mgr.active_connections[conn_id]['tasks'].extend([task1, task2])
        
        # 等待任意任务完成
        done, pending = await asyncio.wait(
            [task1, task2],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        print(f"连接中断，清理资源（ID: {conn_id}）")
        
    except Exception as e:
        print(f"数据桥接异常: {str(e)}")
    finally:
        await tunnel_mgr.remove_connection(conn_id)

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

            
async def maintain_tunnel(server_ip):
    """维护隧道连接（带自动恢复）"""
    retry_interval = 1
    while True:
        try:
            # 连接隧道服务器
            tunnel_reader, tunnel_writer = await asyncio.open_connection(server_ip, 50000)
            print(f"隧道连接成功: {server_ip}:50000")
            
            # 连接本地SOCKS5
            local_reader, local_writer = await asyncio.open_connection('127.0.0.1', 1080)
            
            # 启动数据桥接
            await bridge_traffic(tunnel_reader, tunnel_writer, local_reader, local_writer)
            
            retry_interval = 1  # 重置重试间隔
            
        except (ConnectionRefusedError, asyncio.TimeoutError) as e:
            print(f"连接失败: {str(e)}, {retry_interval}s后重试...")
            await asyncio.sleep(retry_interval)
            retry_interval = min(retry_interval * 2, 60)  # 指数退避
        except Exception as e:
            print(f"隧道维护异常: {str(e)}")
            await asyncio.sleep(5)

async def main():
    # 启动SOCKS5服务器
    socks_server = Socks5Server()
    server_task = asyncio.create_task(socks_server.listen('0.0.0.0', 1080))
    
    # 启动隧道维护
    tunnel_task = asyncio.create_task(maintain_tunnel('127.0.0.1'))  # 替换真实IP
    
    await asyncio.gather(server_task, tunnel_task)

if __name__ == '__main__':
    asyncio.run(main())