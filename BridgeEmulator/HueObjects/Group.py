import uuid
import logManager
import weakref
from datetime import datetime, timezone
from typing import Any, List, Optional, Union
from HueObjects import genV2Uuid, v1StateToV2, v2StateToV1, setGroupAction, StreamEvent, Light, ApiUser

logging = logManager.logger.get_logger(__name__)

class Group:
    def __init__(self, data: dict[str, Any]) -> None:
        self.name: str = data.get("name", f"Group {data['id_v1']}")
        self.id_v1: str = data["id_v1"]
        self.id_v2: str = data.get("id_v2", genV2Uuid())
        self.owner: Optional[ApiUser.ApiUser] = data.get("owner")
        self.icon_class: str = data.get("class", data.get("icon_class", "Other"))
        self.lights: List[weakref.ReferenceType[Light.Light]] = []
        self.action: dict[str, Union[bool, int, str, List[float]]] = {
            "on": False, "bri": 100, "hue": 0, "sat": 254, "effect": "none", "xy": [0.0, 0.0], "ct": 153, "alert": "none", "colormode": "xy"
        }
        self.sensors: List[weakref.ReferenceType] = []
        self.type: str = data.get("type", "LightGroup")
        self.state: dict[str, bool] = {"all_on": False, "any_on": False}
        self.dxState: dict[str, Optional[datetime]] = {"all_on": None, "any_on": None}

        self._send_stream_event(self._get_v2_group(), "add")

    def groupZeroStream(self, rooms: List[str], lights: List[str]) -> None:
        """
        Sends a stream event for group zero with the provided rooms and lights.

        Args:
            rooms (List[str]): List of room IDs.
            lights (List[str]): List of light IDs.
        """
        streamMessage = {
            "data": [{"children": [], "id": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'bridge_home')), "id_v1": "/groups/0", "type": "bridge_home"}],
        }
        for room in rooms:
            streamMessage["data"][0]["children"].append({"rid": room, "rtype": "room"})
        for light in lights:
            streamMessage["data"][0]["children"].append({"rid": light, "rtype": "light"})
        self._send_stream_event(streamMessage["data"][0], "update")

    def __del__(self) -> None:
        """
        Destructor for the Group class. Sends a delete stream event and logs the destruction.
        """
        self._send_stream_event({"id": self.id_v2, "id_v1": f"/groups/{self.id_v1}", "type": "grouped_light"}, "delete")
        element = self._get_v2_group()
        self._send_stream_event({"id": element["id"], "id_v1": f"/groups/{self.id_v1}", "type": element["type"]}, "delete")
        logging.info(f"{self.name} group was destroyed.")

    def add_light(self, light: Light.Light) -> None:
        """
        Adds a light to the group and sends the appropriate stream events.

        Args:
            light (Light.Light): The light object to add.
        """
        self.lights.append(weakref.ref(light))
        element = self._get_v2_group()
        self._send_stream_event({"alert": {"action_values": ["breathe"]}, "id": self.id_v2, "id_v1": f"/groups/{self.id_v1}", "on": {"on": self.action["on"]}, "type": "grouped_light"}, "add")
        self._send_stream_event({"grouped_services": [{"rid": self.id_v2, "rtype": "grouped_light"}], "id": element["id"], "id_v1": f"/groups/{self.id_v1}", "type": element["type"]}, "update")
        self._update_group_children_and_services(element)

    def add_sensor(self, sensor: Any) -> None:
        """
        Adds a sensor to the group.

        Args:
            sensor (Any): The sensor object to add.
        """
        self.sensors.append(weakref.ref(sensor))

    def update_attr(self, newdata: dict[str, Any]) -> None:
        """
        Updates the group's attributes with the provided data.

        Args:
            newdata (dict[str, Any]): Dictionary containing the new attribute values.
        """
        if "lights" in newdata:
            del newdata["lights"]
        if "class" in newdata:
            newdata["icon_class"] = newdata.pop("class")
        for key, value in newdata.items():
            updateAttribute = getattr(self, key)
            if isinstance(updateAttribute, dict):
                updateAttribute.update(value)
                setattr(self, key, updateAttribute)
            else:
                setattr(self, key, value)
        self._send_stream_event(self._get_v2_group(), "update")

    def update_state(self) -> dict[str, Union[bool, int]]:
        """
        Updates and returns the group's state.

        Returns:
            dict[str, Union[bool, int]]: Dictionary containing the updated state.
        """
        all_on = True
        any_on = False
        bri = 0
        lights_on = 0
        if not self.lights:
            all_on = False
        for light_ref in self.lights:
            light_instance = light_ref()
            if light_instance is None:
                continue
            if light_instance.state["on"]:
                any_on = True
                if "bri" in light_instance.state:
                    bri += light_instance.state["bri"]
                    lights_on += 1
            else:
                all_on = False
        if any_on:
            bri = (((bri / lights_on) / 254) * 100) if bri > 0 else 0
        return {"all_on": all_on, "any_on": any_on, "avr_bri": int(bri)}

    def setV2Action(self, state: dict[str, Any]) -> None:
        """
        Sets the V2 action for the group and generates a stream event.

        Args:
            state (dict[str, Any]): The state to set.
        """
        v1State = v2StateToV1(state)
        state.pop("controlled_service", None)
        setGroupAction(self, v1State)
        self.genStreamEvent(state)

    def setV1Action(self, state: dict[str, Any], scene: Optional[Any] = None) -> None:
        """
        Sets the V1 action for the group and generates a stream event.

        Args:
            state (dict[str, Any]): The state to set.
            scene (Optional[Any]): The scene to set, if any.
        """
        setGroupAction(self, state, scene)
        v2State = v1StateToV2(state)
        self.genStreamEvent(v2State)

    def genStreamEvent(self, v2State: dict[str, Any]) -> None:
        """
        Generates and sends a stream event with the provided V2 state.

        Args:
            v2State (dict[str, Any]): The V2 state to include in the stream event.
        """
        streamMessage: dict[str, List[dict[str, Any]]] = {"data": []}
        for num, light_ref in enumerate(self.lights):
            light_instance = light_ref()
            if light_instance is None:
                continue
            streamMessage["data"].insert(num, {
                "id": light_instance.id_v2,
                "id_v1": f"/lights/{light_instance.id_v1}",
                "owner": {"rid": light_instance.getDevice()["id"], "rtype": "device"},
                "service_id": light_instance.protocol_cfg.get("light_nr", 1) - 1,
                "type": "light"
            })
            streamMessage["data"][num].update(v2State)
        self._send_stream_event(streamMessage["data"], "update")

        if "on" in v2State:
            v2State["dimming"] = {"brightness": self.update_state()["avr_bri"]}
        streamMessage = {
            "data": [{
                "id": self.id_v2,
                "id_v1": f"/groups/{self.id_v1}",
                "type": "grouped_light",
                "owner": {
                    "rid": self._get_v2_group()["id"],
                    "rtype": self._get_v2_group()["type"]
                }
            }]
        }
        streamMessage["data"][0].update(v2State)
        self._send_stream_event(streamMessage["data"][0], "update")

    def _send_stream_event(self, data: Union[dict[str, Any], List[dict[str, Any]]], event_type: str) -> None:
        """
        Sends a stream event with the provided data and event type.

        Args:
            data (Union[dict[str, Any], List[dict[str, Any]]]): The data to include in the stream event.
            event_type (str): The type of the event.
        """
        streamMessage = {
            "creationtime": self._current_time(),
            "data": data if isinstance(data, list) else [data],
            "id": str(uuid.uuid4()),
            "type": event_type,
            "id_v1": f"/groups/{self.id_v1}"
        }
        StreamEvent(streamMessage)

    def _current_time(self) -> str:
        """
        Returns the current time in ISO format.

        Returns:
            str: The current time in ISO format.
        """
        return datetime.now(timezone.utc).isoformat()

    def getV1Api(self) -> dict[str, Any]:
        """
        Returns the V1 API representation of the group.

        Returns:
            dict[str, Any]: The V1 API representation of the group.
        """
        result: dict[str, Any] = {"name": self.name}
        if hasattr(self, "owner") and self.owner is not None:
            result["owner"] = self.owner.username
        result["lights"] = [light_instance.id_v1 for light_ref in self.lights if (light_instance := light_ref()) is not None]
        result["sensors"] = [sensor_instance.id_v1 for sensor_ref in self.sensors if (sensor_instance := sensor_ref()) is not None]
        result["type"] = self.type.capitalize()
        result["state"] = self.update_state()
        result["recycle"] = False
        if self.id_v1 == "0":
            result["presence"] = {"state": {"presence": None, "presence_all": None, "lastupdated": "none"}}
            result["lightlevel"] = {"state": {"dark": None, "dark_all": None, "daylight": None, "daylight_any": None, "lightlevel": None, "lightlevel_min": None, "lightlevel_max": None, "lastupdated": "none"}}
        else:
            result["class"] = self.icon_class.capitalize() if len(self.icon_class) > 2 else self.icon_class.upper()
        result["action"] = self.action
        return result

    def _get_v2_group(self) -> dict[str, Any]:
        """
        Returns the V2 group representation based on the group's type.

        Returns:
            dict[str, Any]: The V2 group representation.
        """
        if self.type == "Room":
            return self.getV2Room()
        return self.getV2Zone()

    def getV2Room(self) -> dict[str, Any]:
        """
        Returns the V2 room representation of the group.

        Returns:
            dict[str, Any]: The V2 room representation.
        """
        result = {"children": [], "services": [], "type": "room"}
        for light_ref in self.lights:
            light_instance = light_ref()
            if light_instance:
                result["children"].append({"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, light_instance.id_v2 + 'device')), "rtype": "device"})
        result["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'room'))
        result["id_v1"] = f"/groups/{self.id_v1}"
        result["metadata"] = {"archetype": self.icon_class.replace(" ", "_").replace("'", "").lower(), "name": self.name}
        for light_ref in self.lights:
            light_instance = light_ref()
            if light_instance:
                result["services"].append({"rid": light_instance.id_v2, "rtype": "light"})
        result["services"].append({"rid": self.id_v2, "rtype": "grouped_light"})
        return result

    def getV2Zone(self) -> dict[str, Any]:
        """
        Returns the V2 zone representation of the group.

        Returns:
            dict[str, Any]: The V2 zone representation.
        """
        result = {"children": [], "services": [], "type": "zone"}
        for light_ref in self.lights:
            light_instance = light_ref()
            if light_instance:
                result["children"].append({"rid": light_instance.id_v2, "rtype": "light"})
        result["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'zone'))
        result["id_v1"] = f"/groups/{self.id_v1}"
        result["metadata"] = {"archetype": self.icon_class.replace(" ", "_").replace("'", "").lower(), "name": self.name}
        for light_ref in self.lights:
            light_instance = light_ref()
            if light_instance:
                result["services"].append({"rid": light_instance.id_v2, "rtype": "light"})
        result["services"].append({"rid": self.id_v2, "rtype": "grouped_light"})
        return result

    def getV2GroupedLight(self) -> dict[str, Any]:
        """
        Returns the V2 grouped light representation of the group.

        Returns:
            dict[str, Any]: The V2 grouped light representation.
        """
        result = {
            "alert": {"action_values": ["breathe"]},
            "color": {},
            "dimming": {"brightness": self.update_state()["avr_bri"]},
            "dimming_delta": {},
            "dynamics": {},
            "id": self.id_v2,
            "id_v1": f"/groups/{self.id_v1}",
            "on": {"on": self.update_state()["any_on"]},
            "type": "grouped_light",
            "signaling": {"signal_values": ["no_signal", "on_off"]}
        }
        if hasattr(self, "owner") and self.owner is not None:
            apiuser = self.owner.username
            if len(apiuser) == 32:
                apiuser = f"{apiuser[:8]}-{apiuser[8:12]}-{apiuser[12:16]}-{apiuser[16:20]}-{apiuser[20:]}"
            result["owner"] = {"rid": apiuser, "rtype": "device"}
        else:
            result["owner"] = {"rid": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'device')), "rtype": "device"}
        return result

    def getObjectPath(self) -> dict[str, str]:
        """
        Returns the object path for the group.

        Returns:
            dict[str, str]: The object path for the group.
        """
        return {"resource": "groups", "id": self.id_v1}

    def save(self) -> dict[str, Any]:
        """
        Saves and returns the group's data.

        Returns:
            dict[str, Any]: The group's data.
        """
        result = {"id_v2": self.id_v2, "name": self.name, "class": self.icon_class, "lights": [], "action": self.action, "type": self.type}
        if hasattr(self, "owner") and self.owner is not None:
            result["owner"] = self.owner.username
        for light_ref in self.lights:
            light_instance = light_ref()
            if light_instance is None:
                continue
            result["lights"].append(light_instance.id_v1)
        return result

    def _update_group_children_and_services(self, element: dict[str, Any]) -> None:
        """
        Updates the group's children and services and sends a stream event.

        Args:
            element (dict[str, Any]): The element to update.
        """
        groupChildren = []
        groupServices = []
        for light_ref in self.lights:
            light_instance = light_ref()
            if light_instance is None:
                continue
            groupChildren.append({"rid": light_instance.getDevice()["id"], "rtype": "device"})
            groupServices.append({"rid": light_instance.id_v2, "rtype": "light"})
        groupServices.append({"rid": self.id_v2, "rtype": "grouped_light"})
        self._send_stream_event({"children": groupChildren, "id": element["id"], "id_v1": f"/groups/{self.id_v1}", "services": groupServices, "type": element["type"]}, "update")
