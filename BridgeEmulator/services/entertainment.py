from time import sleep
import socket
import json
import uuid
from subprocess import Popen, PIPE
from typing import List, Tuple, Union, Optional, Any

import logManager
import configManager
import requests
import paho.mqtt.publish as publish
import time

from functions.colors import convert_rgb_xy, convert_xy
from HueObjects import Light, Group, ApiUser, EntertainmentConfiguration

logging = logManager.logger.get_logger(__name__)
bridgeConfig = configManager.bridgeConfig.yaml_config

cieTolerance: float = 0.03  # new frames will be ignored if the color change is smaller than this value
briTolerance: int = 16  # new frames will be ignored if the brightness change is smaller than this value
lastAppliedFrame: dict[str, dict[str, Union[List[float], int]]] = {}
YeelightConnections: dict[str, 'YeelightConnection'] = {}

def skipSimilarFrames(light: str, color: List[float], brightness: int) -> int:
    """
    Skip frames if the color or brightness change is below a certain tolerance.

    Args:
        light (str): The light identifier.
        color (List[float]): The color in xy format.
        brightness (int): The brightness level.

    Returns:
        int: 2 if color change is significant, 1 if brightness change is significant, 0 otherwise.
    """
    if light not in lastAppliedFrame:  # check if light exists in dictionary
        lastAppliedFrame[light] = {"xy": [0, 0], "bri": 0}

    if abs(lastAppliedFrame[light]["xy"][0] - color[0]) > cieTolerance or abs(lastAppliedFrame[light]["xy"][1] - color[1]) > cieTolerance:
        lastAppliedFrame[light]["xy"] = color
        return 2
    if abs(lastAppliedFrame[light]["bri"] - brightness) > briTolerance:
        lastAppliedFrame[light]["bri"] = brightness
        return 1
    return 0

def getObject(v2uuid: str) -> Optional[object]:
    """
    Retrieve the light object based on its v2 UUID.

    Args:
        v2uuid (str): The v2 UUID of the light.

    Returns:
        Optional[object]: The light object if found, None otherwise.
    """
    for key, obj in bridgeConfig["lights"].items():
        obj: Light.Light = obj
        if str(uuid.uuid5(uuid.NAMESPACE_URL, obj.id_v2 + 'entertainment')) == v2uuid:
            return obj
    logging.info("Element not found!")
    return None

def findGradientStrip(group: Group.Group) -> Union[object, str]:
    """
    Find a gradient strip light in the group.

    Args:
        group (Group.Group): The group object containing lights.

    Returns:
        Union[object, str]: The gradient strip light object if found, "not found" otherwise.
    """
    for light in group.lights:
        light: Light.Light = light()
        if light.modelid in ["LCX001", "LCX002", "LCX003", "915005987201", "LCX004"]:
            return light
    return "not found"

def get_hue_entertainment_group(light, groupname: str) -> int:
    """
    Get the entertainment group ID for a given light and group name.

    Args:
        light : The light object.
        groupname (str): The name of the group.

    Returns:
        int: The entertainment group ID if found, -1 otherwise.
    """
    try:
        group = requests.get(f"http://{light.protocol_cfg['ip']}/api/{light.protocol_cfg['hueUser']}/groups/", timeout=3)
        groups: dict[str, dict[str, Any]] = group.json()
        for i, grp in groups.items():
            if grp["name"] == groupname and grp["type"] == "Entertainment" and light.protocol_cfg["id"] in grp["lights"]:
                logging.debug(f"Found corresponding entertainment group with id {i} for light {light.name}")
                return int(i)
    except requests.RequestException as e:
        logging.error(f"Error fetching entertainment group: {e}")
    return -1

def entertainmentService(group: EntertainmentConfiguration.EntertainmentConfiguration, user: ApiUser.ApiUser) -> None:
    """
    Start the entertainment service for a group and user.

    Args:
        group (EntertainmentConfiguration): The group object.
        user (ApiUser): The user object.
    """
    logging.debug(f"User: {user.username}")
    logging.debug(f"Key: {user.client_key}")
    group.stream["owner"] = user.username
    group.state = {"all_on": True, "any_on": True}
    lights_v2 = []
    lights_v1 = {}
    hueGroup = -1
    hueGroupLights = {}
    prev_frame_time = 0
    non_UDP_update_counter = 0

    for light in group.lights:
        light: Light.Light = light()
        lights_v1[int(light.id_v1)] = light
        if light.protocol == "hue" and (hueGroup := get_hue_entertainment_group(light, group.name)) != -1:
            hueGroupLights[int(light.protocol_cfg["id"])] = []
        if light.protocol == "govee":
            light.setV1State({"on": True, "bri": 255})
        light.state.update({"mode": "streaming", "on": True, "colormode": "xy"})

    v2LightNr = {}
    for channel in group.getV2Api()["channels"]:
        lightObj: Light.Light = getObject(channel["members"][0]["service"]["rid"])
        if lightObj:
            v2LightNr[lightObj.id_v1] = v2LightNr.get(lightObj.id_v1, -1) + 1
            lights_v2.append({"light": lightObj, "lightNr": v2LightNr[lightObj.id_v1]})

    logging.debug(lights_v1)
    logging.debug(lights_v2)

    opensslCmd = ['openssl', 's_server', '-dtls', '-psk', user.client_key, '-psk_identity', user.username, '-nocert', '-accept', '2100', '-quiet']
    p = Popen(opensslCmd, stdin=PIPE, stdout=PIPE, stderr=PIPE)

    if hueGroup != -1:
        h = HueConnection(bridgeConfig["config"]["hue"]["ip"])
        h.connect(hueGroup, hueGroupLights)
        if not h._connected:
            hueGroupLights = {}

    init: bool = False
    frameBites: int = 10
    frameID: int = 1
    initMatchBytes: int = 0
    host_ip: str = bridgeConfig["config"]["ipaddress"]
    p.stdout.read(1)  # read one byte so the init function will correctly detect the frameBites

    try:
        min_frame_time = 1.0 / float(bridgeConfig["config"].get("entertainment_fps", 30))
        while group.stream["active"]:
            frame_start_time = time.time()
            new_frame_time = frame_start_time
            if not init:
                readByte: bytes = p.stdout.read(1)
                logging.debug(readByte)
                if readByte in b'HueStream':
                    initMatchBytes += 1
                else:
                    initMatchBytes = 0
                if initMatchBytes == 9:
                    frameBites = frameID - 8
                    logging.debug(f"frameBites: {frameBites}")
                    p.stdout.read(frameBites - 9)  # sync streaming bytes
                    init = True
                frameID += 1
            else:
                data: bytes = p.stdout.read(frameBites)
                nativeLights: dict[int, Light.Light] = {}
                esphomeLights: dict[int, Light.Light] = {}
                mqttLights: list[Light.Light] = []
                wledLights: dict[int, Light.Light] = {}
                non_UDP_lights: list[Light.Light] = []

                if data[:9].decode('utf-8') == "HueStream":
                    i = 0
                    apiVersion: int = 0
                    counter: int = 0
                    if data[9] == 1:
                        i = 16
                        apiVersion = 1
                        counter = len(data)
                    elif data[9] == 2:
                        i = 52
                        apiVersion = 2
                        counter = len(group.getV2Api()["channels"]) * 7 + 52

                    channels: dict[int, int] = {}
                    while i < counter:
                        light: Light.Light | None = None
                        r, g, b = 0, 0, 0
                        bri: int = 0
                        if apiVersion == 1:
                            channels[data[i+1] * 256 + data[i+2]] = channels.get(data[i+1] * 256 + data[i+2], -1) + 1
                            if data[i] == 0:
                                if data[i+1] * 256 + data[i+2] == 0:
                                    break
                                light = lights_v1[data[i+1] * 256 + data[i+2]]
                            elif data[i] == 1:  # Type of device Gradient Strip
                                light = findGradientStrip(group)
                            if data[14] == 0:
                                r = int((data[i+3] * 256 + data[i+4]) / 256)
                                g = int((data[i+5] * 256 + data[i+6]) / 256)
                                b = int((data[i+7] * 256 + data[i+8]) / 256)
                            elif data[14] == 1:
                                x = (data[i+3] * 256 + data[i+4]) / 65535
                                y = (data[i+5] * 256 + data[i+6]) / 65535
                                bri = int((data[i+7] * 256 + data[i+8]) / 256)
                                r, g, b = convert_xy(x, y, bri)
                        elif apiVersion == 2:
                            light = lights_v2[data[i]]["light"]
                            if data[14] == 0:
                                r = int((data[i+1] * 256 + data[i+2]) / 256)
                                g = int((data[i+3] * 256 + data[i+4]) / 256)
                                b = int((data[i+5] * 256 + data[i+6]) / 256)
                            elif data[14] == 1:
                                x = (data[i+1] * 256 + data[i+2]) / 65535
                                y = (data[i+3] * 256 + data[i+4]) / 65535
                                bri = int((data[i+5] * 256 + data[i+6]) / 256)
                                r, g, b = convert_xy(x, y, bri)

                        if light is None:
                            logging.info("Error in light identification")
                            break

                        logging.debug(f"Frame: {frameID} Light: {light.name} RED: {r}, GREEN: {g}, BLUE: {b}")
                        proto = light.protocol
                        if r == 0 and g == 0 and b == 0:
                            light.state["on"] = False
                        else:
                            light.state.update({"on": True, "bri": bri or int((r + g + b) / 3), "xy": [x, y] if bri else convert_rgb_xy(r, g, b), "colormode": "xy"})

                        if proto in ["native", "native_multi", "native_single"]:
                            nativeLights.setdefault(light.protocol_cfg["ip"], {})
                            if apiVersion == 1:
                                if light.modelid in ["LCX001", "LCX002", "LCX003", "915005987201", "LCX004", "LCX006"]:
                                    if data[i] == 1:
                                        nativeLights[light.protocol_cfg["ip"]][data[i+1] * 256 + data[i+2]] = [r, g, b]
                                    else:
                                        for x in range(7):
                                            nativeLights[light.protocol_cfg["ip"]][x] = [r, g, b]
                                else:
                                    nativeLights[light.protocol_cfg["ip"]][light.protocol_cfg["light_nr"] - 1] = [r, g, b]
                            elif apiVersion == 2:
                                if light.modelid in ["LCX001", "LCX002", "LCX003", "915005987201", "LCX004", "LCX006"]:
                                    nativeLights[light.protocol_cfg["ip"]][lights_v2[data[i]]["lightNr"]] = [r, g, b]
                                else:
                                    nativeLights[light.protocol_cfg["ip"]][light.protocol_cfg["light_nr"] - 1] = [r, g, b]
                        elif proto == "esphome":
                            esphomeLights.setdefault(light.protocol_cfg["ip"], {})
                            bri = int(max(r, g, b))
                            esphomeLights[light.protocol_cfg["ip"]]["color"] = [r, g, b, bri]
                        elif proto == "mqtt":
                            operation = skipSimilarFrames(light.id_v1, light.state["xy"], light.state["bri"])
                            if operation == 1:
                                mqttLights.append({"topic": light.protocol_cfg["command_topic"], "payload": json.dumps({"brightness": light.state["bri"], "transition": 0.2})})
                            elif operation == 2:
                                mqttLights.append({"topic": light.protocol_cfg["command_topic"], "payload": json.dumps({"color": {"x": light.state["xy"][0], "y": light.state["xy"][1]}, "transition": 0.15})})
                        elif proto == "yeelight":
                            enableMusic(light.protocol_cfg["ip"], host_ip)
                            c = YeelightConnections[light.protocol_cfg["ip"]]
                            operation = skipSimilarFrames(light.id_v1, light.state["xy"], light.state["bri"])
                            if operation == 1:
                                c.command("set_bright", [int(light.state["bri"] / 2.55), "smooth", 200])
                            elif operation == 2:
                                c.command("set_rgb", [(r * 65536) + (g * 256) + b, "smooth", 200])
                        elif proto == "wled":
                            wledLights.setdefault(light.protocol_cfg["ip"], {})
                            wledLights[light.protocol_cfg["ip"]].setdefault(light.protocol_cfg["segmentId"], {
                                "ledCount": light.protocol_cfg["ledCount"],
                                "start": light.protocol_cfg["segment_start"],
                                "udp_port": light.protocol_cfg["udp_port"],
                                "color": [r, g, b]
                            })
                        elif proto == "hue" and int(light.protocol_cfg["id"]) in hueGroupLights:
                            hueGroupLights[int(light.protocol_cfg["id"])] = [r, g, b]
                        else:
                            if light not in non_UDP_lights:
                                non_UDP_lights.append(light)

                        frameID = (frameID % 25) + 1
                        i += 9 if apiVersion == 1 else 7

                    if nativeLights:
                        for ip, lights in nativeLights.items():
                            udpmsg = bytearray()
                            for light, colors in lights.items():
                                udpmsg += bytes([light]) + bytes(colors)
                            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            sock.sendto(udpmsg, (ip.split(":")[0], 2100))

                    if esphomeLights:
                        for ip, colors in esphomeLights.items():
                            udpmsg = bytearray([0] + colors["color"])
                            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                            sock.sendto(udpmsg, (ip.split(":")[0], 2100))

                    if mqttLights:
                        auth = None
                        if bridgeConfig["config"]["mqtt"]["mqttUser"] and bridgeConfig["config"]["mqtt"]["mqttPassword"]:
                            auth = {'username': bridgeConfig["config"]["mqtt"]["mqttUser"], 'password': bridgeConfig["config"]["mqtt"]["mqttPassword"]}
                        publish.multiple(mqttLights, hostname=bridgeConfig["config"]["mqtt"]["mqttServer"], port=bridgeConfig["config"]["mqtt"]["mqttPort"], auth=auth)

                    if wledLights:
                        wled_udpmode = 4  # DNRGB mode
                        wled_secstowait = 2
                        for ip, segments in wledLights.items():
                            for segment, details in segments.items():
                                udphead = bytes([wled_udpmode, wled_secstowait])
                                start_seg = details["start"].to_bytes(2, "big")
                                color = bytes(details["color"] * details["ledCount"])
                                udpdata = udphead + start_seg + color
                                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                                sock.sendto(udpdata, (ip.split(":")[0], details["udp_port"]))

                    if hueGroupLights:
                        h.send(hueGroupLights, hueGroup)

                    if non_UDP_lights:
                        light = non_UDP_lights[non_UDP_update_counter]
                        operation = skipSimilarFrames(light.id_v1, light.state["xy"], light.state["bri"])
                        if operation == 1:
                            light.setV1State({"bri": light.state["bri"], "transitiontime": 3})
                        elif operation == 2:
                            light.setV1State({"xy": light.state["xy"], "transitiontime": 3})
                        non_UDP_update_counter = (non_UDP_update_counter + 1) % len(non_UDP_lights)

                    if new_frame_time - prev_frame_time > 1:
                        fps = 1.0 / (time.time() - new_frame_time)
                        prev_frame_time = new_frame_time
                        logging.info(f"Entertainment FPS: {fps}")
                else:
                    try:
                        header = data[:9].decode('utf-8', errors='replace')
                    except:
                        header = "unable to decode"
                    logging.error(f"HueStream header missing in frame. Expected 'HueStream', got: '{header}' (hex: {data[:9].hex()})")
                    p.kill()
                    try:
                        h.disconnect()
                    except UnboundLocalError:
                        pass

            # FPS limiting
            elapsed = time.time() - frame_start_time
            if elapsed < min_frame_time:
                time.sleep(min_frame_time - elapsed)

    except socket.timeout as e:
        logging.error(f"Entertainment Service timed out: {e}")
    except Exception as e:
        logging.error(f"An unexpected error occurred: {e}")
    finally:
        p.kill()
        group.stream["owner"] = None
        try:
            h.disconnect()
        except UnboundLocalError:
            pass
        group.stream["active"] = False
        for light in group.lights:
            light: Light.Light = light()
            light.state["mode"] = "homeautomation"
        logging.info("Entertainment service stopped")

def enableMusic(ip: str, host_ip: str) -> None:
    """
    Enable music mode for a Yeelight device.

    Args:
        ip (str): The IP address of the Yeelight device.
        host_ip (str): The IP address of the host.
    """
    if ip in YeelightConnections:
        c = YeelightConnections[ip]
        if not c._music:
            c.enableMusic(host_ip)
    else:
        c = YeelightConnection(ip)
        YeelightConnections[ip] = c
        c.enableMusic(host_ip)

def disableMusic(ip: str) -> None:
    """
    Disable music mode for a Yeelight device.

    Args:
        ip (str): The IP address of the Yeelight device.
    """
    if ip in YeelightConnections:
        YeelightConnections[ip].disableMusic()

class YeelightConnection:
    """
    A class to manage connections to Yeelight devices.
    """
    _music = False
    _connected = False
    _socket: Optional[socket.socket] = None
    _host_ip = ""

    def __init__(self, ip: str):
        """
        Initialize the YeelightConnection.

        Args:
            ip (str): The IP address of the Yeelight device.
        """
        self._ip = ip

    def connect(self, simple: bool = False) -> None:
        """
        Connect to the Yeelight device.

        Args:
            simple (bool): Whether to use a simple connection without music mode.
        """
        self.disconnect()
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.settimeout(5)
        self._socket.connect((self._ip, 55443))
        if not simple and self._music:
            self.enableMusic(self._host_ip)
        else:
            self._connected = True

    def disconnect(self) -> None:
        """
        Disconnect from the Yeelight device.
        """
        self._connected = False
        if self._socket:
            self._socket.close()
        self._socket = None

    def enableMusic(self, host_ip: str) -> None:
        """
        Enable music mode on the Yeelight device.

        Args:
            host_ip (str): The IP address of the host.
        """
        if self._connected and self._music:
            raise AssertionError("Already in music mode!")

        self._host_ip = host_ip

        tempSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        tempSock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        tempSock.settimeout(5)
        tempSock.bind(("", 0))
        port = tempSock.getsockname()[1]
        tempSock.listen(3)
        try:
            while True:
                conn, addr = tempSock.accept()
                if addr[0] == self._ip:
                    tempSock.close()
                    self._socket = conn
                    self._connected = True
                    self._music = True
                    break
                else:
                    logging.info(f"Rejecting connection to the music mode listener from {addr[0]}")
                    conn.close()
        except Exception as e:
            tempSock.close()
            raise ConnectionError(f"Yeelight with IP {self._ip} doesn't want to connect in music mode: {e}")

        logging.info(f"Yeelight device with IP {self._ip} is now in music mode")

    def disableMusic(self) -> None:
        """
        Disable music mode on the Yeelight device.
        """
        if not self._music:
            return

        if self._socket:
            self._socket.close()
            self._socket = None
        self._music = False
        logging.info(f"Yeelight device with IP {self._ip} is no longer using music mode")

    def send(self, data: bytes, flags: int = 0) -> None:
        """
        Send data to the Yeelight device.

        Args:
            data (bytes): The data to send.
            flags (int): Optional flags for the send operation.
        """
        try:
            if not self._connected:
                self.connect()
            self._socket.send(data, flags)
        except Exception as e:
            self._connected = False
            raise e

    def recv(self, bufsize: int, flags: int = 0) -> bytes:
        """
        Receive data from the Yeelight device.

        Args:
            bufsize (int): The buffer size for receiving data.
            flags (int): Optional flags for the receive operation.

        Returns:
            bytes: The received data.
        """
        try:
            if not self._connected:
                self.connect()
            return self._socket.recv(bufsize, flags)
        except Exception as e:
            self._connected = False
            raise e

    def command(self, api_method: str, param: List[Union[int, str]]) -> None:
        """
        Send a command to the Yeelight device.

        Args:
            api_method (str): The API method to call.
            param (List[Union[int, str]]): The parameters for the API method.
        """
        try:
            msg = json.dumps({"id": 1, "method": api_method, "params": param}) + "\r\n"
            self.send(msg.encode())
        except Exception as e:
            logging.warning("Yeelight command error: %s", e)

class HueConnection:
    """
    A class to manage connections to Hue bridges.
    """
    _connected = False
    _ip = ""
    _entGroup = -1
    _connection = ""
    _hueLights = []

    def __init__(self, ip: str):
        """
        Initialize the HueConnection.

        Args:
            ip (str): The IP address of the Hue bridge.
        """
        self._ip = ip

    def connect(self, hueGroup: int, *lights: List[Tuple[int, List[int]]]) -> None:
        """
        Connect to the Hue bridge and start the entertainment stream.

        Args:
            hueGroup (int): The entertainment group ID.
            lights (List[Tuple[int, List[int]]]): The lights in the group.
        """
        self._entGroup = hueGroup
        self._hueLights = lights
        self.disconnect()

        url = f"http://{self._ip}/api/{bridgeConfig['config']['hue']['hueUser']}/groups/{self._entGroup}"
        r = requests.put(url, json={"stream": {"active": True}})
        logging.debug(f"Outgoing connection to hue Bridge returned: {r.text}")
        try:
            _opensslCmd = [
                'openssl', 's_client', '-quiet', '-cipher', 'PSK-AES128-GCM-SHA256', '-dtls', 
                '-psk', bridgeConfig["config"]["hue"]["hueKey"], '-psk_identity', bridgeConfig["config"]["hue"]["hueUser"], 
                '-connect', f"{self._ip}:2100"
            ]
            self._connection = Popen(_opensslCmd, stdin=PIPE, stdout=None, stderr=None)
            self._connected = True
            sleep(1)  # Wait a bit to catch errors
            err = self._connection.poll()
            if err is not None:
                raise ConnectionError(err)
        except Exception as e:
            logging.info(f"Error connecting to Hue bridge for entertainment. Is a proper hueKey set? openssl connection returned: {e}")
            self.disconnect()

    def disconnect(self) -> None:
        """
        Disconnect from the Hue bridge and stop the entertainment stream.
        """
        try:
            url = f"http://{self._ip}/api/{bridgeConfig['config']['hue']['hueUser']}/groups/{self._entGroup}"
            if self._connected:
                self._connection.kill()
            requests.put(url, data={"stream": {"active": False}})
            self._connected = False
        except:
            pass

    def send(self, lights: dict[int, List[int]], hueGroup: int) -> None:
        """
        Send light data to the Hue bridge.

        Args:
            lights (dict[int, List[int]]): The light data to send.
            hueGroup (int): The entertainment group ID.
        """
        arr = bytearray("HueStream", 'ascii')
        msg = [
                1, 0,     #Api version
                0,        #Sequence number, not needed
                0, 0,     #Zeroes
                0,        #0: RGB Color space, 1: XY Brightness
                0,        #Zero
              ]
        for id in lights:
            r, g, b = lights[id]
            msg.extend([    0,      #Type: Light
                            0, id,  #Light id (v1-type), 16 Bit
                            r, r,   #Red (or X) as 16 (2 * 8) bit value
                            g, g,   #Green (or Y)
                            b, b,   #Blue (or Brightness)
                            ])
        arr.extend(msg)
        logging.debug(f"Outgoing data to other Hue Bridge: {arr.hex(',')}")
        try:
            self._connection.stdin.write(arr)
            self._connection.stdin.flush()
        except:
            logging.debug("Reconnecting to Hue bridge to sync. This is normal.")  # Reconnect if the connection timed out
            self.disconnect()
            self.connect(hueGroup)
