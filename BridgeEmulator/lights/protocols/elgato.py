import socket
import json
import requests
import logManager
from time import sleep
from zeroconf import IPVersion, ServiceBrowser, ServiceStateChange, Zeroconf

logging = logManager.logger.get_logger(__name__)

discovered_lights = []

def on_mdns_discover(zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange):
    """
    Callback function for mDNS discovery.
    """
    if "Elgato Key Light" in name and state_change is ServiceStateChange.Added:
        info = zeroconf.get_service_info(service_type, name)
        if info:
            addresses = ["%s" % (socket.inet_ntoa(addr)) for addr in info.addresses]
            discovered_lights.append([addresses[0], name])
            logging.debug('<Elgato> mDNS device discovered: ' + addresses[0])

def discover(detectedLights: list, elgato_ips: list) -> None:
    """
    Discover Elgato lights using mDNS and fallback to IP addresses if necessary.
    """
    mdns_string = "_elgo._tcp.local."
    logging.info('<Elgato> mDNS discovery for ' + mdns_string + ' started')
    zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
    ServiceBrowser(zeroconf, mdns_string, handlers=[on_mdns_discover])

    sleep(2)

    if not discovered_lights:
        logging.info("<Elgato> Nothing found using mDNS, trying to find lights by IP")
        for ip in elgato_ips:
            try:
                response = requests.get(f"http://{ip}:9123/elgato/accessory-info", timeout=3)
                if response.status_code == 200:
                    json_resp = response.json()
                    if json_resp['productName'] in ["Elgato Key Light Mini", "Elgato Key Light Air", "Elgato Key Light"]:
                        discovered_lights.append([ip, json_resp['displayName']])
            except requests.RequestException:
                logging.warning("<Elgato> ip %s is unknown device", ip)

    lights = []
    for device in discovered_lights:
        try:
            response = requests.get(f"http://{device[0]}:9123/elgato/accessory-info", timeout=3)
            if response.status_code == 200:
                json_accessory_info = response.json()
                logging.info("<Elgato> Found device: %s at IP %s" % (device[1], device[0]))
                lights.append({
                    "protocol": "elgato",
                    "name": json_accessory_info["displayName"],
                    "modelid": "LTW001",  # Colortemp Bulb
                    "protocol_cfg": {
                        "ip": device[0],
                        "mdns_name": device[1],
                        "mac": json_accessory_info["macAddress"],
                    }
                })
        except requests.RequestException as e:
            logging.warning("<Elgato> EXCEPTION: " + str(e))
            break

    detectedLights.extend(lights)

def translate_range(value: float, old_min: float, old_max: float, new_min: float, new_max: float) -> int:
    """
    Translate a value from one range to another.
    """
    old_range = old_max - old_min
    new_range = new_max - new_min
    scaled_value = (((value - old_min) * new_range) / old_range) + new_min
    return int(max(min(scaled_value, new_max), new_min))

def set_light(light, data: dict) -> None:
    """
    Set the state of the light.
    """
    light_state = {}

    if 'on' in data:
        light_state['on'] = 1 if data['on'] else 0

    if 'bri' in data and data['bri'] > 0:
        light_state['brightness'] = round((data['bri'] / 255) * 100)

    if 'ct' in data:
        light_state['temperature'] = translate_range(data['ct'], 153, 500, 143, 344)

    # Ignore unsupported values (xy, hue, sat)

    if light_state:
        json_data = json.dumps({"lights": [light_state]})
        response = requests.put(f"http://{light.protocol_cfg['ip']}:9123/elgato/lights", data=json_data, headers={'Content-type': 'application/json'}, timeout=3)
        return response.text

def get_light_state(light) -> dict:
    """
    Get the current state of the light.
    """
    response = requests.get(f"http://{light.protocol_cfg['ip']}:9123/elgato/lights", timeout=3)
    state = response.json()
    light_info = state['lights'][0]
    light_state_on = light_info['on'] == 1

    return {
        'bri': round((light_info['brightness'] / 100) * 255),
        'on': light_state_on,
        'ct': translate_range(light_info['temperature'], 143, 344, 153, 500),
        'colormode': 'ct'
    }
