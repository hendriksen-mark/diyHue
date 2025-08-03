from ws4py.server.cherrypyserver import WebSocketPlugin, WebSocketTool
from ws4py.websocket import WebSocket
import cherrypy
import threading
import time
import logManager
import configManager

logging = logManager.logger.get_logger(__name__)
bridgeConfig = configManager.bridgeConfig.yaml_config

LOG_FILE = logManager.logger._get_log_file_path()

# Global variable to track server state
_server_running: bool = False

class LogWebSocketHandler(WebSocket):
    def opened(self) -> None:
        self._running: bool = True
        self._thread: threading.Thread = threading.Thread(target=self.tail_log)
        self._thread.daemon = True
        self._thread.start()

    def closed(self, code: int, reason: str = None) -> None:
        self._running = False

    def tail_log(self) -> None:
        try:
            with open(LOG_FILE) as f:
                f.seek(0, 2)
                while self._running:
                    line: str = f.readline()
                    if line:
                        try:
                            self.send(line)
                        except Exception as e:
                            logging.error(f"Error sending log line: {e}")
                            break
                    else:
                        time.sleep(0.5)
        except Exception as e:
            logging.error(f"Error tailing log file: {e}")

cherrypy.config.update({'server.socket_host': '0.0.0.0', 'server.socket_port': 9000})
WebSocketPlugin(cherrypy.engine).subscribe()
cherrypy.tools.websocket = WebSocketTool()

class Root(object):
    @cherrypy.expose
    def index(self) -> str:
        return "WebSocket log server running."

    @cherrypy.expose
    def ws(self) -> None:
        pass  # ws4py handles this

def start_ws_server() -> None:
    global _server_running
    try:
        cherrypy.log.screen = False
        cherrypy.engine.autoreload.unsubscribe()

        # Check if port is available
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex(('0.0.0.0', 9000))
        sock.close()

        if result == 0:
            logging.warning("Port 9000 appears to be already in use")
            raise RuntimeError("Port 9000 is already in use. Please stop the service using this port before starting the WebSocket server.")

        _server_running = True

        # This is a blocking call - the server runs here
        cherrypy.quickstart(Root(), '/', config={
            '/ws': {
                'tools.websocket.on': True,
                'tools.websocket.handler_cls': LogWebSocketHandler
            }
        })
    except Exception as e:
        logging.error(f"Failed to start CherryPy WebSocket server: {e}")
        logging.exception("Full traceback:")
        raise
    finally:
        _server_running = False

def stop_ws_server() -> None:
    """
    Gracefully stop the CherryPy WebSocket server.
    """
    global _server_running
    try:
        if _server_running:
            logging.info("Stopping CherryPy WebSocket server...")
            cherrypy.engine.exit()
            _server_running = False
            logging.info("CherryPy WebSocket server stopped.")
        else:
            logging.info("CherryPy WebSocket server is not running.")
    except Exception as e:
        logging.error(f"Error stopping CherryPy WebSocket server: {e}")
        logging.exception("Full traceback:")

def is_server_running() -> bool:
    """
    Check if the WebSocket server is currently running.
    
    Returns:
        bool: True if server is running, False otherwise
    """
    return _server_running
