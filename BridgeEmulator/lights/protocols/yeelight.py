import logManager
import yeelight
from functions.colors import convert_rgb_xy, convert_xy
from time import sleep
from typing import List, Any

logging = logManager.logger.get_logger(__name__)
Connections = {}


def discover(detectedLights: List[dict[str, Any]]) -> List[dict[str, Any]]:
    """
    Discover Yeelight bulbs and append them to the detectedLights list.

    Args:
        detectedLights (List[dict[str, Any]]): List to append discovered lights to.

    Returns:
        List[dict[str, Any]]: Updated list of detected lights.
    """
    logging.debug("Yeelight: <discover> invoked!")
    discover = yeelight.discover_bulbs()
    for light in discover:
        logging.info("Found YeeLight: " + light["capabilities"]["id"])
        modelid = "LWB010"
        if light["capabilities"]["model"] == "desklamp":
            modelid = "LTW001"
        elif light["capabilities"]["model"] in ["ceiling10", "ceiling20", "ceiling4", "ceilb"]:
            detectedLights.append({"protocol": "yeelight", "name": light["capabilities"]["name"] + '-bg' if light["capabilities"]["name"] != '' else 'Yeelight ' + light["capabilities"]["id"], "modelid": "LCT015", "protocol_cfg": {"ip": light["ip"], "id": light["capabilities"]["id"] + "bg", "backlight": True, "model": light["capabilities"]["model"]}})
            modelid = "LWB010" # second light must be CT only
        elif light["capabilities"]["rgb"]:
            modelid = "LCT015"
        elif light["capabilities"]["ct"]:
            modelid = "LTW001"
        elif light["capabilities"]["xy"]:
            modelid = "LLC010"
        detectedLights.append({"protocol": "yeelight", "name": light["capabilities"]["name"] if light["capabilities"]["name"] != '' else 'Yeelight ' + light["capabilities"]["id"], "modelid": modelid, "protocol_cfg": {"ip": light["ip"], "id": light["capabilities"]["id"], "backlight": False, "model": light["capabilities"]["model"]}})

    return detectedLights


def connect(light) -> yeelight.Bulb:
    """
    Connect to a Yeelight bulb.

    Args:
        light (dict[str, Any]): Light configuration dictionary.

    Returns:
        yeelight.Bulb: Connected Yeelight bulb object.
    """
    ip = light.protocol_cfg["ip"]
    if ip in Connections:
        c = Connections[ip]
    else:
        c = yeelight.Bulb(ip)
        Connections[ip] = c
    return c

def set_light(light, data: dict[str, Any]) -> None:
    """
    Set the state of a Yeelight bulb.

    Args:
        light (dict[str, Any]): Light configuration dictionary.
        data (dict[str, Any]): State data to set on the light.
    """
    c = connect(light)
    payload = {}
    transitiontime = 400
    cmdPrefix = ''
    if "backlight" in light.protocol_cfg and light.protocol_cfg["backlight"]:
        cmdPrefix = "bg_"
    if "transitiontime" in data:
        transitiontime = int(data["transitiontime"] * 100)
    for key, value in data.items():
        if key == "on":
            if value:
                payload[cmdPrefix + "set_power"] = ["on", "smooth", transitiontime]
            else:
                payload[cmdPrefix + "set_power"] = ["off", "smooth", transitiontime]
        elif key == "bri":
            payload[cmdPrefix + "set_bright"] = [int(value / 2.55) + 1, "smooth", transitiontime]
        elif key == "ct":
            #if ip[:-3] == "201" or ip[:-3] == "202":
            if light.name.find("desklamp") > 0:
                if value > 369: value = 369
            payload[cmdPrefix + "set_ct_abx"] = [int((-4800/347) * value + 2989900/347), "smooth", transitiontime]
        elif key == "hue":
            payload[cmdPrefix + "set_hsv"] = [int(value / 182), int(light.state["sat"] / 2.54), "smooth", transitiontime]
        elif key == "sat":
            payload[cmdPrefix + "set_hsv"] = [int(light.state["hue"] / 182), int(value / 2.54), "smooth", transitiontime]
        elif key == "xy":
            color = convert_xy(value[0], value[1], light.state["bri"])
            payload[cmdPrefix + "set_rgb"] = [(color[0] * 65536) + (color[1] * 256) + color[2], "smooth", transitiontime] #according to docs, yeelight needs this to set rgb. its r * 65536 + g * 256 + b
        elif key == "alert" and value != "none":
            payload[cmdPrefix + "start_cf"] = [ 4, 0, "1000, 2, 5500, 100, 1000, 2, 5500, 1, 1000, 2, 5500, 100, 1000, 2, 5500, 1"]

    # yeelight uses different functions for each action, so it has to check for each function
    # see page 9 http://www.yeelight.com/download/Yeelight_Inter-Operation_Spec.pdf
    # check if hue wants to change brightness
    for key, value in payload.items():
        c.send_command(key, value)
        sleep(0.4)

def hex_to_rgb(value: str) -> List[int]:
    """
    Convert a hex color string to an RGB list.

    Args:
        value (str): Hex color string.

    Returns:
        List[int]: RGB color list.
    """
    value = value.lstrip('#')
    lv = len(value)
    tup = tuple(int(value[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))
    return list(tup)


def calculate_color_temp(value: int) -> int:
    """
    Calculate the color temperature from a given value.

    Args:
        value (int): Input value.

    Returns:
        int: Calculated color temperature.
    """
    return int(-(347/4800) * int(value) +(2989900/4800))

def get_light_state(light) -> dict[str, Any]:
    """
    Get the current state of a Yeelight bulb.

    Args:
        light (dict[str, Any]): Light configuration dictionary.

    Returns:
        dict[str, Any]: Current state of the light.
    """
    c = connect(light)
    state = {}
    light_data = c.get_properties()
    prefix = ''
    if light.protocol_cfg["backlight"]:
        prefix = "bg_"
    if light_data[prefix + "power"] == "on": #powerstate
        state['on'] = True
    else:
        state['on'] = False

    state["bri"] = int(int(light_data[prefix + "bright"]) * 2.54)

    if light_data["color_mode"] == "1": #rgb mode
        hex_rgb = "%06x" % int(light_data[prefix + "rgb"])
        rgb=hex_to_rgb(hex_rgb)
        state["xy"] = convert_rgb_xy(rgb[0],rgb[1],rgb[2])
        state["colormode"] = "xy"
    elif light_data["color_mode"] == "2": #ct mode
        state["ct"] =  calculate_color_temp(light_data[prefix + "ct"])
        state["colormode"] = "ct"
    elif light_data["color_mode"] == "3": #hs mode
        state["hue"] = int(light_data[prefix + "hue"] * 182)
        state["sat"] = int(light_data[prefix + "sat"] * 2.54)
        state["colormode"] = "hs"
    return state
