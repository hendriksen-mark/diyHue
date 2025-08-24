import json
import socket
import logManager
from functions.colors import convert_xy, hsv_to_rgb
from typing import Any

logging = logManager.logger.get_logger(__name__)

def set_light(light: Any, data: dict[str, Any]) -> None:
    """
    Set the light state based on the provided data.

    Args:
        light (Any): The light object containing protocol configuration and state.
        data (dict[str, Any]): The data dictionary containing light state parameters.
    """
    ip = light.protocol_cfg["ip"]
    payload = {}
    transitiontime = 400
    if "transitiontime" in data:
        transitiontime = int(data["transitiontime"] * 100)
    for key, value in data.items():
        if key == "on":
            payload["state"] = value
        elif key == "bri":
            payload["dimming"] = int(value / 2.83) + 10
        elif key == "ct":
            payload["temp"] = round(translateRange(value, 153, 500, 6500, 2700))
        elif key == "hue":
            rgb = hsv_to_rgb(value, light.state["sat"], light.state["bri"])
            payload["r"] = rgb[0]
            payload["g"] = rgb[1]
            payload["b"] = rgb[2]
        elif key == "sat":
            rgb = hsv_to_rgb(light.state["hue"], value, light.state["bri"])
            payload["r"] = rgb[0]
            payload["g"] = rgb[1]
            payload["b"] = rgb[2]
        elif key == "xy":
            rgb = convert_xy(value[0], value[1], light.state["bri"])
            payload["r"] = rgb[0]
            payload["g"] = rgb[1]
            payload["b"] = rgb[2]
        elif key == "alert" and value != "none":
            payload["dimming"] = 100
    logging.debug(json.dumps({"method": "setPilot", "params": payload}))
    udpmsg = bytes(json.dumps({"method": "setPilot", "params": payload}), "utf8")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM) # UDP
    sock.sendto(udpmsg, (ip, 38899))

def translateRange(value: float, leftMin: float, leftMax: float, rightMin: float, rightMax: float) -> float:
    """
    Translate a value from one range to another.

    Args:
        value (float): The value to translate.
        leftMin (float): The minimum value of the original range.
        leftMax (float): The maximum value of the original range.
        rightMin (float): The minimum value of the target range.
        rightMax (float): The maximum value of the target range.

    Returns:
        float: The translated value in the target range.
    """
    leftSpan = leftMax - leftMin
    rightSpan = rightMax - rightMin
    valueScaled = float(value - leftMin) / float(leftSpan)
    return rightMin + (valueScaled * rightSpan)
