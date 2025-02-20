import socket
import threading

def forward_data(source, destination):
    while True:
        try:
            data = source.recv(4096)
            if not data:
                break
            destination.sendall(data)
        except:
            break
    source.close()
    destination.close()

def handle_client(client_socket, target_host, target_port):
    try:
        remote_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        remote_socket.connect((target_host, target_port))
        
        # 启动双向数据转发线程
        threads = [
            threading.Thread(target=forward_data, args=(client_socket, remote_socket)),
            threading.Thread(target=forward_data, args=(remote_socket, client_socket))
        ]
        
        for t in threads:
            t.start()
            
        for t in threads:
            t.join()
            
    except Exception as e:
        print(f"Connection error: {e}")
        client_socket.close()

def start_proxy(local_host, local_port, remote_host, remote_port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind((local_host, local_port))
    server.listen(5)
    print(f"Proxy listening on {local_host}:{local_port}")
    
    while True:
        client_socket, addr = server.accept()
        print(f"Accepted connection from {addr[0]}:{addr[1]}")
        proxy_thread = threading.Thread(
            target=handle_client,
            args=(client_socket, remote_host, remote_port)
        )
        proxy_thread.start()

if __name__ == "__main__":
    # 配置示例：将本机8080端口转发到example.com的80端口
    start_proxy('127.0.0.1', 8080, '127.0.0.1', 80)