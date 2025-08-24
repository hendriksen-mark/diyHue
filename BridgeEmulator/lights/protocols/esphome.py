import json
import requests
import logManager
from functions.colors import convert_rgb_xy, convert_xy, hsv_to_rgb, rgbBrightness
from typing import List, Any

logging = logManager.logger.get_logger(__name__)

def postRequest(address: str, request_data: str, timeout: int = 3) -> str:
    """
    Send a POST request to the specified address with the given data.

    Args:
        address: The IP address of the device.
        request_data: The data to be sent in the request.
        timeout: The timeout for the request in seconds.

    Returns:
        The response text from the request.
    """
    head = {"Content-type": "application/json"}
    response = requests.post(f"http://{address}{request_data}", timeout=timeout, headers=head)
    return response.text

def addRequest(request_data: str, data_type: str, new_data: Any) -> str:
    """
    Add new data to the request string.

    Args:
        request_data: The existing request data.
        data_type: The type of data to add.
        new_data: The new data to add.

    Returns:
        The updated request string.
    """
    separator = "&" if "?" in request_data else "?"
    return f"{request_data}{separator}{data_type}={new_data}"

def getLightType(light, data: dict[str, Any]) -> str:
    """
    Determine the type of light based on the model and data.

    Args:
        light: The light configuration.
        data: The data to be sent to the light.

    Returns:
        The endpoint for the light type.
    """
    model = light.protocol_cfg["esphome_model"]
    colormode = light.state.get("colormode", "")
    if model == "ESPHome-RGBW":
        if "xy" in data or "hue" in data or "sat" in data or colormode in ["xy", "hs"]:
            return "/light/color_led"
        elif "ct" in data or colormode == "ct":
            return "/light/white_led"
    elif model == "ESPHome-CT":
        return "/light/white_led"
    elif model == "ESPHome-RGB":
        return "/light/color_led"
    elif model == "ESPHome-Dimmable":
        return "/light/dimmable_led"
    elif model == "ESPHome-Toggle":
        return "/light/toggle_led"
    return ""

def is_json(content: str) -> bool:
    """
    Check if the given content is valid JSON.

    Args:
        content: The content to check.

    Returns:
        True if the content is valid JSON, False otherwise.
    """
    try:
        json.loads(content)
    except ValueError:
        return False
    return True

def discover(detectedLights: List[dict[str, Any]], device_ips: List[str]) -> None:
    """
    Discover ESPHome devices on the network.

    Args:
        detectedLights: The list to store detected lights.
        device_ips: The list of device IP addresses to probe.
    """
    logging.debug("ESPHome: <discover> invoked!")
    for ip in device_ips:
        try:
            logging.debug(f"ESPHome: probing ip {ip}")
            response = requests.get(f"http://{ip}/text_sensor/light_id", timeout=3)
            response.raise_for_status()
            if response.content and is_json(response.content):
                device = response.json()['state'].split(';')
                if device[0] != "esphome_diyhue_light":
                    raise ValueError("Invalid device type")
                mac, device_name, ct_boost, rgb_boost = device[1:5]
                logging.debug(f"ESPHome: Found {device_name} at ip {ip}")
                properties, modelid = get_device_properties(ip, device_name, mac, ct_boost, rgb_boost)
                detectedLights.append({"protocol": "esphome", "name": device_name, "modelid": modelid, "protocol_cfg": properties})
        except requests.RequestException as e:
            logging.info(f"ip {ip} is unknown device: {e}")

def get_device_properties(ip: str, device_name: str, mac: str, ct_boost: str, rgb_boost: str) -> tuple[dict[str, Any], str]:
    """
    Get the properties of the device.

    Args:
        ip: The IP address of the device.
        device_name: The name of the device.
        mac: The MAC address of the device.
        ct_boost: The color temperature boost value.
        rgb_boost: The RGB boost value.

    Returns:
        A tuple containing the device properties and model ID.
    """
    responses = {
        "white": requests.get(f"http://{ip}/light/white_led", timeout=3),
        "color": requests.get(f"http://{ip}/light/color_led", timeout=3),
        "dim": requests.get(f"http://{ip}/light/dimmable_led", timeout=3),
        "toggle": requests.get(f"http://{ip}/light/toggle_led", timeout=3)
    }
    if all(res.status_code != 200 for res in responses.values()):
        logging.debug("ESPHome: Device has improper configuration! Exiting.")
        raise ValueError("Improper configuration")
    properties = {"ip": ip, "name": device_name, "mac": mac, "ct_boost": ct_boost, "rgb_boost": rgb_boost}
    if responses["white"].status_code == 200 and responses["color"].status_code == 200:
        properties.update({"rgb": True, "ct": True, "esphome_model": "ESPHome-RGBW"})
        return properties, "LCT015"
    if responses["white"].status_code == 200:
        properties.update({"rgb": False, "ct": True, "esphome_model": "ESPHome-CT"})
        return properties, "LTW001"
    if responses["color"].status_code == 200:
        properties.update({"rgb": True, "ct": False, "esphome_model": "ESPHome-RGB"})
        return properties, "LCT015"
    if responses["dim"].status_code == 200:
        properties.update({"rgb": False, "ct": False, "esphome_model": "ESPHome-Dimmable"})
        return properties, "LWB010"
    if responses["toggle"].status_code == 200:
        properties.update({"rgb": False, "ct": False, "esphome_model": "ESPHome-Toggle"})
        return properties, "LOM001"
    raise ValueError("Unknown device")

def set_light(light, data: dict[str, Any], rgb: List[int] = None) -> None:
    """
    Set the state of the light.

    Args:
        light: The light configuration.
        data: The data to be sent to the light.
        rgb: The RGB values to set (optional).
    """
    logging.debug(f"ESPHome: <set_light> invoked! IP={light['protocol_cfg']['ip']}")
    ct_boost = int(light.protocol_cfg["ct_boost"])
    rgb_boost = int(light.protocol_cfg["rgb_boost"])
    request_data = ""

    if "alert" in data and data['alert'] == "select":
        request_data += "/switch/alert/turn_on"
    else:
        request_data += getLightType(light, data)
        if "white_led" in request_data:
            postRequest(light.protocol_cfg["ip"], "/light/color_led/turn_off")
        else:
            postRequest(light.protocol_cfg["ip"], "/light/white_led/turn_off")
        request_data += "/turn_off" if "on" in data and not data['on'] else "/turn_on"
        if light.protocol_cfg["esphome_model"] != "ESPHome-Toggle":
            request_data = handle_brightness_and_color(light, data, request_data, ct_boost, rgb_boost, rgb)
            request_data = addRequest(request_data, "transition", data.get('transitiontime', 4) / 10)
    postRequest(light.protocol_cfg["ip"], request_data)

def handle_brightness_and_color(light, data: dict[str, Any], request_data: str, ct_boost: int, rgb_boost: int, rgb: List[int] = None) -> str:
    """
    Handle the brightness and color settings for the light.

    Args:
        light: The light configuration.
        data: The data to be sent to the light.
        request_data: The existing request data.
        ct_boost: The color temperature boost value.
        rgb_boost: The RGB boost value.
        rgb: The RGB values to set (optional).

    Returns:
        The updated request string.
    """
    if "bri" in data:
        brightness = adjust_brightness(light, data['bri'], ct_boost, rgb_boost)
        request_data = addRequest(request_data, "brightness", brightness)
    if light.protocol_cfg["esphome_model"] in ["ESPHome-RGBW", "ESPHome-RGB", "ESPHome-CT"]:
        if "xy" in data and light.protocol_cfg["esphome_model"] in ["ESPHome-RGBW", "ESPHome-RGB"]:
            color = rgbBrightness(rgb, light.state["bri"]) if rgb else convert_xy(data['xy'][0], data['xy'][1], light.state["bri"])
            request_data = addRequest(request_data, "r", color[0])
            request_data = addRequest(request_data, "g", color[1])
            request_data = addRequest(request_data, "b", color[2])
        elif "ct" in data and light.protocol_cfg["esphome_model"] in ["ESPHome-RGBW", "ESPHome-CT"]:
            request_data = addRequest(request_data, "color_temp", data['ct'])
        elif ("hue" in data or "sat" in data) and light.protocol_cfg["esphome_model"] in ["ESPHome-RGBW", "ESPHome-RGB"]:
            hue, sat = data.get('hue', light.state["hue"]), data.get('sat', light.state["sat"])
            bri = data.get('bri', light.state["bri"])
            color = hsv_to_rgb(hue, sat, bri)
            request_data = addRequest(request_data, "r", color[0])
            request_data = addRequest(request_data, "g", color[1])
            request_data = addRequest(request_data, "b", color[2])
    return request_data

def adjust_brightness(light, brightness: int, ct_boost: int, rgb_boost: int) -> int:
    """
    Adjust the brightness based on the light model and boost values.

    Args:
        light: The light configuration.
        brightness: The brightness value to adjust.
        ct_boost: The color temperature boost value.
        rgb_boost: The RGB boost value.

    Returns:
        The adjusted brightness value.
    """
    if light.protocol_cfg["esphome_model"] == "ESPHome-RGBW":
        brightness += ct_boost if light.state["colormode"] == "ct" else rgb_boost
    elif light.protocol_cfg["esphome_model"] in ["ESPHome-CT", "ESPHome-Dimmable"]:
        brightness += ct_boost
    elif light.protocol_cfg["esphome_model"] == "ESPHome-RGB":
        brightness += rgb_boost
    return min(brightness, 255)

def get_light_state(light) -> dict[str, Any]:
    """
    Get the current state of the light.

    Args:
        light: The light configuration.

    Returns:
        The current state of the light.
    """
    logging.debug("ESPHome: <get_light_state> invoked!")
    state = {}
    model = light.protocol_cfg["esphome_model"]
    ip = light.protocol_cfg["ip"]

    if model == "ESPHome-RGBW":
        state = get_rgbw_state(ip)
    elif model == "ESPHome-CT":
        state = get_ct_state(ip)
    elif model == "ESPHome-RGB":
        state = get_rgb_state(ip)
    elif model == "ESPHome-Dimmable":
        state = get_dimmable_state(ip)
    elif model == "ESPHome-Toggle":
        state = get_toggle_state(ip)
    return state

def get_rgbw_state(ip: str) -> dict[str, Any]:
    """
    Get the state of an RGBW light.

    Args:
        ip: The IP address of the light.

    Returns:
        The current state of the RGBW light.
    """
    white_response = requests.get(f"http://{ip}/light/white_led", timeout=3)
    color_response = requests.get(f"http://{ip}/light/color_led", timeout=3)
    white_device = white_response.json()
    color_device = color_response.json()
    state = {"on": white_device['state'] == 'ON' or color_device['state'] == 'ON'}
    if white_device['state'] == 'ON':
        state.update({"ct": int(white_device['color_temp']), "bri": int(white_device['brightness']), "colormode": "ct"})
    elif color_device['state'] == 'ON':
        state.update({"xy": convert_rgb_xy(int(color_device['color']['r']), int(color_device['color']['g']), int(color_device['color']['b'])), "bri": int(color_device['brightness']), "colormode": "xy"})
    return state

def get_ct_state(ip: str) -> dict[str, Any]:
    """
    Get the state of a CT light.

    Args:
        ip: The IP address of the light.

    Returns:
        The current state of the CT light.
    """
    white_response = requests.get(f"http://{ip}/light/white_led", timeout=3)
    white_device = white_response.json()
    return {"on": white_device['state'] == 'ON', "ct": int(white_device['color_temp']), "bri": int(white_device['brightness']), "colormode": "ct"} if white_device['state'] == 'ON' else {"on": False}

def get_rgb_state(ip: str) -> dict[str, Any]:
    """
    Get the state of an RGB light.

    Args:
        ip: The IP address of the light.

    Returns:
        The current state of the RGB light.
    """
    color_response = requests.get(f"http://{ip}/light/color_led", timeout=3)
    color_device = color_response.json()
    return {"on": color_device['state'] == 'ON', "xy": convert_rgb_xy(int(color_device['color']['r']), int(color_device['color']['g']), int(color_device['color']['b'])), "bri": int(color_device['brightness']), "colormode": "xy"} if color_device['state'] == 'ON' else {"on": False}

def get_dimmable_state(ip: str) -> dict[str, Any]:
    """
    Get the state of a dimmable light.

    Args:
        ip: The IP address of the light.

    Returns:
        The current state of the dimmable light.
    """
    dimmable_response = requests.get(f"http://{ip}/light/dimmable_led", timeout=3)
    dimmable_device = dimmable_response.json()
    return {"on": dimmable_device['state'] == 'ON', "bri": int(dimmable_device['brightness'])} if dimmable_device['state'] == 'ON' else {"on": False}

def get_toggle_state(ip: str) -> dict[str, Any]:
    """
    Get the state of a toggle light.

    Args:
        ip: The IP address of the light.

    Returns:
        The current state of the toggle light.
    """
    toggle_response = requests.get(f"http://{ip}/light/toggle_led", timeout=3)
    toggle_device = toggle_response.json()
    return {"on": toggle_device['state'] == 'ON'} if toggle_device['state'] == 'ON' else {"on": False}
