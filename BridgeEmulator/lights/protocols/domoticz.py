import json
import requests
import logManager
from typing import Optional
from functions.colors import convert_xy, rgbBrightness

logging = logManager.logger.get_logger(__name__)

def build_url(light, command: str, params: str) -> str:
    base_url = f"http://{light.protocol_cfg['ip']}/json.htm?type=command&idx={light.protocol_cfg['domoticzID']}"
    return f"{base_url}&param={command}&{params}"

def send_request(url: str):
    try:
        logging.debug(url)
        response = requests.put(url, timeout=3)
        response.raise_for_status()
    except requests.RequestException as e:
        logging.error(f"Error sending request to {url}: {e}")

def set_light(light, data: dict, rgb: Optional[tuple[int, int, int]] = None) -> None:
    if "on" in data:
        switch_cmd = "On" if data["on"] else "Off"
        url = build_url(light, "switchlight", f"switchcmd={switch_cmd}")
        send_request(url)

    if "ct" in data or "xy" in data or "bri" in data:
        color_data = {}
        if "ct" in data or ("colormode" in light.state and light.state["colormode"] == "ct"):
            ct = data["ct"] if "ct" in data else light.state["ct"]
            color_data["m"] = 2
            ct01 = (ct - 153) / (500 - 153)  # map color temperature from 153-500 to 0-1
            color_data["t"] = ct01 * 255  # map color temperature from 0-1 to 0-255

        if "xy" in data or ("colormode" in light.state and light.state["colormode"] == "xy"):
            xy = data["xy"] if "xy" in data else light.state["xy"]
            bri = data["bri"] if "bri" in data else light.state["bri"]
            color_data["m"] = 3
            if rgb:
                color_data["r"], color_data["g"], color_data["b"] = rgbBrightness(list(rgb), bri)
            else:
                color_data["r"], color_data["g"], color_data["b"] = convert_xy(xy[0], xy[1], bri)

        params = f"setcolbrightnessvalue&color={json.dumps(color_data)}"
        if "bri" in data:
            params += f"&brightness={round(float(data['bri']) / 255 * 100)}"
        url = build_url(light, "setcolbrightnessvalue", params)
        send_request(url)

def get_light_state(light) -> dict:
    try:
        response = requests.get(f"http://{light.protocol_cfg['ip']}/json.htm?type=devices&rid={light.protocol_cfg['domoticzID']}", timeout=3)
        response.raise_for_status()
        light_data = response.json()
    except requests.RequestException as e:
        logging.error(f"Error getting light state: {e}")
        return {}

    state = {"on": light_data["result"][0]["Status"] != "Off"}
    state["bri"] = int(round(float(light_data["result"][0]["Level"]) / 100 * 255))
    return state
