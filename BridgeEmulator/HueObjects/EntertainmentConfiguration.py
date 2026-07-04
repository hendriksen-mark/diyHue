import uuid
import logManager
import weakref
from datetime import datetime, timezone
from HueObjects import genV2Uuid, v1StateToV2, v2StateToV1, setGroupAction, StreamEvent, update_state, Light
from typing import Any, List, Optional, Union

logging = logManager.logger.get_logger(__name__)

class EntertainmentConfiguration:
    def __init__(self, data: dict[str, Any]):
        self.name: str = data.get("name", f"Group {data['id_v1']}")
        self.id_v1: str = data["id_v1"]
        self.id_v2: str = data.get("id_v2", genV2Uuid())
        self.configuration_type: str = data.get("configuration_type", "screen")
        self.lights: List[weakref.ref] = []
        self.action: dict[str, Union[bool, int, float, str, List[float]]] = {
            "on": False, "bri": 100, "hue": 0, "sat": 254, "effect": "none", "xy": [0.0, 0.0], "ct": 153, "alert": "none", "colormode": "xy"
        }
        self.sensors: List[weakref.ref] = []
        self.type: str = data.get("type", "Entertainment")
        self.locations: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
        self.stream: dict[str, Union[str, bool, None]] = {"proxymode": "auto", "proxynode": "/bridge", "active": False, "owner": None}
        self.state: dict[str, bool] = {"all_on": False, "any_on": False}
        self.dxState: dict[str, Optional[datetime]] = {"all_on": None, "any_on": None}

        self._send_stream_event(self.getV2Api(), "add")

    def __del__(self):
        self._send_stream_event({"id": self.id_v2, "type": "grouped_light"}, "delete")
        self._send_stream_event({"id": self.getV2Api()["id"], "type": "entertainment_configuration"}, "delete")
        logging.info(f"{self.name} entertainment area was destroyed.")

    def add_light(self, light: Any) -> None:
        self.lights.append(weakref.ref(light))
        self.locations[light] = [{"x": 0, "y": 0, "z": 0}]

    def update_attr(self, newdata: dict[str, Any]) -> None:
        newdata.pop("lights", None)
        newdata.pop("locations", None)
        for key, value in newdata.items():
            updateAttribute = getattr(self, key)
            if isinstance(updateAttribute, dict):
                updateAttribute.update(value)
                setattr(self, key, updateAttribute)
            else:
                setattr(self, key, value)
        self._send_stream_event(self.getV2Api(), "update")

    def getV2GroupedLight(self) -> dict[str, Any]:
        result = {
            "alert": {"action_values": ["breathe"]},
            "id": self.id_v2,
            "id_v1": f"/groups/{self.id_v1}",
            "on": {"on": update_state(self)["any_on"]},
            "dimming": {"brightness": update_state(self)["avr_bri"]},
            "dimming_delta": {},
            "color": {},
            "color_temperature": {},
            "color_temperature_delta": {},
            "signaling": {"signal_values": ["no_signal", "on_off"]},
            "dynamics": {},
            "type": "grouped_light"
        }
        result["owner"] = {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'entertainment_configuration')), "rtype": "entertainment_configuration"}
        return result

    def getV1Api(self) -> dict[str, Any]:
        lights: List[str] = []
        for light_ref in self.lights:
            light_obj = light_ref()
            if light_obj is not None:
                lights.append(light_obj.id_v1)

        sensors: List[str] = []
        for sensor_ref in self.sensors:
            sensor_obj = sensor_ref()
            if sensor_obj is not None:
                sensors.append(sensor_obj.id_v1)

        locations = {light.id_v1: [loc[0]["x"], loc[0]["y"], loc[0]["z"]] for light, loc in list(self.locations.items()) if light.id_v1 in lights}
        class_type = "Free" if self.configuration_type == "3dspace" else "TV"
        return {
            "name": self.name,
            "lights": lights,
            "sensors": sensors,
            "type": self.type,
            "state": update_state(self),
            "recycle": False,
            "class": class_type,
            "action": self.action,
            "locations": locations,
            "stream": self.stream
        }

    def getV2Api(self) -> dict[str, Any]:
        gradienStripPositions = [
            {"x": -0.4, "y": 0.8, "z": -0.4}, {"x": -0.4, "y": 0.8, "z": 0.0}, {"x": -0.4, "y": 0.8, "z": 0.4},
            {"x": 0.0, "y": 0.8, "z": 0.4}, {"x": 0.4, "y": 0.8, "z": 0.4}, {"x": 0.4, "y": 0.8, "z": 0.0},
            {"x": 0.4, "y": 0.8, "z": -0.4}
        ]
        first_light = self.lights[0]() if self.lights else None
        stream_proxy_rid = str(uuid.uuid5(uuid.NAMESPACE_URL, first_light.id_v2 + 'entertainment')) if first_light else None

        result = {
            "configuration_type": self.configuration_type,
            "locations": {"service_locations": []},
            "metadata": {"name": self.name},
            "id_v1": f"/groups/{self.id_v1}",
            "stream_proxy": {
                "mode": "auto",
                "node": {
                    "rid": stream_proxy_rid,
                    "rtype": "entertainment"
                }
            },
            "light_services": [],
            "channels": [],
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'entertainment_configuration')),
            "type": "entertainment_configuration",
            "name": self.name,
            "status": "active" if self.stream["active"] else "inactive"
        }
        if self.stream["active"]:
            result["active_streamer"] = {"rid": self.stream["owner"], "rtype": "auth_v1"}
        channel_id = 0
        for light_ref in self.lights:
            light: Optional[Light.Light] = light_ref()
            if light:
                result["light_services"].append({"rtype": "light", "rid": light.id_v2})
                entertainmentUuid = str(uuid.uuid5(uuid.NAMESPACE_URL, light.id_v2 + 'entertainment'))
                result["locations"]["service_locations"].append({
                    "equalization_factor": 1,
                    "positions": self.locations[light],
                    "service": {"rid": entertainmentUuid, "rtype": "entertainment"},
                    "position": self.locations[light][0]
                })
                loops = len(gradienStripPositions) if light.modelid in ["LCX001", "LCX002", "LCX003"] else len(self.locations[light])
                for x in range(loops):
                    channel = {
                        "channel_id": channel_id,
                        "members": [{"index": x, "service": {"rid": entertainmentUuid, "rtype": "entertainment"}}]
                    }
                    if light.modelid in ["LCX001", "LCX002", "LCX003"]:
                        channel["position"] = gradienStripPositions[x]
                    elif light.modelid in ["915005987201", "LCX004", "LCX006"]:
                        if x == 0:
                            channel["position"] = self.locations[light][0]
                        elif x == 2:
                            channel["position"] = self.locations[light][1]
                        else:
                            channel["position"] = {
                                "x": (self.locations[light][0]["x"] + self.locations[light][1]["x"]) / 2,
                                "y": (self.locations[light][0]["y"] + self.locations[light][1]["y"]) / 2,
                                "z": (self.locations[light][0]["z"] + self.locations[light][1]["z"]) / 2
                            }
                    else:
                        channel["position"] = self.locations[light][0]
                    result["channels"].append(channel)
                    channel_id += 1
        return result

    def setV2Action(self, state: dict[str, Any]) -> None:
        v1State = v2StateToV1(state)
        setGroupAction(self, v1State)
        self.genStreamEvent(state)

    def setV1Action(self, state: dict[str, Any], scene: Optional[str] = None) -> None:
        setGroupAction(self, state, scene)
        v2State = v1StateToV2(state)
        self.genStreamEvent(v2State)

    def genStreamEvent(self, v2State: dict[str, Any]) -> None:
        streamMessage = {"data": [{"id": self.id_v2, "type": "grouped_light"}]}
        streamMessage["data"][0].update(v2State)
        self._send_stream_event(streamMessage["data"][0], "update")

    def _send_stream_event(self, data: dict[str, Any], event_type: str) -> None:
        streamMessage = {
            "creationtime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data": [data],
            "id": str(uuid.uuid4()),
            "type": event_type,
            "id_v1": f"/groups/{self.id_v1}"
        }
        StreamEvent(streamMessage)

    def getObjectPath(self) -> dict[str, str]:
        return {"resource": "groups", "id": self.id_v1}

    def save(self) -> dict[str, Any]:
        light_ids: List[str] = []
        for light_ref in self.lights:
            light_obj = light_ref()
            if light_obj is not None:
                light_ids.append(light_obj.id_v1)

        result = {
            "id_v2": self.id_v2,
            "name": self.name,
            "configuration_type": self.configuration_type,
            "lights": light_ids,
            "action": self.action,
            "type": self.type,
            "locations": {light.id_v1: loc for light, loc in self.locations.items() if light.id_v1 in light_ids}
        }
        return result
