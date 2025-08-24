import socket
import urllib.request
import json
import math
import logManager
import requests
from functions.colors import convert_rgb_xy, convert_xy
from time import sleep
from zeroconf import IPVersion, ServiceBrowser, ServiceStateChange, Zeroconf
from typing import List, Any

logging = logManager.logger.get_logger(__name__)

discovered_lights: List[List[str]] = []
Connections: dict[str, 'WledDevice'] = {}


def on_mdns_discover(zeroconf: Zeroconf, service_type: str, name: str, state_change: ServiceStateChange) -> None:
    """
    Callback function for mDNS discovery.
    
    Args:
        zeroconf: Zeroconf instance
        service_type: Type of the service
        name: Name of the service
        state_change: State change of the service
    """
    global discovered_lights
    if "wled" in name and state_change is ServiceStateChange.Added:
        info = zeroconf.get_service_info(service_type, name)
        if info:
            addresses = ["%s" % (socket.inet_ntoa(addr))
                         for addr in info.addresses]
            discovered_lights.append([addresses[0], name])


def discover(detectedLights: List[dict[str, Any]], device_ips: List[str]) -> None:
    """
    Discover WLED devices using mDNS and fallback to device IPs if necessary.
    
    Args:
        detectedLights: List to store detected lights
        device_ips: List of device IPs to fallback to
    """
    logging.info('<WLED> discovery started')
    ip_version = IPVersion.V4Only
    zeroconf = Zeroconf(ip_version=ip_version)
    services = "_http._tcp.local."
    browser = ServiceBrowser(zeroconf, services, handlers=[on_mdns_discover])
    sleep(2)
    if not discovered_lights:
        logging.info(
            "<WLED> Nothing found using mDNS, trying device_ips method...")
        for ip in device_ips:
            try:
                response = requests.get(
                    f"http://{ip}/json/info", timeout=3)
                if response.status_code == 200:
                    json_resp = response.json()
                    if json_resp['brand'] == "WLED":
                        discovered_lights.append([ip, json_resp['name']])
            except Exception as e:
                logging.debug("<WLED> ip %s is unknown device", ip)

    lights = []
    for device in discovered_lights:
        try:
            wled_device = WledDevice(device[0], device[1])
            logging.info("<WLED> Found device: %s with %d segments",
                         device[1], wled_device.segmentCount)
            modelid = "LST002"  # Gradient Strip
            for segment_id in range(wled_device.segmentCount):
                lights.append({
                    "protocol": "wled",
                    "name": f"{wled_device.name}_seg{segment_id}",
                    "modelid": modelid,
                    "protocol_cfg": {
                        "ip": wled_device.ip,
                        "ledCount": wled_device.segments[segment_id]["len"],
                        "mdns_name": device[1],
                        "mac": wled_device.mac,
                        "segmentId": segment_id,
                        "segment_start": wled_device.segments[segment_id]["start"],
                        "udp_port": wled_device.udpPort
                    }
                })
            detectedLights.extend(lights)
        except Exception as e:
            logging.error("<WLED> Error discovering device: %s", e)


def set_light(light: dict[str, Any], data: dict[str, Any]) -> None:
    """
    Set the state of a WLED light.
    
    Args:
        light: Light configuration
        data: Data to set the light state
    """
    ip = light.protocol_cfg['ip']
    if ip in Connections:
        wled_device = Connections[ip]
    else:
        wled_device = WledDevice(ip, light.protocol_cfg['mdns_name'])
        Connections[ip] = wled_device

    if "lights" in data:
        destructured_data = data["lights"][list(data["lights"].keys())[0]]
        send_light_data(wled_device, light, destructured_data)
    else:
        send_light_data(wled_device, light, data)


def send_light_data(wled_device: 'WledDevice', light: dict[str, Any], data: dict[str, Any]) -> None:
    """
    Send light data to the WLED device.
    
    Args:
        wled_device: WledDevice instance
        light: Light configuration
        data: Data to send to the light
    """
    state = {}
    seg = {
        "id": light.protocol_cfg['segmentId'],
        "on": True
    }
    for key, value in data.items():
        if key == "on":
            seg["on"] = value
        elif key == "bri":
            seg["bri"] = value + 1
        elif key == "ct":
            kelvin = round(translate_range(value, 153, 500, 6500, 2000))
            color = kelvin_to_rgb(kelvin)
            seg["col"] = [[color[0], color[1], color[2]]]
        elif key == "xy":
            color = convert_xy(value[0], value[1], 255)
            seg["col"] = [[color[0], color[1], color[2]]]
        elif key == "alert" and value != "none":
            state = wled_device.get_seg_state(light.protocol_cfg['segmentId'])
            wled_device.set_bri_seg(0, light.protocol_cfg['segmentId'])
            sleep(0.6)
            wled_device.set_bri_seg(state["bri"], light.protocol_cfg['segmentId'])
            return
    state["seg"] = [seg]
    wled_device.send_json(state)


def get_light_state(light: dict[str, Any]) -> dict[str, Any]:
    """
    Get the current state of a WLED light.
    
    Args:
        light: Light configuration
        
    Returns:
        Current state of the light
    """
    ip = light.protocol_cfg['ip']
    if ip in Connections:
        wled_device = Connections[ip]
    else:
        wled_device = WledDevice(ip, light.protocol_cfg['mdns_name'])
        Connections[ip] = wled_device
    return wled_device.get_seg_state(light.protocol_cfg['segmentId'])


def translate_range(value: float, left_min: float, left_max: float, right_min: float, right_max: float) -> float:
    """
    Translate a value from one range to another.
    
    Args:
        value: Value to translate
        left_min: Minimum of the left range
        left_max: Maximum of the left range
        right_min: Minimum of the right range
        right_max: Maximum of the right range
        
    Returns:
        Translated value
    """
    left_span = left_max - left_min
    right_span = right_max - right_min
    value_scaled = float(value - left_min) / float(left_span)
    return right_min + (value_scaled * right_span)


def clamp(num: float, min_val: float, max_val: float) -> float:
    """
    Clamp a number between a minimum and maximum value.
    
    Args:
        num: Number to clamp
        min_val: Minimum value
        max_val: Maximum value
        
    Returns:
        Clamped number
    """
    return max(min(num, max_val), min_val)


def kelvin_to_rgb(temp: float) -> List[int]:
    """
    Convert a color temperature in Kelvin to an RGB color.
    
    Args:
        temp: Color temperature in Kelvin
        
    Returns:
        RGB color as a list of integers
    """
    tmp_kelvin = clamp(temp, 1000, 40000) / 100
    r = 255 if tmp_kelvin <= 66 else clamp(
        329.698727446 * pow(tmp_kelvin - 60, -0.1332047592), 0, 255)
    g = clamp(99.4708025861 * math.log(tmp_kelvin) - 161.1195681661, 0,
              255) if tmp_kelvin <= 66 else clamp(288.1221695283 * (pow(tmp_kelvin - 60, -0.0755148492)), 0, 255)
    b = 255 if tmp_kelvin >= 66 else 0 if tmp_kelvin <= 19 else clamp(
        138.5177312231 * math.log(tmp_kelvin - 10) - 305.0447927307, 0, 255)
    return [r, g, b]


class WledDevice:
    """
    Class representing a WLED device.
    """

    def __init__(self, ip: str, mdns_name: str) -> None:
        """
        Initialize the WledDevice instance.
        
        Args:
            ip: IP address of the device
            mdns_name: mDNS name of the device
        """
        self.ip = ip
        self.name = mdns_name.split(".")[0]
        self.url = f'http://{self.ip}'
        self.ledCount = 0
        self.mac = None
        self.segmentCount = 1  # Default number of segments in WLED
        self.segments = []
        self.get_initial_state()

    def get_initial_state(self) -> None:
        """
        Get the initial state of the WLED device.
        """
        self.state = self.get_light_state()
        self.get_info()

    def get_info(self) -> None:
        """
        Get information about the WLED device.
        """
        self.ledCount = self.state['info']['leds']['count']
        self.mac = ':'.join(self.state[
                            'info']['mac'][i:i+2] for i in range(0, 12, 2))
        self.segments = self.state['state']['seg']
        self.segmentCount = len(self.segments)
        self.udpPort = self.state['info']['udpport']

    def get_light_state(self) -> dict[str, Any]:
        """
        Get the current state of the WLED device.
        
        Returns:
            Current state of the device
        """
        with urllib.request.urlopen(f"{self.url}/json") as resp:
            return json.loads(resp.read())

    def get_seg_state(self, seg: int) -> dict[str, Any]:
        """
        Get the state of a specific segment.
        
        Args:
            seg: Segment ID
            
        Returns:
            State of the segment
        """
        state = {}
        data = self.get_light_state()['state']
        seg = data['seg'][seg]
        state['bri'] = seg['bri']
        state['on'] = seg['on']
        r = int(seg['col'][0][0])+1
        g = int(seg['col'][0][1])+1
        b = int(seg['col'][0][2])+1
        state['xy'] = convert_rgb_xy(r, g, b)
        state["colormode"] = "xy"
        return state

    def set_rgb_seg(self, r: int, g: int, b: int, seg: int) -> None:
        """
        Set the RGB color of a specific segment.
        
        Args:
            r: Red value
            g: Green value
            b: Blue value
            seg: Segment ID
        """
        state = {"seg": [{"id": seg, "col": [[r, g, b]]}]}
        self.send_json(state)

    def set_on_seg(self, on: bool, seg: int) -> None:
        """
        Turn a specific segment on or off.
        
        Args:
            on: On/Off state
            seg: Segment ID
        """
        state = {"seg": [{"id": seg, "on": on}]}
        self.send_json(state)

    def set_bri_seg(self, bri: int, seg: int) -> None:
        """
        Set the brightness of a specific segment.
        
        Args:
            bri: Brightness value
            seg: Segment ID
        """
        state = {"seg": [{"id": seg, "bri": bri}]}
        self.send_json(state)

    def send_json(self, data: dict[str, Any]) -> None:
        """
        Send JSON data to the WLED device.
        
        Args:
            data: Data to send
        """
        req = urllib.request.Request(f"{self.url}/json")
        req.add_header('Content-Type', 'application/json; charset=utf-8')
        jsondata = json.dumps(data)
        jsondataasbytes = jsondata.encode('utf-8')
        req.add_header('Content-Length', len(jsondataasbytes))
        urllib.request.urlopen(req, jsondataasbytes)
