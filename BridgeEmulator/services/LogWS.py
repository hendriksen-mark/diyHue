import socket
import threading
import base64
import hashlib
import time
from pathlib import Path
import logManager

logging = logManager.logger.get_logger(__name__)

LOG_FILE = str(Path(__file__).parent.parent / "diyhue.log")

class WebSocketServer:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.clients = []

    def start(self):
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((self.host, self.port))
        server_socket.listen(5)
        logging.info(f"WebSocket server running on ws://{self.host}:{self.port}")

        while True:
            client_socket, address = server_socket.accept()
            logging.info(f"Connection from {address}")
            threading.Thread(target=self.handle_client, args=(client_socket,)).start()

    def handle_client(self, client_socket):
        try:
            self.handshake(client_socket)
            self.clients.append(client_socket)
            self.stream_logs(client_socket)
        except Exception as e:
            logging.error(f"Error handling client: {e}")
        finally:
            self.clients.remove(client_socket)
            client_socket.close()

    def handshake(self, client_socket):
        request = client_socket.recv(1024).decode('utf-8')
        headers = self.parse_headers(request)
        key = headers.get("Sec-WebSocket-Key")
        if not key:
            raise ValueError("Missing Sec-WebSocket-Key in headers")

        accept_key = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode('utf-8')
        response = (
            "HTTP/1.1 101 Switching Protocols\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Accept: {accept_key}\r\n\r\n"
        )
        client_socket.send(response.encode('utf-8'))

    def parse_headers(self, request):
        headers = {}
        for line in request.split("\r\n")[1:]:
            if ": " in line:
                key, value = line.split(": ", 1)
                headers[key] = value
        return headers

    def stream_logs(self, client_socket):
        with open(LOG_FILE) as f:
            f.seek(0, 2)
            while True:
                line = f.readline()
                if line:
                    self.send_message(client_socket, line)
                else:
                    time.sleep(0.5)

    def send_message(self, client_socket, message):
        try:
            message = message.encode('utf-8')
            length = len(message)
            if length <= 125:
                frame = b"\x81" + bytes([length]) + message
            elif length <= 65535:
                frame = b"\x81\x7e" + length.to_bytes(2, 'big') + message
            else:
                frame = b"\x81\x7f" + length.to_bytes(8, 'big') + message
            client_socket.send(frame)
        except Exception as e:
            logging.error(f"Error sending message: {e}")
            raise

def start_websocket_server():
    server = WebSocketServer('0.0.0.0', 9000)
    try:
        server.start()
    except KeyboardInterrupt:
        logging.info("Shutting down WebSocket server.")
