import logManager
import configManager
from HueObjects import Sensor
import random
from functions.core import nextFreeId
from typing import Dict, Any, Optional

logging = logManager.logger.get_logger(__name__)
bridgeConfig = configManager.bridgeConfig.yaml_config

def generate_unique_id() -> str:
    """
    Generate a unique ID for a sensor.
    
    Returns:
        str: A unique ID string.
    """
    rand_bytes = [random.randrange(0, 256) for _ in range(3)]
    return "00:17:88:01:03:%02x:%02x:%02x" % tuple(rand_bytes)

def addHueMotionSensor(name: str, protocol: str, protocol_cfg: Dict[str, Any]) -> None:
    """
    Add a Hue motion sensor to the bridge configuration.
    
    Args:
        name (str): The name of the sensor.
        protocol (str): The protocol used by the sensor.
        protocol_cfg (Dict[str, Any]): The protocol configuration.
    """
    try:
        uniqueid = generate_unique_id()
        sensor_types = [
            ("Hue motion " + name[:21], "ZLLPresence", "-02-0406"),
            ("Hue ambient light " + name[:14], "ZLLLightLevel", "-02-0400"),
            ("Hue temperature " + name[:16], "ZLLTemperature", "-02-0402")
        ]
        for sensor_name, sensor_type, sensor_suffix in sensor_types:
            sensor_id = nextFreeId(bridgeConfig, "sensors")
            sensor_data = {
                "name": sensor_name,
                "id_v1": sensor_id,
                "protocol": protocol,
                "modelid": "SML001",
                "type": sensor_type,
                "protocol_cfg": protocol_cfg,
                "uniqueid": uniqueid + sensor_suffix
            }
            bridgeConfig["sensors"][sensor_id] = Sensor.Sensor(sensor_data)
        logging.info(f"Successfully added Hue motion sensor '{name}' with unique ID '{uniqueid}'.")
    except KeyError as e:
        logging.error(f"Key error when adding Hue motion sensor '{name}': {e}")
    except Exception as e:
        logging.error(f"Failed to add Hue motion sensor '{name}': {e}")

def addHueSwitch(uniqueid: str, sensorsType: str) -> Optional[Sensor.Sensor]:
    """
    Add a Hue switch to the bridge configuration.
    
    Args:
        uniqueid (str): The unique ID of the switch.
        sensorsType (str): The type of the switch.
    
    Returns:
        Optional[Sensor.Sensor]: The added switch sensor object, or None if an error occurred.
    """
    try:
        new_sensor_id = nextFreeId(bridgeConfig, "sensors")
        if not uniqueid:
            uniqueid = "00:17:88:01:02:" + (f"0{new_sensor_id}" if len(new_sensor_id) == 1 else new_sensor_id) + ":4d:c6-02-fc00"
        deviceData = {
            "id_v1": new_sensor_id,
            "state": {"buttonevent": 0, "lastupdated": "none"},
            "config": {"on": True, "battery": 100, "reachable": True},
            "name": "Dimmer Switch" if sensorsType == "ZLLSwitch" else "Tap Switch",
            "type": sensorsType,
            "modelid": "RWL021" if sensorsType == "ZLLSwitch" else "ZGPSWITCH",
            "manufacturername": "Philips",
            "swversion": "5.45.1.17846" if sensorsType == "ZLLSwitch" else "",
            "uniqueid": uniqueid,
            "protocol": "native",
        }
        bridgeConfig["sensors"][new_sensor_id] = Sensor.Sensor(deviceData)
        logging.info(f"Successfully added Hue switch '{deviceData['name']}' with unique ID '{uniqueid}'.")
        return bridgeConfig["sensors"][new_sensor_id]
    except KeyError as e:
        logging.error(f"Key error when adding Hue switch: {e}")
    except Exception as e:
        logging.error(f"Failed to add Hue switch: {e}")
        return None

def addHueRotarySwitch(protocol_cfg: Dict[str, Any]) -> None:
    """
    Add a Hue rotary switch to the bridge configuration.
    
    Args:
        protocol_cfg (Dict[str, Any]): The protocol configuration.
    """
    try:
        uniqueid = generate_unique_id()
        sensor_types = [
            ("Hue tap dial switch", "ZLLSwitch", "-02-0406"),
            ("Hue tap dial switch", "ZLLRelativeRotary", "-02-0406")
        ]
        for sensor_name, sensor_type, sensor_suffix in sensor_types:
            sensor_id = nextFreeId(bridgeConfig, "sensors")
            sensor_data = {
                "name": sensor_name,
                "id_v1": sensor_id,
                "modelid": "RDM002",
                "type": sensor_type,
                "protocol_cfg": protocol_cfg,
                "uniqueid": uniqueid + sensor_suffix
            }
            bridgeConfig["sensors"][sensor_id] = Sensor.Sensor(sensor_data)
        logging.info(f"Successfully added Hue rotary switch with unique ID '{uniqueid}'.")
    except KeyError as e:
        logging.error(f"Key error when adding Hue rotary switch: {e}")
    except Exception as e:
        logging.error(f"Failed to add Hue rotary switch: {e}")
