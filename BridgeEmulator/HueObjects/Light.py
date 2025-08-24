import uuid
import logManager
from lights.light_types import lightTypes, archetype
from lights.protocols import protocols
from HueObjects import genV2Uuid, incProcess, v1StateToV2, generate_unique_id, v2StateToV1, StreamEvent
from datetime import datetime, timezone
from copy import deepcopy
from time import sleep
from typing import Any, List, Optional

logging = logManager.logger.get_logger(__name__)

class Light:
    def __init__(self, data: dict[str, Any]) -> None:
        self.name: str = data["name"]
        self.modelid: str = data["modelid"]
        self.id_v1: str = data["id_v1"]
        self.id_v2: str = data.get("id_v2", genV2Uuid())
        self.uniqueid: str = data.get("uniqueid", generate_unique_id())
        self.state: dict[str, Any] = data.get("state", deepcopy(lightTypes[self.modelid]["state"]))
        self.protocol: str = data.get("protocol", "dummy")
        self.config: dict[str, Any] = data.get("config", deepcopy(lightTypes[self.modelid]["config"]))
        self.protocol_cfg: dict[str, Any] = data.get("protocol_cfg", {})
        self.streaming: bool = False
        self.dynamics: dict[str, Any] = deepcopy(lightTypes[self.modelid]["dynamics"])
        self.effect: str = "no_effect"
        self.function: str = data.get("function", "mixed")
        self.controlled_service: str = data.get("controlled_service", "manual")

        self._initialize_stream_events()

    def _initialize_stream_events(self) -> None:
        self._send_stream_event(self.getV2Entertainment(), "add")
        self._send_stream_event(self.getZigBee(), "add")
        self._send_stream_event(self.getV2Api(), "add")
        self._send_stream_event(self.getDevice(), "add")

    def __del__(self) -> None:
        self._send_stream_event({"id": self.id_v2, "type": "light"}, "delete")
        self._send_stream_event({"id": self.getDevice()["id"], "type": "device"}, "delete")
        self._send_stream_event({"id": self.getZigBee()["id"], "type": "zigbee_connectivity"}, "delete")
        self._send_stream_event({"id": self.getV2Entertainment()["id"], "type": "entertainment"}, "delete")
        logging.info(f"{self.name} light was destroyed.")

    def update_attr(self, newdata: dict[str, Any]) -> None:
        for key, value in newdata.items():
            updateAttribute = getattr(self, key, None)
            if isinstance(updateAttribute, dict):
                updateAttribute.update(value)
                setattr(self, key, updateAttribute)
            else:
                setattr(self, key, value)
        self._send_stream_event(self.getDevice(), "update")

    def getV1Api(self) -> dict[str, Any]:
        result = deepcopy(lightTypes[self.modelid]["v1_static"])
        result["config"] = self.config
        result["state"] = {"on": self.state["on"]}
        if "bri" in self.state and self.modelid not in ["LOM001", "LOM004", "LOM010"]:
            result["state"]["bri"] = int(self.state["bri"]) if self.state["bri"] is not None else 1
        if "ct" in self.state and self.modelid not in ["LOM001", "LOM004", "LOM010", "LTW001", "LLC010"]:
            result["state"]["ct"] = self.state["ct"]
            result["state"]["colormode"] = self.state["colormode"]
        if "xy" in self.state and self.modelid not in ["LOM001", "LOM004", "LOM010", "LTW001", "LWB010"]:
            result["state"]["xy"] = self.state["xy"]
            result["state"]["hue"] = self.state["hue"]
            result["state"]["sat"] = self.state["sat"]
            result["state"]["colormode"] = self.state["colormode"]
        result["state"]["alert"] = self.state["alert"]
        if "mode" in self.state:
            result["state"]["mode"] = self.state["mode"]
        result["state"]["reachable"] = self.state["reachable"]
        if self.modelid in ["LCX002", "915005987201", "LCX004", "LCX006"]:
            result["state"]["gradient"] = {"points": self.state["gradient"]["points"], "points_capable": self.protocol_cfg["points_capable"]}
        result["modelid"] = self.modelid
        result["name"] = self.name
        result["uniqueid"] = self.uniqueid
        return result

    def updateLightState(self, state: dict[str, Any]) -> None:
        if "xy" in state and "xy" in self.state:
            self.state["colormode"] = "xy"
        elif "ct" in state and "ct" in self.state:
            self.state["colormode"] = "ct"
        elif ("hue" in state or "sat" in state) and "hue" in self.state:
            self.state["colormode"] = "hs"

    def setV1State(self, state: dict[str, Any], advertise: bool = True) -> None:
        if "lights" not in state:
            state = incProcess(self.state, state)
            self.updateLightState(state)
            for key, value in state.items():
                if key in self.state:
                    logging.debug(f"Set '{key}' to '{value}' for {self.name}")
                    self.state[key] = value
                if key in self.config:
                    if key == "archetype":
                        self.config[key] = value.replace("_", "")
                    else:
                        self.config[key] = value
                if key == "name":
                    self.name = value
                if key == "function":
                    self.function = value
            if "bri" in state:
                if "min_bri" in self.protocol_cfg and self.protocol_cfg["min_bri"] > state["bri"]:
                    state["bri"] = self.protocol_cfg["min_bri"]
                if "max_bri" in self.protocol_cfg and self.protocol_cfg["max_bri"] < state["bri"]:
                    state["bri"] = self.protocol_cfg["max_bri"]

        if self.protocol not in ["dummy"]:
            for protocol in protocols:
                if "lights.protocols." + self.protocol == protocol.__name__:
                    try:
                        protocol.set_light(self, state)
                        self.state["reachable"] = True
                    except Exception as e:
                        self.state["reachable"] = False
                        logging.warning(f"{self.name} light error, details: {e}")
        if advertise:
            if "lights" in state:
                for item in state["lights"]:
                    light_state = state["lights"][item]
                    v2State = v1StateToV2(light_state)
                    self.genStreamEvent(v2State)

    def setV2State(self, state: dict[str, Any]) -> None:
        v1State = v2StateToV1(state)
        if "effects_v2" in state and "action" in state["effects_v2"]:
            v1State["effect"] = state["effects_v2"]["action"]["effect"]
            self.effect = v1State["effect"]
        if "effects" in state:
            v1State["effect"] = state["effects"]["effect"]
            self.effect = v1State["effect"]
        if "dynamics" in state and "speed" in state["dynamics"]:
            self.dynamics["speed"] = state["dynamics"]["speed"]
        if "metadata" in state:
            if "archetype" in state["metadata"]:
                v1State["archetype"] = state["metadata"]["archetype"]
            if "name" in state["metadata"]:
                v1State["name"] = state["metadata"]["name"]
            if "function" in state["metadata"]:
                v1State["function"] = state["metadata"]["function"]
        if "controlled_service" in state:
            self.controlled_service = state["controlled_service"]
            del state["controlled_service"]
        self.setV1State(v1State, advertise=False)
        self.genStreamEvent(state)

    def genStreamEvent(self, v2State: dict[str, Any]) -> None:
        streamMessage = {
            "data": [{"id": self.id_v2, "id_v1": f"/lights/{self.id_v1}", "type": "light"}],
        }
        streamMessage["data"][0].update(v2State)
        streamMessage["data"][0].update({"owner": {"rid": self.getDevice()["id"], "rtype": "device"}})
        streamMessage["data"][0].update({"service_id": self.protocol_cfg.get("light_nr", 1) - 1})
        self._send_stream_event(streamMessage["data"][0], "update")
        self._send_stream_event(self.getDevice(), "update")

    def _send_stream_event(self, data: dict[str, Any], event_type: str) -> None:
        streamMessage = {
            "creationtime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data": [data],
            "id": str(uuid.uuid4()),
            "type": event_type,
            "id_v1": f"/lights/{self.id_v1}"
        }
        StreamEvent(streamMessage)

    def getDevice(self) -> dict[str, Any]:
        result = {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'device')),
            "id_v1": f"/lights/{self.id_v1}",
            "identify": {},
            "metadata": {
                "archetype": archetype[self.config["archetype"]],
                "name": self.name
            },
            "product_data": lightTypes[self.modelid]["device"],
            "service_id": self.protocol_cfg.get("light_nr", 1) - 1,
            "services": [
                {"rid": self.id_v2, "rtype": "light"},
                {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'zigbee_connectivity')), "rtype": "zigbee_connectivity"},
                {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'entertainment')), "rtype": "entertainment"}
            ],
            "type": "device"
        }
        result["product_data"]["model_id"] = self.modelid
        return result

    def getZigBee(self) -> dict[str, Any]:
        return {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'zigbee_connectivity')),
            "id_v1": f"/lights/{self.id_v1}",
            "mac_address": self.uniqueid[:23],
            "owner": {"rid": self.getDevice()["id"], "rtype": "device"},
            "status": "connected" if self.state["reachable"] else "connectivity_issue",
            "type": "zigbee_connectivity"
        }

    def getBridgeHome(self) -> dict[str, str]:
        return {"rid": self.id_v2, "rtype": "light"}

    def getV2Api(self) -> dict[str, Any]:
        result = {
            "alert": {"action_values": ["breathe"]},
            "dynamics": self.dynamics,
            "effects": {
                "effect_values": ["no_effect", "candle", "fire"],
                "status": self.effect,
                "status_values": ["no_effect", "candle", "fire"]
            },
            "timed_effects": {},
            "identify": {},
            "id": self.id_v2,
            "id_v1": f"/lights/{self.id_v1}",
            "metadata": {"name": self.name, "function": self.function, "archetype": archetype[self.config["archetype"]]},
            "mode": "streaming" if self.state.get("mode") == "streaming" else "normal",
            "on": {"on": self.state["on"]},
            "owner": {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'device')), "rtype": "device"},
            "product_data": {"function": "mixed"},
            "signaling": {"signal_values": ["no_signal", "on_off"]},
            "powerup": {
                "preset": "last_on_state",
                "configured": True,
                "on": {"mode": "on", "on": {"on": True}},
                "dimming": {"mode": "previous"}
            },
            "service_id": self.protocol_cfg.get("light_nr", 1) - 1,
            "type": "light"
        }

        if self.modelid in ["LCX002", "915005987201", "LCX004", "LCX006"]:
            result["effects"] = {
                "effect_values": ["no_effect", "candle", "fire"],
                "status": self.effect,
                "status_values": ["no_effect", "candle", "fire"]
            }
            result["gradient"] = {"points": self.state["gradient"]["points"], "points_capable": self.protocol_cfg["points_capable"], "pixel_count": self.protocol_cfg["points_capable"],
                                  "mode": "interpolated_palette", "mode_values": ["interpolated_palette", "interpolated_palette_mirrored", "random_pixelated"]}

        if self.modelid in ["LST002", "LCT001", "LCT015", "LCX002", "915005987201", "LCX004", "LCX006", "LCA005", "LLC010"]:
            colorgamut = lightTypes[self.modelid]["v1_static"]["capabilities"]["control"]["colorgamut"]
            result["color"] = {
                "gamut": {
                    "blue": {"x": colorgamut[2][0], "y": colorgamut[2][1]},
                    "green": {"x": colorgamut[1][0], "y": colorgamut[1][1]},
                    "red": {"x": colorgamut[0][0], "y": colorgamut[0][1]}
                },
                "gamut_type": lightTypes[self.modelid]["v1_static"]["capabilities"]["control"]["colorgamuttype"],
                "xy": {"x": self.state["xy"][0], "y": self.state["xy"][1]}
            }

        if "ct" in self.state:
            result["color_temperature"] = {
                "mirek": self.state["ct"] if self.state["colormode"] == "ct" else None,
                "mirek_schema": {"mirek_maximum": 500, "mirek_minimum": 153},
                "mirek_valid": 153 < self.state["ct"] < 500 if self.state["ct"] is not None else False
            }
            result["color_temperature_delta"] = {}

        if "bri" in self.state:
            bri_value = self.state["bri"] if self.state["bri"] is not None else 1
            result["dimming"] = {
                "brightness": round(float(bri_value) / 2.54, 2),
                "min_dim_level": 0.1  # Adjust this value as needed
            }
            result["dimming_delta"] = {}

        return result

    def getV2Entertainment(self) -> dict[str, Any]:
        entertainmenUuid = str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'entertainment'))
        result = {
            "equalizer": True,
            "id": entertainmenUuid,
            "id_v1": f"/lights/{self.id_v1}",
            "proxy": lightTypes[self.modelid]["v1_static"]["capabilities"]["streaming"]["proxy"],
            "renderer": lightTypes[self.modelid]["v1_static"]["capabilities"]["streaming"]["renderer"],
            "renderer_reference": {"rid": self.id_v2, "rtype": "light"},
            "owner": {"rid": self.getDevice()["id"], "rtype": "device"},
            "segments": {"configurable": False},
            "type": "entertainment"
        }

        if self.modelid == "LCX002":
            result["segments"]["max_segments"] = 7
            result["segments"]["segments"] = [
                {"length": 2, "start": 0},
                {"length": 2, "start": 2},
                {"length": 4, "start": 4},
                {"length": 4, "start": 8},
                {"length": 4, "start": 12},
                {"length": 2, "start": 16},
                {"length": 2, "start": 18}
            ]
        elif self.modelid in ["915005987201", "LCX004", "LCX006"]:
            result["segments"]["max_segments"] = 10
            result["segments"]["segments"] = [
                {"length": 3, "start": 0},
                {"length": 4, "start": 3},
                {"length": 3, "start": 7}
            ]
        else:
            result["segments"]["max_segments"] = 1
            result["segments"]["segments"] = [{"length": 1, "start": 0}]

        return result

    def getObjectPath(self) -> dict[str, str]:
        return {"resource": "lights", "id": self.id_v1}

    def dynamicScenePlay(self, palette: dict[str, List[dict[str, Any]]], index: int) -> None:
        logging.debug(f"Start Dynamic scene play for {self.name}")
        if "dynamic_palette" in self.dynamics["status_values"]:
            self.dynamics["status"] = "dynamic_palette"
        while self.dynamics["status"] == "dynamic_palette":
            transition = int(30 / self.dynamics["speed"])
            logging.debug(f"using transition time {transition}")
            if self.modelid in ["LCT001", "LCT015", "LST002", "LCX002", "915005987201", "LCX004", "LCX006", "LCA005"]:
                if index == len(palette["color"]):
                    index = 0
                points = []
                if self.modelid in ["LCX002", "915005987201", "LCX004", "LCX006"]:
                    # for gradient lights
                    gradientIndex = index
                    for x in range(self.protocol_cfg["points_capable"]):
                        points.append(palette["color"][gradientIndex])
                        gradientIndex += 1
                        if gradientIndex == len(palette["color"]):
                            gradientIndex = 0
                    self.setV2State(
                        {"gradient": {"points": points}, "transitiontime": transition})
                else:
                    lightState = palette["color"][index]
                    # based on youtube videos, the transition is slow
                    lightState["transitiontime"] = transition
                    self.setV2State(lightState)
            elif self.modelid == "LTW001":
                if index == len(palette["color_temperature"]):
                    index = 0
                lightState = palette["color_temperature"][index]
                lightState["transitiontime"] = transition
                self.setV2State(lightState)
            else:
                if index == len(palette["dimming"]):
                    index = 0
                lightState = palette["dimming"][index]
                lightState["transitiontime"] = transition
                self.setV2State(lightState)
            sleep(transition / 10)
            index += 1
            logging.debug("Step forward dynamic scene " + self.name)
        logging.debug("Dynamic Scene " + self.name + " stopped.")

    def save(self) -> dict[str, Any]:
        result = {"id_v2": self.id_v2, "name": self.name, "modelid": self.modelid, "uniqueid": self.uniqueid, "function": self.function,
                  "state": self.state, "config": self.config, "protocol": self.protocol, "protocol_cfg": self.protocol_cfg}
        return result
