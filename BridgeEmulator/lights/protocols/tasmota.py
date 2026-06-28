import json
import logManager
import requests
from functions.colors import convert_rgb_xy, convert_xy, rgbBrightness
from typing import List, Any, Union

logging = logManager.logger.get_logger(__name__)

def sendRequest(url: str, timeout: int = 3) -> Union[str, None]:
    """
    Send a GET request to the specified URL with a JSON header.

    Args:
        url (str): The URL to send the request to.
        timeout (int): The timeout for the request in seconds.

    Returns:
        Union[str, None]: The response text if the request was successful, None otherwise.
    """
    head = {"Content-type": "application/json"}
    try:
        response = requests.get(url, timeout=timeout, headers=head)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logging.error(f"Request to {url} failed: {e}")
        return None

def is_json(content: str) -> bool:
    """
    Check if the given content is valid JSON.

    Args:
        content (str): The content to check.

    Returns:
        bool: True if the content is valid JSON, False otherwise.
    """
    try:
        json.loads(content)
    except ValueError:
        return False
    return True

def discover(detectedLights: List[dict[str, Any]], device_ips: List[str]) -> None:
    """
    Discover Tasmota devices on the network.

    Args:
        detectedLights (List[dict[str, Any]]): The list to append detected lights to.
        device_ips (List[str]): The list of device IPs to probe.
    """
    logging.debug("tasmota: <discover> invoked!")
    for ip in device_ips:
        try:
            #logging.debug(f"tasmota: probing ip {ip}")
            response = requests.get(f"http://{ip}/cm?cmnd=Status%200", timeout=3)
            response.raise_for_status()
            if response.content and is_json(response.text):
                device_data = response.json()
                #logging.debug(pretty_json(device_data))
                if "StatusSTS" in device_data:
                    logging.debug(f'tasmota: {ip} is a Tasmota device')
                    logging.debug(f'tasmota: Hostname: {device_data["StatusNET"]["Hostname"]}')
                    logging.debug(f'tasmota: Mac:      {device_data["StatusNET"]["Mac"]}')

                    properties = {"rgb": True, "ct": False, "ip": ip, "name": device_data["StatusNET"]["Hostname"], "id": device_data["StatusNET"]["Mac"], "mac": device_data["StatusNET"]["Mac"]}
                    detectedLights.append({"protocol": "tasmota", "name": device_data["StatusNET"]["Hostname"], "modelid": "LCT015", "protocol_cfg": {"ip": ip, "id": device_data["StatusNET"]["Mac"]}})

        except requests.RequestException as e:
            logging.info(f"ip {ip} is unknown device: {e}")

def set_light(light, data: dict[str, Any], rgb: Union[List[int], None] = None) -> None:
    """
    Set the state of a Tasmota light.

    Args:
        light : The light configuration.
        data (dict[str, Any]): The state data to set.
        rgb (Union[List[int], None]): The RGB values if available.
    """
    for key, value in data.items():
        if key == "on":
            url = f"http://{light.protocol_cfg['ip']}/cm?cmnd=Power%20{'on' if value else 'off'}"
            sendRequest(url)
        elif key == "bri":
            brightness = int(100.0 * (value / 254.0))
            url = f"http://{light.protocol_cfg['ip']}/cm?cmnd=Dimmer%20{brightness}"
            sendRequest(url)
        elif key == "ct":
            color = {}
        elif key == "xy":
            if rgb:
                color = rgbBrightness(rgb, light["state"]["bri"])
            else:
                color = convert_xy(value[0], value[1], light["state"]["bri"])
            url = f"http://{light.protocol_cfg['ip']}/cm?cmnd=Color%20{color[0]},{color[1]},{color[2]}"
            sendRequest(url)
        elif key == "alert":
            if value == "select":
                url = f"http://{light.protocol_cfg['ip']}/cm?cmnd=dimmer%20100"
                sendRequest(url)

def hex_to_rgb(value: str) -> List[int]:
    """
    Convert a hex color string to an RGB list.

    Args:
        value (str): The hex color string.

    Returns:
        List[int]: The RGB values.
    """
    value = value.lstrip('#')
    lv = len(value)
    tup = tuple(int(value[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))
    return list(tup)

def rgb_to_hex(rgb: List[int]) -> str:
    """
    Convert an RGB list to a hex color string.

    Args:
        rgb (List[int]): The RGB values.

    Returns:
        str: The hex color string.
    """
    return '%02x%02x%02x' % tuple(rgb)
    # return '#%02x%02x%02x' % rgb

def get_light_state(light) -> dict[str, Any]:
    """
    Get the current state of a Tasmota light.

    Args:
        light : The light configuration.

    Returns:
        dict[str, Any]: The current state of the light.
    """
    data = sendRequest(f"http://{light.protocol_cfg['ip']}/cm?cmnd=Status%2011")
    if not data:
        return {}
    light_data = json.loads(data)["StatusSTS"]
    state = {}

    if 'POWER' in light_data:
        state['on'] = True if light_data["POWER"] == "ON" else False
    elif 'POWER1' in light_data:
        state['on'] = True if light_data["POWER1"] == "ON" else False

    if 'Color' not in light_data:
        if state['on']:
            state["xy"] = convert_rgb_xy(255, 255, 255)
            state["bri"] = int(255)
            state["colormode"] = "xy"
    else:
        if "," in light_data["Color"]:
            rgb = light_data["Color"].split(",")
            state["xy"] = convert_rgb_xy(int(rgb[0], 16), int(rgb[1], 16), int(rgb[2], 16))
        else:
            hex = light_data["Color"]
            rgb = hex_to_rgb(hex)
            state["xy"] = convert_rgb_xy(rgb[0], rgb[1], rgb[2])

        state["bri"] = int(light_data["Dimmer"] / 100.0 * 254.0)
        state["colormode"] = "xy"

    return state
