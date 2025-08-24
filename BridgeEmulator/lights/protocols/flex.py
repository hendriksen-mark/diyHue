import json
import logManager
import socket
from functions.colors import convert_xy, rgbBrightness
from typing import Any

logging = logManager.logger.get_logger(__name__)

def pretty_json(data: dict[str, Any]) -> str:
    """
    Convert a dictionary to a pretty-printed JSON string.

    args:
        data: The dictionary to convert.

    returns:
        A pretty-printed JSON string.
    """
    return json.dumps(data, sort_keys=True, indent=4, separators=(',', ': '))

def send_udp_message(msg: bytearray, ip: str, port: int = 48899) -> None:
    """
    Send a UDP message to a specified IP and port.

    args:
        msg: The message to send as a bytearray.
        ip: The IP address to send the message to.
        port: The port to send the message to (default is 48899).
    """
    checksum = sum(msg) & 0xFF
    msg.append(checksum)
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)  # UDP
        sock.sendto(msg, (ip, port))
    except socket.error as e:
        logging.error(f"Failed to send UDP message: {e}")
    finally:
        sock.close()

def set_light(light, data: dict[str, Any]) -> None:
    """
    Set the light state based on the provided data.

    args:
        light: The light object to control.
        data: The data dictionary containing light state information.
    """
    if "on" in data:
        msg = bytearray([0x71, 0x23, 0x8a, 0x0f]) if data["on"] else bytearray([0x71, 0x24, 0x8a, 0x0f])
        send_udp_message(msg, light.protocol_cfg["ip"])

    if ("bri" in data and light.state["colormode"] == "xy") or "xy" in data:
        logging.info(pretty_json(data))
        bri = data.get("bri", light.state["bri"])
        xy = data.get("xy", light.state["xy"])
        color = rgbBrightness(data["rgb"], bri) if "rgb" in data else convert_xy(xy[0], xy[1], bri)
        msg = bytearray([0x41, color[0], color[1], color[2], 0x00, 0xf0, 0x0f])
        send_udp_message(msg, light.protocol_cfg["ip"])

    elif ("bri" in data and light.state["colormode"] == "ct") or "ct" in data:
        bri = data.get("bri", light.state["bri"])
        msg = bytearray([0x41, 0x00, 0x00, 0x00, bri, 0x0f, 0x0f])
        send_udp_message(msg, light.protocol_cfg["ip"])
