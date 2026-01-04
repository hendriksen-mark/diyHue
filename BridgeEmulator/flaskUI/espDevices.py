import configManager
import logManager
from flask_restful import Resource
from flask import request
from functions.rules import rulesProcessor
from sensors.discover import addHueMotionSensor, addHueSwitch, addHueRotarySwitch
from datetime import datetime, timezone
from threading import Thread
from time import sleep
from functions.behavior_instance import checkBehaviorInstances
from typing import Union
from HueObjects import Sensor

logging = logManager.logger.get_logger(__name__)

bridgeConfig = configManager.bridgeConfig.yaml_config


def noMotion(sensor: str) -> None:
    """
    Monitor the sensor for no motion and update its state after 60 seconds of inactivity.

    Args:
        sensor (str): The sensor identifier.

    Returns:
        None
    """
    sensor: Sensor.Sensor = bridgeConfig["sensors"][sensor]
    sensor.protocol_cfg["threaded"] = True
    logging.info("Monitor the sensor for no motion")

    while (datetime.now() - sensor.dxState["presence"]).total_seconds() < 60:
        sleep(1)
    sensor.state["presence"] = False
    current_time = datetime.now()
    sensor.dxState["presence"] = current_time
    rulesProcessor(sensor, current_time)
    sensor.protocol_cfg["threaded"] = False


class Switch(Resource):
    def get(self) -> dict[str, Union[str, dict[str, str]]]:
        """
        Handle GET requests to register or update devices based on the provided arguments.

        Args:
            None

        Returns:
            dict[str, Union[str, dict[str, str]]]: The result of the operation.
        """
        args = request.args
        if "mac" not in args:
            return {"fail": "missing mac address"}

        current_time = datetime.now()
        mac = args["mac"]

        if "devicetype" in args:  # device registration if is new
            if self.is_device_new(mac):
                return self.register_device(args, mac)
            else:
                return {"fail": "device already registered"}
        else:
            return self.update_device(args, mac, current_time)

    def post(self) -> dict[str, Union[str, dict[str, str]]]:
        """
        Handle POST requests with JSON body to register or update devices.
        More efficient than GET with query parameters.

        Args:
            None

        Returns:
            dict[str, Union[str, dict[str, str]]]: The result of the operation.
        """
        try:
            data = request.get_json()
            if not data:
                return {"fail": "invalid json"}
            
            if "mac" not in data:
                return {"fail": "missing mac address"}

            current_time = datetime.now()
            mac = data["mac"]

            if "devicetype" in data:  # device registration if is new
                if self.is_device_new(mac):
                    return self.register_device(data, mac)
                else:
                    return {"fail": "device already registered"}
            else:
                return self.update_device(data, mac, current_time)
        except Exception as e:
            logging.error(f"Error processing POST request: {e}")
            return {"fail": "error processing request"}

    def is_device_new(self, mac: str) -> bool:
        """
        Check if the device with the given MAC address is new.

        Args:
            mac (str): The MAC address of the device.

        Returns:
            bool: True if the device is new, False otherwise.
        """
        return all(
            obj.protocol_cfg.get("mac") != mac for obj in bridgeConfig["sensors"].values()
        )

    def register_device(self, args: dict[str, str], mac: str) -> dict[str, str]:
        """
        Register a new device based on the provided arguments and MAC address.

        Args:
            args (dict[str, str]): The arguments provided in the request.
            mac (str): The MAC address of the device.

        Returns:
            dict[str, str]: The result of the registration operation.
        """
        device_type = args["devicetype"]
        if device_type in ["ZLLSwitch", "ZGPSwitch"]:
            sensor = addHueSwitch("", device_type)
        elif device_type == "ZLLPresence":
            sensor = addHueMotionSensor("Hue Motion Sensor", "native", {"mac": mac, "threaded": False})
        elif device_type == "ZLLRelativeRotary":
            sensor = addHueRotarySwitch({"mac": mac})
        else:
            return {"fail": "unknown device"}

        sensor.protocol_cfg["mac"] = mac
        return {"success": "device registered"}

    def update_device(self, args: dict[str, str], mac: str, current_time: datetime) -> dict[str, str]:
        """
        Update an existing device based on the provided arguments and MAC address.

        Args:
            args (dict[str, str]): The arguments provided in the request.
            mac (str): The MAC address of the device.
            current_time (datetime): The current time.

        Returns:
            dict[str, str]: The result of the update operation.
        """
        for device, obj in bridgeConfig["sensors"].items():
            obj: Sensor.Sensor = obj
            if obj.protocol_cfg.get("mac") == mac:
                self.apply_device_updates(args, obj, current_time)
                return {"success": "command applied"}
        return {"fail": "device not found"}

    def apply_device_updates(self, args: dict[str, str], obj: Sensor.Sensor, current_time: datetime) -> None:
        """
        Apply updates to the device based on its type and the provided arguments.

        Args:
            args (dict[str, str]): The arguments provided in the request.
            obj (Any): The device object.
            current_time (datetime): The current time.

        Returns:
            None
        """
        update_methods = {
            "ZLLLightLevel": self.update_light_level,
            "ZLLPresence": self.update_presence,
            "ZLLTemperature": self.update_temperature,
            "ZLLSwitch": self.update_switch,
            "ZGPSwitch": self.update_switch,
            "ZLLRelativeRotary": self.update_rotary,
        }

        update_method = update_methods.get(obj.type)
        if update_method:
            update_method(args, obj, current_time)
            obj.dxState["lastupdated"] = current_time
            obj.state["lastupdated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
            rulesProcessor(obj, current_time)
            checkBehaviorInstances(obj)
        else:
            return {"fail": "unknown device"}

    def update_light_level(self, args: dict[str, str], obj: Sensor.Sensor, current_time: datetime) -> None:
        """
        Update the light level sensor based on the provided arguments.

        Args:
            args (dict[str, str]): The arguments provided in the request.
            obj (Any): The device object.
            current_time (datetime): The current time.

        Returns:
            None
        """
        if "lightlevel" in args:
            obj.state["lightlevel"] = int(args["lightlevel"])
            obj.dxState["lightlevel"] = current_time
        if "dark" in args:
            dark = args["dark"].lower() == "true"
            if obj.state["dark"] != dark:
                obj.dxState["dark"] = current_time
                obj.state["dark"] = dark
        if "daylight" in args:
            daylight = args["daylight"].lower() == "true"
            if obj.state["daylight"] != daylight:
                obj.dxState["daylight"] = current_time
                obj.state["daylight"] = daylight

    def update_presence(self, args: dict[str, str], obj: Sensor.Sensor, current_time: datetime) -> None:
        """
        Update the presence sensor based on the provided arguments.

        Args:
            args (dict[str, str]): The arguments provided in the request.
            obj (Any): The device object.
            current_time (datetime): The current time.

        Returns:
            None
        """
        if "battery" in args:
            obj.config["battery"] = int(args["battery"])
        if "presence" in args:
            presence = args["presence"].lower() == "true"
            if obj.state["presence"] != presence:
                obj.state["presence"] = presence
                obj.dxState["presence"] = current_time
                if not obj.protocol_cfg["threaded"]:
                    Thread(target=noMotion, args=[obj]).start()

    def update_temperature(self, args: dict[str, str], obj: Sensor.Sensor, current_time: datetime) -> None:
        """
        Update the temperature sensor based on the provided arguments.

        Args:
            args (dict[str, str]): The arguments provided in the request.
            obj (Any): The device object.
            current_time (datetime): The current time.

        Returns:
            None
        """
        if "temperature" in args:
            obj.state["temperature"] = int(args["temperature"])
            obj.dxState["temperature"] = current_time

    def update_switch(self, args: dict[str, str], obj: Sensor.Sensor, current_time: datetime) -> None:
        """
        Update the switch sensor based on the provided arguments.

        Args:
            args (dict[str, str]): The arguments provided in the request.
            obj (Any): The device object.
            current_time (datetime): The current time.

        Returns:
            None
        """
        if "button" in args:
            obj.update_attr({"state": {"buttonevent": int(args["button"])}})
            obj.dxState["buttonevent"] = current_time
        if "battery" in args:
            obj.update_attr({"config": {"battery": int(args["battery"])}})

    def update_rotary(self, args: dict[str, str], obj: Sensor.Sensor, current_time: datetime) -> None:
        """
        Update the rotary sensor based on the provided arguments.

        Args:
            args (dict[str, str]): The arguments provided in the request.
            obj (Any): The device object.
            current_time (datetime): The current time.

        Returns:
            None
        """
        if "rotary" in args:
            obj.state["rotaryevent"] = int(args["rotary"])
            obj.state["expectedrotation"] = int(args["rotation"])
            obj.state["expectedeventduration"] = int(args["duration"])
            obj.dxState["rotaryevent"] = current_time
        if "battery" in args:
            obj.config["battery"] = int(args["battery"])
