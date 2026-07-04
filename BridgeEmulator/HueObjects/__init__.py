import uuid
import logManager
import random
from typing import Any, Union

logging = logManager.logger.get_logger(__name__)

eventstream = []

def StreamEvent(message: dict[str, Any]) -> None:
    eventstream.append(message)

def v1StateToV2(v1State: dict[str, Any]) -> dict[str, Any]:
    v2State = {}
    if "on" in v1State:
        v2State["on"] = {"on": v1State["on"]}
    if "bri" in v1State:
        v2State["dimming"] = {"brightness": round(v1State["bri"] / 2.54, 2)}
    if "ct" in v1State:
        v2State["color_temperature"] = {"mirek": v1State["ct"], "color_temperature_delta": {}}
    if "xy" in v1State:
        v2State["color"] = {"xy": {"x": v1State["xy"][0], "y": v1State["xy"][1]}}
    return v2State

def v2StateToV1(v2State: dict[str, Any]) -> dict[str, Any]:
    v1State = {}
    if "dimming" in v2State:
        v1State["bri"] = int(v2State["dimming"]["brightness"] * 2.54)
    if "on" in v2State:
        v1State["on"] = v2State["on"]["on"]
    if "color_temperature" in v2State:
        v1State["ct"] = v2State["color_temperature"]["mirek"]
    if "color" in v2State and "xy" in v2State["color"]:
        v1State["xy"] = [v2State["color"]["xy"]["x"], v2State["color"]["xy"]["y"]]
    if "gradient" in v2State:
        v1State["gradient"] = v2State["gradient"]
    if "transitiontime" in v2State:
        v1State["transitiontime"] = v2State["transitiontime"]
    if "controlled_service" in v2State:
        v1State["controlled_service"] = v2State["controlled_service"]
    return v1State

def genV2Uuid() -> str:
    return str(uuid.uuid4())

def generate_unique_id() -> str:
    rand_bytes = [random.randrange(0, 256) for _ in range(3)]
    return "00:17:88:01:00:%02x:%02x:%02x-0b" % tuple(rand_bytes)

def setGroupAction(group, state: dict[str, Any], scene = None) -> None:
    lightsState: dict[str, Any] = {}
    if scene is not None:
        sceneStates = list(scene.lightstates.items())
        for light, state in sceneStates:
            state["controlled_service"] = "scene"
            lightsState[light.id_v1] = state
            if state.get("on"):
                group.state["any_on"] = True
    else:
        state = incProcess(group.action, state)
        for light in group.lights:
            if light():
                lightsState[light().id_v1] = state
        updateGroupActionColormode(group, state)
        if "on" in state:
            group.state["any_on"] = state["on"]
            group.state["all_on"] = state["on"]
        group.action.update(state)

    queueState: dict[str, Any] = {}
    for light in group.lights:
        if light() and light().id_v1 in lightsState:
            updateLightState(light, lightsState[light().id_v1])
            if light().protocol in ["native_multi", "mqtt"]:
                addToQueueState(queueState, light, lightsState[light().id_v1])
            else:
                light().setV1State(lightsState[light().id_v1])
    for device, state in queueState.items():
        state["object"].setV1State(state)

    group.state = update_state(group)

def updateGroupActionColormode(group, state: dict[str, Any]) -> None:
    if "xy" in state:
        group.action["colormode"] = "xy"
    elif "ct" in state:
        group.action["colormode"] = "ct"
    elif "hue" in state or "sat" in state:
        group.action["colormode"] = "hs"

def updateLightState(light, state: dict[str, Any]) -> None:
    for key, value in state.items():
        if key in light().state:
            light().state[key] = value
        if key == "controlled_service":
            light().controlled_service = value
    light().updateLightState(state)
    if "bri" in state:
        applyBrightnessLimits(light, state)

def applyBrightnessLimits(light, state: dict[str, Any]) -> None:
    if "min_bri" in light().protocol_cfg and light().protocol_cfg["min_bri"] > state["bri"]:
        state["bri"] = light().protocol_cfg["min_bri"]
    if "max_bri" in light().protocol_cfg and light().protocol_cfg["max_bri"] < state["bri"]:
        state["bri"] = light().protocol_cfg["max_bri"]
    if light().protocol == "mqtt" and not light().state["on"]:
        return

def addToQueueState(queueState: dict[str, Any], light, state: dict[str, Any]) -> None:
    if light().protocol_cfg["ip"] not in queueState:
        queueState[light().protocol_cfg["ip"]] = {"object": light(), "lights": {}}
    if light().protocol == "native_multi":
        queueState[light().protocol_cfg["ip"]]["lights"][light().protocol_cfg["light_nr"]] = state
    elif light().protocol == "mqtt":
        queueState[light().protocol_cfg["ip"]]["lights"][light().protocol_cfg["command_topic"]] = state

def incProcess(state: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    if "bri_inc" in data:
        state["bri"] = min(max(state["bri"] + data["bri_inc"], 1), 254)
        data["bri"] = state["bri"]
        del data["bri_inc"]
    elif "ct_inc" in data:
        state["ct"] = min(max(state["ct"] + data["ct_inc"], 153), 500)
        data["ct"] = state["ct"]
        del data["ct_inc"]
    elif "hue_inc" in data:
        state["hue"] = (state["hue"] + data["hue_inc"]) % 65536
        data["hue"] = state["hue"]
        del data["hue_inc"]
    elif "sat_inc" in data:
        state["sat"] = min(max(state["sat"] + data["sat_inc"], 1), 254)
        data["sat"] = state["sat"]
        del data["sat_inc"]
    return data

def update_state(group) -> dict[str, Union[bool, int]]:
    """
    Updates and returns the group's state.

    Returns:
        dict[str, Union[bool, int]]: Dictionary containing the updated state.
    """
    all_on = True
    any_on = False
    bri = 0
    lights_on = 0
    if not group.lights:
        all_on = False
    for light_ref in group.lights:
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
