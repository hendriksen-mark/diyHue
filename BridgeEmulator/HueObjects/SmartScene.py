import uuid
import logManager
from threading import Thread
from datetime import datetime, timezone
from HueObjects import genV2Uuid, StreamEvent

logging = logManager.logger.get_logger(__name__)

class SmartScene():

    DEFAULT_SPEED = 60000#ms

    def __init__(self, data):
        self.name = data["name"]
        self.id_v1 = data["id_v1"]
        self.id_v2 = data["id_v2"] if "id_v2" in data else genV2Uuid()
        self.appdata = data["appdata"] if "appdata" in data else {}
        self.type = data["type"] if "type" in data else "smart_scene"
        self.image = data["image"] if "image" in data else None
        self.action = data["action"] if "action" in data else "activate"
        self.lastupdated = data["lastupdated"] if "lastupdated" in data else datetime.now(timezone.utc
        ).strftime("%Y-%m-%dT%H:%M:%S")
        self.timeslots = data["week_timeslots"] if "week_timeslots" in data else data["timeslots"] if "timeslots" in data else {}
        self.speed = data["transition_duration"] if "transition_duration" in data else self.DEFAULT_SPEED
        self.group = data["group"] if "group" in data else None
        self.state = data["state"] if "state" in data else "inactive"
        streamMessage = {"creationtime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "data": [self.getV2Api()],
                         "id": str(uuid.uuid4()),
                         "type": "add"
                         }
        streamMessage["data"][0].update(self.getV2Api())
        StreamEvent(streamMessage)

    def __del__(self):
        streamMessage = {"creationtime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                         "data": [{"id": self.id_v2, "type": "scene"}],
                         "id": str(uuid.uuid4()),
                         "type": "delete"
                         }
        streamMessage["id_v1"] = "/smart_scene/" + self.id_v1
        StreamEvent(streamMessage)
        logging.info(self.name + " scene was destroyed.")

    def add_light(self, light):
        self.lights.append(light)

    def activate(self, data):
        # activate dynamic scene
        if "recall" in data and data["recall"]["action"] == "activate":
            lightIndex = 0
            for light in self.lights:
                if light():
                    light().dynamics["speed"] = self.speed
                    Thread(target=light().dynamicScenePlay, args=[
                           self.timeslots, lightIndex]).start()
                    lightIndex += 1

            return
        queueState = {}
        for light, state in self.lightstates.items():
            logging.debug(state)
            light.state.update(state)
            light.updateLightState(state)
            if light.dynamics["status"] == "dynamic_palette":
                light.dynamics["status"] = "none"
                logging.debug("Stop Dynamic scene play for " + light.name)
            if len(data) > 0:
                transitiontime = 0
                if "seconds" in data:
                    transitiontime += data["seconds"] * 10
                if "minutes" in data:
                    transitiontime += data["minutes"] * 600
                if transitiontime > 0:
                    state["transitiontime"] = transitiontime
                if "recall" in data and "duration" in data["recall"]:
                    state["transitiontime"] = int(
                        data["recall"]["duration"] / 100)

            if light.protocol in ["native_multi", "mqtt"]:
                if light.protocol_cfg["ip"] not in queueState:
                    queueState[light.protocol_cfg["ip"]] = {
                        "object": light, "lights": {}}
                if light.protocol == "native_multi":
                    queueState[light.protocol_cfg["ip"]
                               ]["lights"][light.protocol_cfg["light_nr"]] = state
                elif light.protocol == "mqtt":
                    queueState[light.protocol_cfg["ip"]
                               ]["lights"][light.protocol_cfg["command_topic"]] = state
            else:
                logging.debug(state)
                light.setV1State(state)
        for device, state in queueState.items():
            state["object"].setV1State(state)

    def getV2Api(self):
        result = {}
        result["metadata"] = {}
        if self.image != None:
            result["metadata"]["image"] = {"rid": self.image,
                                           "rtype": "public_image"}
        result["metadata"]["name"] = self.name
        result["metadata"]["appdata"] = self.appdata
        result["id"] = self.id_v2
        result["id_v1"] = "/smart_scene/" + self.id_v1
        result["group"] = self.group
        result["type"] = "smart_scene"
        result["week_timeslots"] = self.timeslots
        result["transition_duration"] = self.speed
        result["state"] = self.state
        result["active_timeslot"] = {"timeslot_id": 0, "weekday": str(datetime.now(timezone.utc).strftime("%A")).lower()}
        return result

    def update_attr(self, newdata):
        self.lastupdated = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
        for key, value in newdata.items():
            updateAttribute = getattr(self, key)
            if isinstance(updateAttribute, dict):
                updateAttribute.update(value)
                setattr(self, key, updateAttribute)
            else:
                setattr(self, key, value)

    def save(self):
        result = {"id_v2": self.id_v2, "name": self.name, "appdata": self.appdata, "type": self.type, "image": self.image,
                  "lastupdated": self.lastupdated, "state": self.state, "group": self.group}
        if self.timeslots != None:
            result["timeslots"] = self.timeslots
        result["speed"] = self.speed or self.DEFAULT_SPEED

        return result
