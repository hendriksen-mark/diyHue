import requests
from typing import Any

def set_light(light, data: dict[str, Any]) -> None:
    """
    Set the state of a light.

    Args:
        light: The light object containing protocol configuration.
        data: A dictionary containing the state data to set (e.g., on, bri).
    """
    base_url = f"http://{light.protocol_cfg['ip']}/core/api/jeeApi.php?apikey={light.protocol_cfg['light_api']}&type=cmd&id="
    for key, value in data.items():
        if key == "on":
            url = base_url + (light.protocol_cfg["light_on"] if value else light.protocol_cfg["light_off"])
        elif key == "bri":
            brightness = round(float(value) / 255 * 100)
            url = f"{base_url}{light.protocol_cfg['light_slider']}&slider={brightness}"
        requests.get(url, timeout=3)

def get_light_state(light) -> dict[str, Any]:
    """
    Get the current state of a light.

    Args:
        light: The light object containing protocol configuration.

    Returns:
        A dictionary containing the current state of the light (e.g., on, bri).
    """
    url = f"http://{light.protocol_cfg['ip']}/core/api/jeeApi.php?apikey={light.protocol_cfg['light_api']}&type=cmd&id={light.protocol_cfg['light_id']}"
    response = requests.get(url, timeout=3)
    light_data = response.json()
    state = {
        "on": light_data != 0,
        "bri": str(round(float(light_data) / 100 * 255))
    }
    return state
