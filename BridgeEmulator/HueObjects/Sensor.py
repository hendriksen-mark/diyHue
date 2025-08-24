import uuid
from datetime import datetime, timezone
from copy import deepcopy
from typing import Any, Optional

import logManager
from sensors.sensor_types import sensorTypes
from HueObjects import genV2Uuid, StreamEvent

logging = logManager.logger.get_logger(__name__)

class Sensor:
    def __init__(self, data: dict[str, Any]) -> None:
        if data["modelid"] in sensorTypes:
            sensor_type = sensorTypes[data["modelid"]][data["type"]]
            data.setdefault("manufacturername", sensor_type["static"]["manufacturername"])
            data.setdefault("config", deepcopy(sensor_type["config"]))
            data.setdefault("state", deepcopy(sensor_type["state"]))
            data.setdefault("swversion", sensor_type["static"]["swversion"])
        
        data.setdefault("config", {})
        data["config"].setdefault("reachable", True)
        data["config"].setdefault("on", True)
        data.setdefault("state", {})
        data["state"].setdefault("lastupdated", "none")

        self.name: str = data["name"]
        self.id_v1: str = data["id_v1"]
        self.id_v2: str = data.get("id_v2", genV2Uuid())
        self.config: dict[str, Any] = data["config"]
        self.modelid: str = data["modelid"]
        self.manufacturername: str = data.get("manufacturername", "Philips")
        self.protocol: str = data.get("protocol", "none")
        self.protocol_cfg: dict[str, Any] = data.get("protocol_cfg", {})
        self.type: str = data["type"]
        self.state: dict[str, Any] = data["state"]
        self.dxState: dict[str, datetime] = {state: datetime.now() for state in data["state"].keys()}
        self.swversion: str = data.get("swversion")
        self.recycle: bool = data.get("recycle", False)
        self.uniqueid: str = data.get("uniqueid")

        if self.getDevice() is not None:
            streamMessage = {
                "creationtime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "data": [{"id": self.id_v2, "type": "device"}],
                "id": str(uuid.uuid4()),
                "type": "add"
            }
            streamMessage["data"][0].update(self.getDevice())
            StreamEvent(streamMessage)

    def __del__(self) -> None:
        if self.modelid in ["SML001", "RWL022"]:
            streamMessage = {
                "creationtime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "data": [{"id": self.getDevice()["id"], "type": "device"}],
                "id": str(uuid.uuid4()),
                "type": "delete"
            }
            streamMessage["id_v1"] = "/sensors/" + self.id_v1
            StreamEvent(streamMessage)
        logging.info(self.name + " sensor was destroyed.")

    def setV1State(self, state: dict[str, Any]) -> None:
        self.state.update(state)

    def getBridgeHome(self) -> dict[str, str]:
        if self.modelid == "SML001":
            rtype = {
                "ZLLPresence": "motion",
                "ZLLLightLevel": "light_level",
                "ZLLTemperature": "temperature"
            }.get(self.type, 'device')
            return {"rid": self.id_v2, "rtype": rtype}
        return {"rid": self.id_v2, "rtype": 'device'}

    def getV1Api(self) -> dict[str, Any]:
        result: dict[str, Any] = sensorTypes.get(self.modelid, {}).get(self.type, {}).get("static", {})
        result.update({
            "state": self.state,
            "config": self.config,
            "name": self.name,
            "type": self.type,
            "modelid": self.modelid,
            "manufacturername": self.manufacturername,
            "swversion": self.swversion,
            "uniqueid": self.uniqueid,
            "recycle": self.recycle
        })
        return result

    def getObjectPath(self) -> dict[str, str]:
        return {"resource": "sensors", "id": self.id_v1}

    def getDevice(self) -> Optional[dict[str, Any]]:
        if self.modelid == "SML001" and self.type == "ZLLPresence":
            return {
                "id": self.id_v2,
                "id_v1": "/sensors/" + self.id_v1,
                "type": "device",
                "identify": {},
                "metadata": {"archetype": "unknown_archetype", "name": self.name},
                "product_data": {
                    "certified": True,
                    "manufacturer_name": "Signify Netherlands B.V.",
                    "model_id": self.modelid,
                    "product_archetype": "unknown_archetype",
                    "product_name": "Hue motion sensor",
                    "software_version": "1.1.27575"
                },
                "services": [
                    {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'motion')), "rtype": "motion"},
                    {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'device_power')), "rtype": "device_power"},
                    {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'zigbee_connectivity')), "rtype": "zigbee_connectivity"},
                    {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'light_level')), "rtype": "light_level"},
                    {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'temperature')), "rtype": "temperature"}
                ]
            }
        elif self.modelid in ["RWL022", "RWL021", "RWL020"]:
            return {
                "id": self.id_v2,
                "id_v1": "/sensors/" + self.id_v1,
                "type": "device",
                "identify": {},
                "metadata": {"archetype": "unknown_archetype", "name": self.name},
                "product_data": {
                    "model_id": self.modelid,
                    "manufacturer_name": "Signify Netherlands B.V.",
                    "product_name": "Hue dimmer switch",
                    "product_archetype": "unknown_archetype",
                    "certified": True,
                    "software_version": "2.44.0",
                    "hardware_platform_type": "100b-119"
                },
                "services": [
                    {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'button1')), "rtype": "button"},
                    {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'button2')), "rtype": "button"},
                    {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'button3')), "rtype": "button"},
                    {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'button4')), "rtype": "button"},
                    {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'device_power')), "rtype": "device_power"},
                    {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'zigbee_connectivity')), "rtype": "zigbee_connectivity"}
                ]
            }
        elif self.modelid == "RDM002":
            services = [
                {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'button1')), "rtype": "button"},
                {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'button2')), "rtype": "button"},
                {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'button3')), "rtype": "button"},
                {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'button4')), "rtype": "button"},
                {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'device_power')), "rtype": "device_power"},
                {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'zigbee_connectivity')), "rtype": "zigbee_connectivity"}
            ]
            if self.type == "ZLLRelativeRotary":
                services = [
                    {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'relative_rotary')), "rtype": "relative_rotary"},
                    {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'device_power')), "rtype": "device_power"},
                    {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'zigbee_connectivity')), "rtype": "zigbee_connectivity"}
                ]
            return {
                "id": self.id_v2,
                "id_v1": "/sensors/" + self.id_v1,
                "type": "device",
                "identify": {},
                "metadata": {"archetype": "unknown_archetype", "name": self.name},
                "product_data": {
                    "model_id": self.modelid,
                    "manufacturer_name": "Signify Netherlands B.V.",
                    "product_name": "Hue tap dial switch",
                    "product_archetype": "unknown_archetype",
                    "certified": True,
                    "software_version": "2.59.25",
                    "hardware_platform_type": "100b-119"
                },
                "services": services
            }
        elif self.modelid == "SOC001":
            return {
                "id": self.id_v2,
                "id_v1": "/sensors/" + self.id_v1,
                "type": "device",
                "identify": {},
                "metadata": {"archetype": "unknown_archetype", "name": self.name},
                "product_data": {
                    "model_id": self.modelid,
                    "manufacturer_name": "Signify Netherlands B.V.",
                    "product_name": "Hue secure contact sensor",
                    "product_archetype": "unknown_archetype",
                    "certified": True,
                    "software_version": "2.67.9",
                    "hardware_platform_type": "100b-125"
                },
                "services": [
                    {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'contact')), "rtype": "contact"},
                    {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'device_power')), "rtype": "device_power"},
                    {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'zigbee_connectivity')), "rtype": "zigbee_connectivity"}
                ]
            }
        return None

    def getMotion(self) -> Optional[dict[str, Any]]:
        if self.modelid == "SML001" and self.type == "ZLLPresence":
            return {
                "enabled": self.config["on"],
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'motion')),
                "id_v1": "/sensors/" + self.id_v1,
                "motion": {
                    "motion_report": {
                        "changed": self.state["lastupdated"],
                        "motion": bool(self.state["presence"]),
                    }
                },
                "sensitivity": {
                    "status": "set",
                    "sensitivity": 2,
                    "sensitivity_max": 2
                },
                "owner": {
                    "rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'device')),
                    "rtype": "device"
                },
                "type": "motion"
            }
        return None

    def getTemperature(self) -> Optional[dict[str, Any]]:
        if self.modelid == "SML001" and self.type == "ZLLTemperature":
            return {
                "enabled": self.config["on"],
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'temperature')),
                "id_v1": "/sensors/" + self.id_v1,
                "temperature": {
                    "temperature_report": {
                        "changed": self.state["lastupdated"],
                        "temperature": self.state["temperature"] / 100 if isinstance(self.state["temperature"], int) else self.state["temperature"]
                    }
                },
                "owner": {
                    "rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'device')),
                    "rtype": "device"
                },
                "type": "temperature"
            }
        return None

    def getLightlevel(self) -> Optional[dict[str, Any]]:
        if self.modelid == "SML001" and self.type == "ZLLLightLevel":
            return {
                "enabled": self.config["on"],
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'light_level')),
                "id_v1": "/sensors/" + self.id_v1,
                "light": {
                    "light_level_report": {
                        "changed": self.state["lastupdated"],
                        "light_level": self.state["lightlevel"]
                    }
                },
                "owner": {
                    "rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'device')),
                    "rtype": "device"
                },
                "type": "light_level"
            }
        return None

    def getZigBee(self) -> Optional[dict[str, Any]]:
        if self.modelid == "SML001" and self.type != "ZLLPresence":
            return None
        if not self.uniqueid:
            return None
        return {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'zigbee_connectivity')),
            "id_v1": "/sensors/" + self.id_v1,
            "owner": {"rid": self.id_v2, "rtype": "device"},
            "type": "zigbee_connectivity",
            "mac_address": self.uniqueid[:23],
            "status": "connected"
        }

    def getButtons(self) -> Optional[dict[str, Any]]:
        if self.modelid in ["RWL022", "RWL021", "RWL020", "RDM002"] and self.type != "ZLLRelativeRotary":
            return [
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + f'button{button + 1}')),
                    "id_v1": "/sensors/" + self.id_v1,
                    "owner": {"rid": self.id_v2, "rtype": "device"},
                    "metadata": {"control_id": button + 1},
                    "button": {
                        "last_event": "short_release",
                        "button_report": {
                            "updated": self.state["lastupdated"],
                            "event": "initial_press"
                        },
                        "repeat_interval": 800,
                        "event_values": [
                            "initial_press",
                            "repeat",
                            "short_release",
                            "long_release",
                            "long_press"
                        ]
                    },
                    "type": "button"
                } for button in range(4)
            ]
        return None

    def getRotary(self) -> Optional[dict[str, Any]]:
        if self.modelid == "RDM002" and self.type == "ZLLRelativeRotary":
            return {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'relative_rotary')),
                "id_v1": "/sensors/" + self.id_v1,
                "owner": {"rid": self.id_v2, "rtype": "device"},
                "relative_rotary": {
                    "rotary_report": {
                        "updated": self.state["lastupdated"],
                        "action": "start" if self.state["rotaryevent"] == 1 else "repeat",
                        "rotation": {
                            "direction": "right",
                            "steps": self.state["expectedrotation"],
                            "duration": self.state["expectedeventduration"]
                        }
                    }
                },
                "type": "relative_rotary"
            }
        return None

    def getDevicePower(self) -> Optional[dict[str, Any]]:
        if "battery" in self.config:
            return {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'device_power')),
                "id_v1": "/sensors/" + self.id_v1,
                "owner": {"rid": self.id_v2, "rtype": "device"},
                "power_state": {
                    "battery_level": self.config["battery"],
                    "battery_state": "normal"
                },
                "type": "device_power"
            }
        return None

    def getContact(self) -> Optional[dict[str, Any]]:
        if self.modelid == "SOC001":
            return {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'contact')),
                "id_v1": "/sensors/" + self.id_v1,
                "owner": {"rid": self.id_v2, "rtype": "device"},
                "contact_report": {
                    "changed": "2023-11-08T20:32:24.507Z",
                    "state": "contact"
                },
                "type": "contact"
            }
        return None

    def update_attr(self, newdata: dict[str, Any]) -> None:
        if self.id_v1 == "1" and "config" in newdata:  # manage daylight sensor
            if "long" in newdata["config"] and "lat" in newdata["config"]:
                self.config["configured"] = True
                self.protocol_cfg = {
                    "long": float(newdata["config"]["long"][:-1]),
                    "lat": float(newdata["config"]["lat"][:-1])
                }
                return
        for key, value in newdata.items():
            updateAttribute = getattr(self, key)
            if isinstance(updateAttribute, dict):
                updateAttribute.update(value)
                setattr(self, key, updateAttribute)
            else:
                setattr(self, key, value)
        streamMessage = {
            "creationtime": datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data": [self.getButtons()],
            "id": str(uuid.uuid4()),
            "type": "update"
        }
        StreamEvent(streamMessage)

    def save(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "id_v1": self.id_v1,
            "id_v2": self.id_v2,
            "state": self.state,
            "config": self.config,
            "type": self.type,
            "modelid": self.modelid,
            "manufacturername": self.manufacturername,
            "uniqueid": self.uniqueid,
            "swversion": self.swversion,
            "protocol": self.protocol,
            "protocol_cfg": self.protocol_cfg
        }
