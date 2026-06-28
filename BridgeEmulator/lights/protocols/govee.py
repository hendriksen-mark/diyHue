import json
import logManager
from functions.colors import convert_rgb_xy, convert_xy, hsv_to_rgb
from typing import List, Any, Generator, Tuple, Optional
import socket
import struct
import base64

logging = logManager.logger.get_logger(__name__)

MULTICAST_GROUP = '239.255.255.250'
DISCOVER_PORT, RECEIVE_PORT, CMD_PORT = 4001, 4002, 4003
DISCOVER_MESSAGE = {"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}}
DEV_MESSAGE = {"msg": {"cmd": "devStatus", "data": {}}}
CMD_MESSAGE = {"msg": {"cmd": "status", "data": {}}}
BRI_MESSAGE = {"msg": {"cmd": "brightness", "data": {"value": 0}}}
ON_OFF_MESSAGE = {"msg": {"cmd": "turn", "data": {"value": 0}}}
COLOR_MESSAGE = {"msg": {"cmd": "colorwc", "data": {"color": {"r": 0, "g": 0, "b": 0}}}}
SEG_MESSAGE = {"msg": {"cmd": "razer", "data": {"pt": ""}}}
TIMEOUT_MSG = 'Timed out, no more responses'
FAILED_STATUS_MSG = 'Failed to get status from'

responded_devices = []

def is_json(content: str) -> bool:
    """
    Check if the content is valid JSON.

    Args:
        content (str): The string content to validate.

    Returns:
        bool: True if the content is valid JSON, False otherwise.
    """
    try:
        json.loads(content)
        return True
    except ValueError:
        return False

def save_scan_results(ip: str, data: dict) -> None:
    """
    Save scan results to the global responded_devices list.

    Args:
        ip (str): The IP address of the device.
        data (dict): The data received from the device.
    """
    responded_devices.append({ip: data["msg"]["data"]})

def receive_responses(sock: socket.socket, ip: str, is_multicast: bool) -> bool:
    """
    Receive responses from the socket and process them.

    Args:
        sock (socket.socket): The socket to receive data from.
        ip (str): The IP address to associate with responses.
        is_multicast (bool): Whether the communication is multicast.

    Returns:
        bool: True if responses were received, False otherwise.
    """
    responses_received = False
    while True:
        try:
            data, server = sock.recvfrom(1024)
            save_scan_results(server[0] if is_multicast else ip, json.loads(data.decode()))
            responses_received = True
            if not is_multicast:
                return True
        except socket.timeout:
            if is_multicast:
                logging.warning(TIMEOUT_MSG)
            break
        except json.JSONDecodeError:
            pass
    return responses_received

def send_and_receive(sock: socket.socket, message: dict, ip: str, port: int, is_multicast: bool = False) -> bool:
    """
    Send a message and wait for responses.

    Args:
        sock (socket.socket): The socket to use for sending and receiving.
        message (dict): The message to send.
        ip (str): The target IP address.
        port (int): The target port number.
        is_multicast (bool, optional): Whether the message is multicast. Defaults to False.

    Returns:
        bool: True if responses were received, False otherwise.
    """
    if is_multicast:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, struct.pack('b', 1))
    try:
        sock.sendto(json.dumps(message).encode(), (ip, port))
        return receive_responses(sock, ip, is_multicast)
    except socket.error:
        return False

def create_socket(timeout: float, reuse: bool = False) -> socket.socket:
    """
    Create or reuse a UDP socket with the specified timeout.

    Args:
        timeout (float): The timeout value for the socket in seconds.
        reuse (bool, optional): Whether to reuse an existing socket. Defaults to False.

    Returns:
        socket.socket: The created or reused socket.
    """
    global shared_socket
    if reuse and 'shared_socket' in globals() and shared_socket:
        shared_socket.settimeout(timeout)
        return shared_socket

    shared_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    shared_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    shared_socket.settimeout(timeout)
    shared_socket.bind(('0.0.0.0', RECEIVE_PORT))
    return shared_socket

def close_shared_socket() -> None:
    """
    Close the shared socket if it exists.
    """
    global shared_socket
    if 'shared_socket' in globals() and shared_socket:
        shared_socket.close()
        shared_socket = None

def scan(ip: str = MULTICAST_GROUP, port: int = DISCOVER_PORT, timeout: float = 5) -> int:
    """
    Scan for devices using multicast or unicast.

    Args:
        ip (str, optional): The IP address to scan. Defaults to MULTICAST_GROUP.
        port (int, optional): The port to scan. Defaults to DISCOVER_PORT.
        timeout (float, optional): The timeout for the scan in seconds. Defaults to 5.

    Returns:
        int: 0 if devices were found, 1 otherwise.
    """
    sock = create_socket(timeout)
    return 0 if send_and_receive(sock, DISCOVER_MESSAGE, ip, port, ip == MULTICAST_GROUP) else 1

def generate_ips(port: int) -> Generator[Tuple[str, int], None, None]:
    """
    Generate IP addresses within the specified range.

    Args:
        port (int): The port to associate with generated IPs.

    Yields:
        Tuple[str, int]: A tuple containing an IP address and the port.
    """
    import configManager
    bridgeConfig = configManager.bridgeConfig.yaml_config
    rangeConfig = bridgeConfig["config"]["IP_RANGE"]
    HOST_IP = configManager.runtimeConfig.arg["HOST_IP"]
    ip_range_start = rangeConfig["IP_RANGE_START"]
    ip_range_end = rangeConfig["IP_RANGE_END"]
    sub_ip_range_start = rangeConfig["SUB_IP_RANGE_START"]
    sub_ip_range_end = rangeConfig["SUB_IP_RANGE_END"]
    host = HOST_IP.split('.')
    for sub_addr in range(sub_ip_range_start, sub_ip_range_end + 1):
        host[2] = str(sub_addr)
        for addr in range(ip_range_start, ip_range_end + 1):
            host[3] = str(addr)
            if (test_host := '.'.join(host)) != HOST_IP:
                yield (test_host, port)

def find_hosts(port: int = DISCOVER_PORT) -> List[str]:
    """
    Find hosts on the specified port by scanning IP ranges.

    Args:
        port (int, optional): The port to scan. Defaults to DISCOVER_PORT.

    Returns:
        List[str]: A list of found hosts in the format "IP:port".
    """
    return [
        f'{host}:{port}' for host, port in generate_ips(port)
        if scan(host, port, 0.02) == 0
    ]

def discover(detectedLights: List[dict[str, Any]]) -> None:
    """
    Discover Govee lights and append them to the detectedLights list.

    Args:
        detectedLights (List[dict[str, Any]]): The list to append discovered lights to.
    """
    logging.debug("Govee: <discover> invoked!")
    global responded_devices
    responded_devices = []  # Reset the list
    
    if scan() != 0:
        find_hosts()
    
    for device in responded_devices:
        try:
            ip = list(device.keys())[0]
            data = device[ip]
            if data and is_json(json.dumps(data)):
                detectedLights.append(create_light_entry(data))
        except (IndexError, KeyError):
            pass

def create_light_entry(device: dict[str, Any]) -> dict[str, Any]:
    """
    Create a light entry for a Govee device.

    Args:
        device (dict[str, Any]): The device information.

    Returns:
        dict[str, Any]: A dictionary representing the light entry.
    """
    return {
        "protocol": "govee",
        "name": device.get("deviceName", f'{device["sku"]}-{device["device"].replace(":","")[10:]}'),
        "modelid": "LCX002",
        "protocol_cfg": {
            "ip": device["ip"],
            "points_capable": 5,
            "device_id": device["device"],
            "sku_model": device["sku"],
            "bri_range": {
                "min": 1,
                "max": 100,
                "precision": 1
            }
        }
    }

def set_light(light, data: dict[str, Any]) -> None:
    """
    Set the state of a Govee light.

    Args:
        light: The light object containing protocol configuration.
        data (dict[str, Any]): The data containing state information to set.
    """
    ip = light.protocol_cfg["ip"]
    try:
        sock = create_socket(timeout=0.01, reuse=True)  # Reuse the socket
        for data_type in data:
            request_data = create_request_data(light, data, data_type)
            if request_data is not None:
                try:
                    send_and_receive(sock, request_data, ip, CMD_PORT)
                except (socket.timeout, socket.error):
                    pass
    except socket.error:
        pass

def create_request_data(light, data: dict[str, Any], data_type: str) -> Optional[dict[str, Any]]:
    """
    Create the request data for setting the state of a Govee light.

    Args:
        light: The light object containing protocol configuration.
        data (dict[str, Any]): The data containing state information to set.
        data_type (str): The type of data to set (e.g., "on", "bri", "xy").

    Returns:
        Optional[dict[str, Any]]: The request data, or None if the data type is unsupported.
    """
    try:
        request_data = {"msg": {}}

        if data_type == "on":
            request_data["msg"] = create_on_off_capability(data["on"])
            if data["on"] and "gradient" not in data and "gradient" in light.state:
                send_gradient_request(light, light.state)
            return request_data

        elif data_type == "bri":
            request_data["msg"] = create_brightness_capability(data['bri'], light.protocol_cfg.get("bri_range", {}))
            return request_data

        elif data_type == "xy":
            if isinstance(data['xy'], list) and len(data['xy']) == 2:
                r, g, b = convert_xy(data['xy'][0], data['xy'][1], data.get('bri', 255))
                request_data["msg"] = create_color_capability(r, g, b)
            return request_data

        elif data_type == "hue" or data_type == "sat":
            hue = data.get('hue', 0)
            sat = data.get('sat', 0)
            bri = data.get('bri', 255)
            r, g, b = hsv_to_rgb(hue, sat, bri)
            request_data["msg"] = create_color_capability(r, g, b)
            return request_data

        elif data_type == "gradient":
            if "gradient" in data and isinstance(data["gradient"], dict):
                send_gradient_request(light, data)
            return None

        else:
            return None
    except KeyError:
        return None
    except TypeError:
        return None

def send_gradient_request(light, data: dict[str, Any]) -> None:
    """
    Send a gradient request to the Govee light.

    Args:
        light: The light object containing protocol configuration.
        data (dict[str, Any]): The gradient data to send.
    """
    ip = light.protocol_cfg["ip"]
    try:
        sock = create_socket(timeout=0.01, reuse=True)  # Reuse the shared socket
    except Exception:
        return

    SEG_MESSAGE["msg"]["data"]["pt"] = "uwABsQEK"
    sock.sendto(json.dumps(SEG_MESSAGE).encode(), (ip, CMD_PORT))
    gradient_flag = 1
    points = len(data["gradient"]["points"])
    header = [187, 0, 32, 176]
    rgb_values = []

    for point in data["gradient"]["points"]:
        x = point["color"]["xy"]["x"]
        y = point["color"]["xy"]["y"]
        r, g, b = convert_xy(x, y, 255)
        rgb_values.extend([r, g, b])

    byte_array = header + [gradient_flag, points] + rgb_values
    checksum = 0
    for byte in byte_array:
        checksum ^= byte
    byte_array.append(checksum)

    final_send_value = base64.b64encode(bytes(byte_array)).decode()
    SEG_MESSAGE["msg"]["data"]["pt"] = final_send_value

    try:
        sock.sendto(json.dumps(SEG_MESSAGE).encode(), (ip, CMD_PORT))
        sock.recvfrom(1024)  # Ignore response
    except (socket.timeout, socket.error):
        pass

def create_on_off_capability(value: bool) -> dict[str, Any]:
    """
    Create the on/off capability for a Govee light.

    Args:
        value (bool): The on/off value.

    Returns:
        dict[str, Any]: The on/off capability.
    """
    return {
        "cmd": "turn",
        "data": {
            "value": 1 if value else 0
        },
    }

def create_brightness_capability(brightness: int, bri_range: dict[str, Any]) -> dict[str, Any]:
    """
    Create the brightness capability for a Govee light.

    Args:
        brightness (int): The brightness value.
        bri_range (dict[str, Any]): The brightness range configuration.

    Returns:
        dict[str, Any]: The brightness capability.
    """
    mapped_value = round(bri_range.get("min", 0) + ((brightness / 255) * (bri_range.get("max", 100) - bri_range.get("min", 0))),bri_range.get("precision", 0))
    return {
        "cmd": "brightness",
        "data": {
            "value": int(mapped_value)
        }
    }

def create_color_capability(r: int, g: int, b: int) -> dict[str, Any]:
    """
    Create the color capability for a Govee light.

    Args:
        r (int): The red color value.
        g (int): The green color value.
        b (int): The blue color value.

    Returns:
        dict[str, Any]: The color capability.
    """
    return {
        "cmd": "colorwc",
        "data": {
            "color": {
                "r": r,
                "g": g,
                "b": b
            }
        }
    }

def get_light_state(light) -> dict[str, Any]:
    """
    Get the current state of a Govee light.

    Args:
        light: The light object containing protocol configuration.

    Returns:
        dict[str, Any]: The current state of the light, including brightness and on/off status.
    """
    global responded_devices
    responded_devices = []  # Reset the list
    ip = light.protocol_cfg["ip"]
    sock = create_socket(timeout=5, reuse=True)
    if not send_and_receive(sock, CMD_MESSAGE, ip, CMD_PORT):
        raise Exception("Failed to get status from device")
    state = {}
    for device in responded_devices:
        if ip in device:
            bri_range = light.protocol_cfg.get("bri_range", {})
            state['bri'] = round(
                (device[ip]["brightness"] - bri_range.get("min", 0)) / 
                (bri_range.get("max", 100) - bri_range.get("min", 0)) * 255
            )
            state["on"] = bool(device[ip]["onOff"])
            break
    return state

# Ensure the shared socket is closed when the program exits
import atexit
atexit.register(close_shared_socket)
