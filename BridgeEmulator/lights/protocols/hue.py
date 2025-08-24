import logManager
import requests
from typing import Any, List, Optional

logging = logManager.logger.get_logger(__name__)

def build_url(light, endpoint: str = "state") -> str:
    """
    Build the URL for the Hue light API.

    Args:
        light: The light object.
        endpoint (str): The API endpoint to access. Defaults to "state".

    Returns:
        str: The constructed URL.
    """
    return f"http://{light.protocol_cfg['ip']}/api/{light.protocol_cfg['hueUser']}/lights/{light.protocol_cfg['id']}/{endpoint}"

def set_light(light, data: dict[str, Any]) -> None:
    """
    Set the state of the light.

    Args:
        light: The light object.
        data (dict[str, Any]): The data to set on the light.
    """
    url = build_url(light)
    payload = {}
    payload.update(data)
    color = {}
    if "xy" in payload:
        color["xy"] = payload["xy"]
        del payload["xy"]
    elif "ct" in payload:
        color["ct"] = payload["ct"]
        del payload["ct"]
    elif "hue" in payload:
        color["hue"] = payload["hue"]
        del payload["hue"]
    elif "sat" in payload:
        color["sat"] = payload["sat"]
        del payload["sat"]
    if payload:
        requests.put(url, json=payload, timeout=3)
    if color:
        requests.put(url, json=color, timeout=3)

def get_light_state(light) -> Optional[dict[str, Any]]:
    """
    Get the current state of the light.

    Args:
        light: The light object.

    Returns:
        Optional[dict[str, Any]]: The state of the light, or None if an error occurred.
    """
    try:
        state = requests.get(build_url(light, ""), timeout=3)
        state.raise_for_status()
        return state.json().get("state")
    except requests.RequestException as e:
        logging.error("Error getting light state: %s", e)
        return None

def discover(detectedLights: List[dict[str, Any]], credentials: dict[str, str]) -> None:
    """
    Discover Hue lights and add them to the detectedLights list.

    Args:
        detectedLights (List[dict[str, Any]]): The list to append discovered lights to.
        credentials (dict[str, str]): The credentials for accessing the Hue Bridge.
    """
    if "hueUser" in credentials and len(credentials["hueUser"]) >= 32:
        logging.debug("hue: <discover> invoked!")
        try:
            response = requests.get(f"http://{credentials['ip']}/api/{credentials['hueUser']}/lights", timeout=3)
            response.raise_for_status()
            lights = response.json()
            for id, light in lights.items():
                modelid = "LCT015"
                if light["modelid"].startswith("LWB"):#Dimmable light
                    modelid = "LWB010"
                elif light["modelid"].startswith("LTW"):#Color temperature light
                    modelid = "LTW001"
                elif light["modelid"].startswith("LOM"):#On/Off plug-in unit
                    modelid = "LOM001"
                elif light["modelid"].startswith("LLC"):#Color light
                    modelid = "LLC010"
                elif light["modelid"].startswith("LCX"):#Extended color light
                    modelid = "LCX002"
                elif light["modelid"].startswith("LCA"):#Color temperature light
                    modelid = "LCA005"
                elif light["modelid"].startswith("LST"):#Lightstrip Plus
                    modelid = "LST002"
                detectedLights.append({
                    "protocol": "hue", 
                    "name": light["name"], 
                    "modelid": modelid, 
                    "protocol_cfg": {
                        "ip": credentials["ip"], 
                        "hueUser": credentials["hueUser"], 
                        "modelid": light["modelid"], 
                        "id": id, 
                        "uniqueid": light["uniqueid"],
                        **({"points_capable": 5} if modelid == "LCX002" else {})
                    }
                })
        except requests.RequestException as e:
            logging.error("Error connecting to Hue Bridge: %s", e)
