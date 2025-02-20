import asyncio
import socket
from enum import IntEnum

class Socks5Server:
    class AuthMethod(IntEnum):
        NO_AUTH = 0x00
        GSSAPI = 0x01
        USER_PASS = 0x02
    
    class AddressType(IntEnum):
        IPV4 = 0x01
        DOMAIN = 0x03
        IPV6 = 0x04
    
    class Command(IntEnum):
        CONNECT = 0x01
        BIND = 0x02
        UDP_ASSOCIATE = 0x03
    
    class ReplyCode(IntEnum):
        SUCCESS = 0x00
        GENERAL_FAILURE = 0x01
        CONN_NOT_ALLOWED = 0x02
        NETWORK_UNREACHABLE = 0x03
        HOST_UNREACHABLE = 0x04
        CONN_REFUSED = 0x05
        TTL_EXPIRED = 0x06
        CMD_NOT_SUPPORTED = 0x07
        ADDR_TYPE_NOT_SUPPORTED = 0x08

    async def handle_client(self, reader, writer):
        try:
            # ===== 阶段1：方法协商 =====
            version, nmethods = await self._read_method_negotiation(reader)
            await self._send_method_selection(writer)
            
            # ===== 阶段2：请求处理 ===== 
            ver, cmd, rsv, atyp = await self._read_request_header(reader)
            addr, port = await self._parse_address(reader, atyp)
            
            # ===== 建立真实连接 =====
            target_reader, target_writer = await self._connect_target(addr, port)
            
            # ===== 返回响应 =====
            await self._send_success_response(writer, atyp, addr, port)
            
            # ===== 数据转发 =====
            await self._relay_data(reader, writer, target_reader, target_writer)
            
        except (asyncio.IncompleteReadError, asyncio.TimeoutError) as e:
            await self.send_error_response(writer)  # 新增统一错误处理
        except Exception as e:
            print(f"Client error: {e}")
        finally:
            writer.close()

            
    async def send_error_response(self, writer):
        """统一错误响应方法"""
        try:
            error_packet = bytes([0x05, 0x01])  # 通用错误代码
            writer.write(error_packet)
            await writer.drain()
        except:
            pass

    async def _read_method_negotiation(self, reader):
        data = await reader.readexactly(2)
        version, nmethods = data
        print(f"Received method negotiation: {version}, {nmethods}")
        if version != 0x05:
            raise ValueError("Invalid SOCKS version")
        methods = await reader.readexactly(nmethods)
        print(f"Supported methods: {methods}")
        return version, methods

    async def _send_method_selection(self, writer):
        print("Sending method selection 0x05 0x00")
        writer.write(bytes([0x05, self.AuthMethod.NO_AUTH]))
        await writer.drain()

    async def _read_request_header(self, reader):
        header = await reader.readexactly(4)
        print("Received request header:", header)
        return header[0], header[1], header[2], header[3]

    async def _parse_address(self, reader, atyp):
        print("Parsing address")
        if atyp == self.AddressType.IPV4:
            print("IPv4 address")
            addr_bytes = await reader.readexactly(4)
            addr = socket.inet_ntop(socket.AF_INET, addr_bytes)
        elif atyp == self.AddressType.DOMAIN:
            print("Domain address")
            length = ord(await reader.readexactly(1))
            addr = (await reader.readexactly(length)).decode()
        elif atyp == self.AddressType.IPV6:
            print("IPv6 address")
            addr_bytes = await reader.readexactly(16)
            addr = socket.inet_ntop(socket.AF_INET6, addr_bytes)
        else:
            raise ValueError("Unsupported address type")
        
        port = int.from_bytes(await reader.readexactly(2), 'big')
        return addr, port

    async def _connect_target(self, addr, port):
        print(f"Connecting to target: {addr}:{port}")
        try:
            return await asyncio.open_connection(addr, port)
        except OSError as e:
            raise ConnectionError(f"Connect failed: {str(e)}")

    async def _send_success_response(self, writer, atyp, addr, port):
        response = bytearray()
        response += bytes([0x05, self.ReplyCode.SUCCESS, 0x00, atyp])
        print(f"Sending success response: {addr}:{port}")
        
        if atyp == self.AddressType.IPV4:
            response += socket.inet_aton(addr)
        elif atyp == self.AddressType.IPV6:
            response += socket.inet_pton(socket.AF_INET6, addr)
        else:
            response += bytes([len(addr)]) + addr.encode()
            
        response += port.to_bytes(2, 'big')
        writer.write(response)
        await writer.drain()

    async def _relay_data(self, client_reader, client_writer, target_reader, target_writer):
        tasks = [
            self._pipe(client_reader, target_writer),
            self._pipe(target_reader, client_writer)
        ]
        await asyncio.gather(*tasks)

    async def _pipe(self, reader, writer):
        try:
            while True:
                data = await reader.read(4096)
                print(f"Received {len(data)} bytes:{data}")
                if not data:
                    break
                writer.write(data)
                await writer.drain()
        finally:
            writer.close()

    async def listen(self, host, port):
        server = await asyncio.start_server(
            self.handle_client, host, port, reuse_port=True
        )
        
        async with server:
            await server.serve_forever()


async def main():
    server = Socks5Server()
    await server.listen('0.0.0.0', 1080)

if __name__ == '__main__':
    asyncio.run(main())