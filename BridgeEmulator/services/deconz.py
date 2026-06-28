import json
import weakref
from datetime import datetime, timezone
from threading import Thread
from time import sleep
from typing import Union, Any

import requests
from ws4py.client.threadedclient import WebSocketClient

import configManager
import logManager
from HueObjects import Sensor
from functions.core import nextFreeId
from functions.rules import rulesProcessor
from sensors.discover import addHueMotionSensor

bridgeConfig = configManager.bridgeConfig.yaml_config
logging = logManager.logger.get_logger(__name__)
devicesIds: dict[str, dict[str, weakref.ReferenceType]] = {"sensors": {}, "lights": {}}
motionSensors = ["TRADFRI motion sensor", "lumi.sensor_motion", "lumi.vibration.aq1"]

def getObject(resource: str, id: str) -> Union[Sensor.Sensor, bool]:
    """
    Retrieve an object from the cache or bridge configuration.

    Args:
        resource (str): The type of resource (e.g., 'sensors', 'lights').
        id (str): The ID of the resource.

    Returns:
        Union[Sensor.Sensor, bool]: The sensor object if found, otherwise False.
    """
    if id in devicesIds[resource]:
        logging.debug(f"Cache Hit for {resource} {id}")
        obj = devicesIds[resource][id]()
        if obj is None:
            del devicesIds[resource][id]
            return False
        return obj
    else:
        for key, device in bridgeConfig[resource].items():
            if device.protocol == "deconz" and device.protocol_cfg["deconzId"] == id:
                devicesIds[resource][id] = weakref.ref(device)
                logging.debug(f"Cache Miss for {resource} {id}")
                return device
        logging.debug(f"Device not found for {resource} {id}")
        return False

def longPressButton(sensor: Sensor.Sensor, buttonevent: int) -> None:
    """
    Handle long press button events.

    Args:
        sensor (Sensor.Sensor): The sensor object.
        buttonevent (int): The button event code.
    """
    logging.info("Long press detected")
    sleep(1)
    while sensor.state["buttonevent"] == buttonevent:
        logging.info("Still pressed")
        current_time = datetime.now()
        sensor.dxState["lastupdated"] = current_time
        rulesProcessor(sensor, current_time)
        sleep(0.5)
    return

def scanDeconz() -> None:
    """
    Scan for deconz sensors and register them in the bridge configuration.
    """
    deconzConf = bridgeConfig["config"]["deconz"]
    try:
        deconz_config = requests.get(f"http://{deconzConf['deconzHost']}:{deconzConf['deconzPort']}/api/{deconzConf['deconzUser']}/config").json()
        deconzConf["websocketport"] = deconz_config["websocketport"]
    except requests.RequestException as e:
        logging.error(f"Failed to get deconz config: {e}")
        return

    try:
        deconz_sensors = requests.get(f"http://{deconzConf['deconzHost']}:{deconzConf['deconzPort']}/api/{deconzConf['deconzUser']}/sensors").json()
    except requests.RequestException as e:
        logging.error(f"Failed to get deconz sensors: {e}")
        return

    for id, sensor in deconz_sensors.items():
        if not getObject("sensors", id):
            new_sensor_id = nextFreeId(bridgeConfig, "sensors")
            if sensor["modelid"] in motionSensors:
                logging.info("Register motion sensor as Philips Motion Sensor")
                addHueMotionSensor(sensor["name"], "deconz", {"lightSensor": "on", "deconzId": id, "modelid": sensor["modelid"]})
            elif sensor["modelid"] == "lumi.sensor_motion.aq2":
                if sensor["type"] == "ZHALightLevel":
                    logging.info("Register new Xiaomi light sensor")
                    lightSensor = {
                        "name": f"Hue ambient light {sensor['name'][:14]}",
                        "id_v1": new_sensor_id,
                        "protocol": "deconz",
                        "modelid": "SML001",
                        "type": "ZLLLightLevel",
                        "protocol_cfg": {"deconzId": id},
                        "uniqueid": f"00:17:88:01:02:{sensor['uniqueid'][12:]}"
                    }
                    bridgeConfig["sensors"][new_sensor_id] = Sensor.Sensor(lightSensor)
                elif sensor["type"] == "ZHAPresence":
                    logging.info("Register new Xiaomi motion sensor")
                    motion_sensor = {
                        "name": f"Hue motion {sensor['name'][:21]}",
                        "id_v1": new_sensor_id,
                        "protocol": "deconz",
                        "modelid": "SML001",
                        "type": "ZLLPresence",
                        "protocol_cfg": {"deconzId": id},
                        "uniqueid": f"00:17:88:01:02:{sensor['uniqueid'][12:]}"
                    }
                    bridgeConfig["sensors"][new_sensor_id] = Sensor.Sensor(motion_sensor)
                    new_sensor_id = nextFreeId(bridgeConfig, "sensors")
                    temp_sensor = {
                        "name": f"Hue temperature {sensor['name'][:16]}",
                        "id_v1": new_sensor_id,
                        "protocol": "deconz",
                        "modelid": "SML001",
                        "type": "ZLLTemperature",
                        "protocol_cfg": {"deconzId": "none", "id_v1": new_sensor_id},
                        "uniqueid": f"00:17:88:01:02:{sensor['uniqueid'][:-1]}2"
                    }
                    bridgeConfig["sensors"][new_sensor_id] = Sensor.Sensor(temp_sensor)
            elif sensor["modelid"] not in ["PHDL00"]:
                logging.info(f"Register new sensor {sensor['name']}")
                sensor.update({"protocol": "deconz", "protocol_cfg": {"deconzId": id}, "id_v1": new_sensor_id})
                bridgeConfig["sensors"][new_sensor_id] = Sensor.Sensor(sensor)

def websocketClient() -> None:
    """
    Establish a WebSocket connection to deconz and process incoming messages.
    """
    scanDeconz()
    if "websocketport" not in bridgeConfig["config"]["deconz"]:
        return

    class EchoClient(WebSocketClient):
        def opened(self) -> None:
            self.send("hello")

        def closed(self, code: int, reason: Union[str, None] = None) -> None:
            logging.info(f"deconz websocket disconnected: {code}, {reason}")
            del bridgeConfig["config"]["deconz"]["websocketport"]

        def received_message(self, m: Any) -> None:
            logging.info(m)
            message = json.loads(str(m))
            try:
                if message["r"] == "sensors":
                    bridgeSensor = getObject("sensors", message["id"])
                    if isinstance(bridgeSensor, Sensor.Sensor) and "config" in message and bridgeSensor.config["on"]:
                        bridgeSensor.config.update(message["config"])
                    elif isinstance(bridgeSensor, Sensor.Sensor) and "state" in message and message["state"] and bridgeSensor.config["on"]:
                        if bridgeSensor.modelid == "SML001" and "lightSensor" in bridgeSensor.protocol_cfg:
                            lightSensor = None
                            for key, sensor in bridgeConfig["sensors"].items():
                                if sensor.type == "ZLLLightLevel" and sensor.uniqueid == bridgeSensor.uniqueid[:-1] + "0":
                                    lightSensor = sensor
                                    break

                            if lightSensor:
                                if lightSensor.protocol_cfg["lightSensor"] == "no":
                                    lightSensor.state["dark"] = True
                                else:
                                    lightSensor.state["dark"] = not bridgeConfig["sensors"]["1"].state["daylight"]
                                lightSensor.state["lightlevel"] = 6000 if lightSensor.state["dark"] else 25000
                                lightSensor.state["daylight"] = not lightSensor.state["dark"]
                                lightSensor.state["lastupdated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
                                if "dark" in message["state"]:
                                    del message["state"]["dark"]

                        if bridgeSensor.modelid == "SML001" and "lightlevel" in message["state"]:
                            message["state"]["dark"] = message["state"]["lightlevel"] <= bridgeSensor.config["tholddark"]

                        bridgeSensor.state.update(message["state"])
                        current_time = datetime.now()
                        for key in message["state"].keys():
                            bridgeSensor.dxState[key] = current_time
                        rulesProcessor(bridgeSensor, current_time)

                        if "buttonevent" in message["state"] and bridgeSensor.modelid in ["TRADFRI remote control", "RWL021", "TRADFRI on/off switch"]:
                            if message["state"]["buttonevent"] in [1001, 2001, 3001, 4001, 5001]:
                                Thread(target=longPressButton, args=[bridgeSensor, message["state"]["buttonevent"]]).start()
                        if "presence" in message["state"] and message["state"]["presence"] and bridgeConfig["config"]["alarm"]["enabled"] and bridgeConfig["config"]["alarm"]["lasttriggered"] + 300 < datetime.now().timestamp():
                            logging.info("Alarm triggered, sending email...")
                            try:
                                requests.post("https://diyhue.org/cdn/mailNotify.php", json={"to": bridgeConfig["config"]["alarm"]["email"], "sensor": bridgeSensor.name})
                            except requests.RequestException as e:
                                logging.error(f"Failed to send alarm email: {e}")
                            bridgeConfig["config"]["alarm"]["lasttriggered"] = int(datetime.now().timestamp())
                elif message["r"] == "lights":
                    bridgeLightId = getObject("lights", message["id"])
                    if not isinstance(bridgeLightId, bool) and "state" in message and "colormode" not in message["state"]:
                        bridgeLightId.state.update(message["state"])
            except Exception as e:
                logging.error(f"Unable to process the request: {e}")

    try:
        ws = EchoClient(f'ws://{bridgeConfig["config"]["deconz"]["deconzHost"]}:{bridgeConfig["config"]["deconz"]["websocketport"]}')
        ws.connect()
        ws.run_forever()
    except KeyboardInterrupt:
        ws.close()
    except Exception as e:
        logging.error(f"WebSocket connection error: {e}")
