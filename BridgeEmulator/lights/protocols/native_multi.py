import json
import logManager
import requests
from typing import List, Any

logging = logManager.logger.get_logger(__name__)

def set_light(light, data: dict[str, Any]) -> str:
    """
    Set the state of a light.

    Args:
        light : The light object containing protocol configuration.
        data (dict[str, Any]): The data to set the light state.

    Returns:
        str: The response text or error message.
    """
    lightsData = data.get("lights", {light.protocol_cfg["light_nr"]: data})
    try:
        response = requests.put(f"http://{light.protocol_cfg['ip']}/state", json=lightsData, timeout=3)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        logging.error(f"Failed to set light state: {e}")
        return str(e)

def get_light_state(light) -> dict[str, Any]:
    """
    Get the state of a light.

    Args:
        light : The light object containing protocol configuration.

    Returns:
        dict[str, Any]: The current state of the light.
    """
    try:
        response = requests.get(f"http://{light.protocol_cfg['ip']}/state?light={light.protocol_cfg['light_nr']}", timeout=3)
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        logging.error(f"Failed to get light state: {e}")
        return {}

def generate_light_name(base_name: str, light_nr: int) -> str:
    """
    Generate a light name based on the base name and light number.

    Args:
        base_name (str): The base name of the light.
        light_nr (int): The light number.

    Returns:
        str: The generated light name.
    """
    suffix = f' {light_nr}'
    return f'{base_name[:32-len(suffix)]}{suffix}'

def is_json(content: str) -> bool:
    """
    Check if the content is valid JSON.

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

def discover(detectedLights: List[dict[str, Any]], device_ips: List[str]) -> List[dict[str, Any]]:
    """
    Discover lights on the network.

    Args:
        detectedLights (List[dict[str, Any]]): The list to append detected lights.
        device_ips (List[str]): The list of device IPs to discover.

    Returns:
        List[dict[str, Any]]: The updated list of detected lights.
    """
    logging.debug("native: <discover> invoked!")
    for ip in device_ips:
        try:
            response = requests.get(f"http://{ip}/detect", timeout=3)
            response.raise_for_status()
            if response.content and is_json(response.content):  # Check if response content is valid JSON
                device_data = response.json()
                logging.debug(json.dumps(device_data))

                if "modelid" in device_data:
                    logging.info(f"{ip} is {device_data['name']}")
                    protocol = device_data.get("protocol", "native")
                    lights = device_data.get("lights", 1)

                    logging.info(f"Detected light : {device_data['name']}")
                    for x in range(1, lights + 1):
                        lightName = generate_light_name(device_data['name'], x)
                        protocol_cfg = {
                            "ip": ip,
                            "version": device_data["version"],
                            "type": device_data["type"],
                            "light_nr": x,
                            "mac": device_data["mac"]
                        }
                        if device_data["modelid"] in ["LCX002", "915005987201", "LCX004", "LCX006"]:
                            protocol_cfg["points_capable"] = 5
                        detectedLights.append({
                            "protocol": protocol,
                            "name": lightName,
                            "modelid": device_data["modelid"],
                            "protocol_cfg": protocol_cfg
                        })
            else:
                logging.info(f"ip {ip} returned empty or invalid JSON response")

        except requests.RequestException as e:
            logging.info(f"ip {ip} is unknown device: {e}")

    return detectedLights
