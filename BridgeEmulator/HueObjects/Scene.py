import uuid
import logManager
import weakref
from threading import Thread
from datetime import datetime, timezone
from typing import List, Optional, Union, Any
from HueObjects import genV2Uuid, StreamEvent, Light, ApiUser, Group

logging = logManager.logger.get_logger(__name__)

class Scene:
    DEFAULT_SPEED = 0.6269841194152832

    def __init__(self, data: dict[str, Any]):
        self.name: str = data.get("name", "")
        self.id_v1: str = data.get("id_v1", "")
        self.id_v2: str = data.get("id_v2", genV2Uuid())
        self.owner: Optional[ApiUser.ApiUser] = data.get("owner", None)
        self.appdata: dict = data.get("appdata", {})
        self.type: str = data.get("type", "LightScene")
        self.picture: str = data.get("picture", "")
        self.image: Optional[str] = data.get("image", None)
        self.recycle: bool = data.get("recycle", False)
        self.lastupdated: str = data.get("lastupdated", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"))
        self.lightstates: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
        self.palette: dict = data.get("palette", {})
        self.speed: float = data.get("speed", self.DEFAULT_SPEED)
        self.group: Optional[weakref.ref] = data.get("group", None)
        self.lights: List[weakref.ref] = data.get("lights", [])
        self.status: str = data.get("status", "inactive")
        group_ref = self.group
        group_obj = group_ref() if group_ref is not None else None
        if "group" in data and group_obj is not None:
            self.storelightstate()
            self.lights = group_obj.lights
        self._send_stream_event(self.getV2Api(), "add")

    def __del__(self):
        self._send_stream_event({"id": self.id_v2, "type": "scene"}, "delete")
        logging.info(f"{self.name} scene was destroyed.")

    def _send_stream_event(self, data: dict[str, Any], event_type: str) -> None:
        streamMessage = {
            "creationtime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data": [data],
            "id": str(uuid.uuid4()),
            "type": event_type,
            "id_v1": f"/scenes/{self.id_v1}"
        }
        StreamEvent(streamMessage)

    def add_light(self, light: weakref.ref) -> None:
        self.lights.append(light)

    def _get_group(self) -> Optional[Group.Group]:
        return self.group() if self.group is not None else None

    def activate(self, data: dict[str, Any]) -> None:
        if "recall" in data:
            action = data["recall"]["action"]
            if action == "dynamic_palette":
                self._activate_dynamic_palette(data)
            elif action == "deactivate":
                self.status = "inactive"
            return

        self._activate_static_scene(data)

    def _activate_dynamic_palette(self, data: dict[str, Any]) -> None:
        self.status = data["recall"]["action"]
        for lightIndex, light_ref in enumerate(self.lights):
            light_obj = light_ref()
            if light_obj is not None:
                light_obj.dynamics["speed"] = self.speed
                light_obj.controlled_service = data.get("controlled_service", {"rid": self.id_v2, "rtype": "scene"})
                Thread(target=light_obj.dynamicScenePlay, args=[self.palette, lightIndex]).start()

    def _activate_static_scene(self, data: dict[str, Any]) -> None:
        queueState = {}
        self.status = data["recall"]["action"]
        for light, state in self.lightstates.items():
            logging.debug(state)
            light: Light.Light = light
            light.state.update(state)
            light.updateLightState(state)
            if light.dynamics["status"] == "dynamic_palette":
                light.dynamics["status"] = "none"
                logging.debug(f"Stop Dynamic scene play for {light.name}")
            self._update_transition_time(state, data)
            light.controlled_service = data.get("controlled_service", {"rid": self.id_v2, "rtype": "scene"})

            if light.protocol in ["native_multi", "mqtt"]:
                self._queue_state(queueState, light, state)
            else:
                logging.debug(state)
                light.setV1State(state)
        self._apply_queued_state(queueState)

        if self.type == "GroupScene":
            group = self._get_group()
            if group is not None:
                group.state["any_on"] = True

    def _update_transition_time(self, state: dict[str, Any], data: dict[str, Any]) -> None:
        transitiontime = data.get("seconds", 0) * 10 + data.get("minutes", 0) * 600
        if transitiontime > 0:
            state["transitiontime"] = transitiontime
        if "recall" in data and "duration" in data["recall"]:
            state["transitiontime"] = int(data["recall"]["duration"] / 100)

    def _queue_state(self, queueState: dict[str, Any], light: Light.Light, state: dict[str, Any]) -> None:
        ip = light.protocol_cfg["ip"]
        if ip not in queueState:
            queueState[ip] = {"object": light, "lights": {}}
        if light.protocol == "native_multi":
            queueState[ip]["lights"][light.protocol_cfg["light_nr"]] = state
        elif light.protocol == "mqtt":
            queueState[ip]["lights"][light.protocol_cfg["command_topic"]] = state

    def _apply_queued_state(self, queueState: dict[str, Any]) -> None:
        for device, state in queueState.items():
            light: Light.Light = state["object"]
            light.setV1State(state)

    def getV1Api(self) -> dict[str, Any]:
        result = {
            "name": self.name,
            "type": self.type,
            "lights": [],
            "lightstates": {},
            "owner": self.owner.username if self.owner is not None else "",
            "recycle": self.recycle,
            "locked": True,
            "appdata": self.appdata,
            "picture": self.picture,
            "lastupdated": self.lastupdated
        }
        if self.type == "LightScene":
            result["lights"] = [light_obj.id_v1 for light in self.lights if (light_obj := light()) is not None]
        elif self.type == "GroupScene":
            group = self._get_group()
            if group is not None:
                result["group"] = group.id_v1
                result["lights"] = [light_obj.id_v1 for light in group.lights if (light_obj := light()) is not None]

        result["lightstates"] = {light.id_v1: state for light, state in self.lightstates.items() if light.id_v1 in result["lights"] and "gradient" not in state}
        if self.image is not None:
            result["image"] = self.image
        return result

    def getV2Api(self) -> dict[str, Any]:
        result: dict[str, Any] = {"actions": []}
        lightstates = list(self.lightstates.items())

        for light, state in lightstates:
            v2State = {}
            if "on" in state:
                v2State["on"] = {"on": state["on"]}
            if "bri" in state:
                bri_value = state["bri"]
                if bri_value is None or bri_value == "null":
                    bri_value = 1
                v2State["dimming"] = {"brightness": round(float(bri_value) / 2.54, 2)}

            if "xy" in state:
                v2State["color"] = {"xy": {"x": state["xy"][0], "y": state["xy"][1]}}
            if "ct" in state:
                v2State["color_temperature"] = {"mirek": state["ct"]}
            result["actions"].append({
                "action": v2State,
                "target": {"rid": light.id_v2, "rtype": "light"}
            })

        group = self._get_group()
        if self.type == "GroupScene" and group is not None:
            result["group"] = {
                "rid": str(uuid.uuid5(uuid.NAMESPACE_URL, group.id_v2 + group.type.lower())),
                "rtype": group.type.lower()
            }
        metadata: dict[str, Any] = {"name": self.name}
        if self.image is not None:
            metadata["image"] = {"rid": self.image, "rtype": "public_image"}
        result["metadata"] = metadata
        result.update({
            "id": self.id_v2,
            "id_v1": f"/scenes/{self.id_v1}",
            "type": "scene",
            "palette": self.palette,
            "speed": self.speed,
            "auto_dynamic": False,
            "status": {"active": self.status},
            "recall": {}
        })
        return result

    def storelightstate(self) -> None:
        group = self._get_group()
        lights = group.lights if self.type == "GroupScene" and group is not None else self.lightstates.keys()
        for light_ref in lights:
            light_obj: Optional[Light.Light] = light_ref()
            if light_obj is not None:
                state = {"on": light_obj.state["on"]}
                colormode = light_obj.state.get("colormode")
                if colormode == "xy":
                    state["xy"] = light_obj.state["xy"]
                elif colormode == "ct":
                    state["ct"] = light_obj.state["ct"]
                elif colormode == "hs":
                    state["hue"] = light_obj.state["hue"]
                    state["sat"] = light_obj.state["sat"]
                if "bri" in light_obj.state:
                    state["bri"] = light_obj.state["bri"]
                self.lightstates[light_obj] = state

    def update_attr(self, newdata: dict[str, Any]) -> None:
        self.lastupdated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        if newdata.get("storelightstate"):
            self.storelightstate()
            return
        for key, value in newdata.items():
            updateAttribute = getattr(self, key)
            if isinstance(updateAttribute, dict):
                updateAttribute.update(value)
                setattr(self, key, updateAttribute)
            else:
                setattr(self, key, value)

    def getObjectPath(self) -> dict[str, str]:
        return {"resource": "scenes", "id": self.id_v1}

    def save(self) -> Union[dict[str, Any], bool]:
        result = {
            "id_v2": self.id_v2,
            "name": self.name,
            "appdata": self.appdata,
            "owner": self.owner.username if self.owner is not None else "",
            "type": self.type,
            "picture": self.picture,
            "image": self.image,
            "recycle": self.recycle,
            "lastupdated": self.lastupdated,
            "lights": [],
            "lightstates": {}
        }
        if self.type == "GroupScene":
            group = self._get_group()
            if group is not None:
                result["group"] = group.id_v1
            else:
                return False
        if self.palette is not None:
            result["palette"] = self.palette
        result["speed"] = self.speed or self.DEFAULT_SPEED
        result["lights"] = [light_obj.id_v1 for light in self.lights if (light_obj := light()) is not None]
        result["lightstates"] = {light.id_v1: state for light, state in self.lightstates.items()}
        return result
