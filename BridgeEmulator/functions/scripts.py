import logManager
import configManager
from time import sleep
from random import randrange
from typing import Union, Any, List, Callable
from HueObjects import Group, Scene, BehaviorInstance

logging = logManager.logger.get_logger(__name__)
bridgeConfig = configManager.bridgeConfig.yaml_config

def findScene(element: dict[str, Any]) -> Union[Scene.Scene, None]:
    """
    Find a scene based on the provided element.

    Args:
        element (dict[str, Any]): The element to find the scene for.

    Returns:
        Union[Scene.Scene, None]: The found scene or None if not found.
    """
    for scene, obj in bridgeConfig["scenes"].items():
        if element["group"]["rtype"] == "room" and obj.id_v2 == element["recall"]["rid"] and obj.group().getV2Room()["id"] == element["group"]["rid"]:
            return obj
        elif element["group"]["rtype"] == "zone" and obj.id_v2 == element["recall"]["rid"] and obj.group().getV2Zone()["id"] == element["group"]["rid"]:
            return obj
    return None

def findGroup(id_v2: str) -> Union[Group.Group, None]:
    """
    Find a group based on the provided id_v2.

    Args:
        id_v2 (str): The id_v2 to find the group for.

    Returns:
        Union[Group.Group, None]: The found group or None if not found.
    """
    for group, obj in bridgeConfig["groups"].items():
        if obj.type != "Entertainment" and (obj.getV2Room()["id"] == id_v2 or obj.getV2Zone()["id"] == id_v2):
            return obj
    return None

def handleWakeUp(behavior_instance: BehaviorInstance.BehaviorInstance) -> None:
    """
    Handle the Wake Up routine.

    Args:
        behavior_instance (BehaviorInstance.BehaviorInstance): The behavior instance to handle.
    """
    if behavior_instance.active and "turn_lights_off_after" in behavior_instance.configuration:
        logging.debug("End Wake Up routine")
        for element in behavior_instance.configuration["where"]:
            if "group" in element:
                group = findGroup(element["group"]["rid"])
                if not group:
                    continue
                sleep(1)
                group.setV1Action(state={"on": False})
                behavior_instance.active = False
                logging.debug("End Wake Up")
    else:
        logging.debug("Start Wake Up routine")
        for element in behavior_instance.configuration["where"]:
            if "group" in element:
                group = findGroup(element["group"]["rid"])
                if not group:
                    continue
                group.setV1Action(state={"ct": 250, "bri": 1})
                sleep(1)
                group.setV1Action(state={"on": True})
                group.setV1Action(state={"bri": 254, "transitiontime": behavior_instance.configuration["fade_in_duration"]["seconds"] * 10})
                behavior_instance.active = "turn_lights_off_after" in behavior_instance.configuration
                logging.debug("Finish Wake Up")

def handleGoToSleep(behavior_instance: BehaviorInstance.BehaviorInstance) -> None:
    """
    Handle the Go to Sleep routine.

    Args:
        behavior_instance (BehaviorInstance.BehaviorInstance): The behavior instance to handle.
    """
    logging.debug("Start Go to Sleep %s", behavior_instance.name)
    for element in behavior_instance.configuration["where"]:
        if "group" in element:
            group = findGroup(element["group"]["rid"])
            if not group:
                continue
            group.setV1Action(state={"ct": 500})
            sleep(1)
            group.setV1Action(state={"bri": 1, "transitiontime": behavior_instance.configuration["fade_out_duration"]["seconds"] * 10})
            sleep(behavior_instance.configuration["fade_out_duration"]["seconds"])
            if behavior_instance.configuration["end_state"] == "turn_off":
                group.setV1Action(state={"on": False})
            behavior_instance.active = False
            logging.debug("Finish Go to Sleep")

def handleActivateScene(behavior_instance: BehaviorInstance.BehaviorInstance) -> None:
    """
    Handle the Activate Scene routine.

    Args:
        behavior_instance (BehaviorInstance.BehaviorInstance): The behavior instance to handle.
    """
    if behavior_instance.active and "end_at" in behavior_instance.configuration["when_extended"]:
        logging.debug("End routine %s", behavior_instance.name)
        for element in behavior_instance.configuration["what"]:
            if "group" in element:
                scene = findScene(element)
                if scene:
                    logging.info("Deactivate scene " + scene.name)
                    putDict = {"recall": {"action": "deactivate"}}
                    scene.activate(putDict)
                group = findGroup(element["group"]["rid"])
                if not group:
                    continue
                logging.info("Turn off group " + group.name)
                group.setV1Action({"on": False})
                behavior_instance.active = False
    else:
        logging.debug("Start routine %s", behavior_instance.name)
        for element in behavior_instance.configuration["what"]:
            if "group" in element:
                scene = findScene(element)
                if scene:
                    logging.info("Activate scene " + scene.name)
                    if "when_extended" in behavior_instance.configuration and "transition" in behavior_instance.configuration["when_extended"]["start_at"]:
                        putDict = {"recall": {"action": "active"}, "minutes": behavior_instance.configuration["when_extended"]["start_at"]["transition"].get("minutes", 3)}
                        scene.activate(putDict)
                else:
                    group = findGroup(element["group"]["rid"])
                    if not group:
                        continue
                    if element["recall"]["rid"] == "732ff1d9-76a7-4630-aad0-c8acc499bb0b":  # Bright scene
                        logging.info("Apply Bright scene to group " + group.name)
                        group.setV1Action(state={"ct": 247, "bri": 1})
                        sleep(1)
                        group.setV1Action(state={"on": True})
                        if "when_extended" in behavior_instance.configuration and "transition" in behavior_instance.configuration["when_extended"]["start_at"]:
                            transition_minutes = behavior_instance.configuration["when_extended"]["start_at"]["transition"].get("minutes", 3)
                            group.setV1Action(state={"bri": 254, "transitiontime": transition_minutes * 60 * 10})
                behavior_instance.active = "end_at" in behavior_instance.configuration["when_extended"]

def handleCountdownTimer(behavior_instance: BehaviorInstance.BehaviorInstance) -> None:
    """
    Handle the Countdown Timer routine.

    Args:
        behavior_instance (BehaviorInstance.BehaviorInstance): The behavior instance to handle.
    """
    logging.debug("Start Countdown Timer %s", behavior_instance.name)
    secondsToCount = sum(
        behavior_instance.configuration["duration"].get(unit, 0) * factor
        for unit, factor in [("minutes", 60), ("seconds", 1)]
    )
    sleep(secondsToCount)
    for element in behavior_instance.configuration["what"]:
        if "group" in element:
            scene = findScene(element)
            group = findGroup(element["group"]["rid"])
            if not group:
                continue
            if scene:
                logging.info("Activate scene " + scene.name + " to group " + group.name)
                putDict = {"recall": {"action": "active"}}
                scene.activate(putDict)
            else:
                logging.info("Apply Bright scene to group " + group.name)
                group.setV1Action(state={"on": True, "bri": 254, "ct": 247 if element["recall"]["rid"] == "732ff1d9-76a7-4630-aad0-c8acc499bb0b" else 370})
    behavior_instance.active = False
    behavior_instance.update_attr({"enabled": False})
    logging.debug("Finish Countdown Timer %s", behavior_instance.name)

def triggerScript(behavior_instance: BehaviorInstance.BehaviorInstance) -> None:
    """
    Trigger the appropriate script based on the behavior instance.

    Args:
        behavior_instance (BehaviorInstance.BehaviorInstance): The behavior instance to handle.
    """
    if "when_extended" in behavior_instance.configuration and "randomization" in behavior_instance.configuration["when_extended"]:
        sleep(randrange(behavior_instance.configuration["when_extended"]["randomization"]["minutes"] * 60))

    script_handlers: dict[str, Callable[[BehaviorInstance.BehaviorInstance], None]] = {
        "ff8957e3-2eb9-4699-a0c8-ad2cb3ede704": handleWakeUp,
        "7e571ac6-f363-42e1-809a-4cbf6523ed72": handleGoToSleep,
        "7238c707-8693-4f19-9095-ccdc1444d228": handleActivateScene,
        "e73bc72d-96b1-46f8-aa57-729861f80c78": handleCountdownTimer,
    }

    script_id = behavior_instance.script_id
    if script_id in script_handlers:
        script_handlers[script_id](behavior_instance)

def behaviorScripts() -> List[dict[str, Any]]:
    """
    Return the list of behavior scripts.

    Returns:
        List[dict[str, Any]]: The list of behavior scripts.
    """
    return [{
      "configuration_schema": {
        "$ref": "goto_sleep_config.json#"
      },
      "description": "Get ready for nice sleep.",
      "id": "7e571ac6-f363-42e1-809a-4cbf6523ed72",
      "metadata": {
        "category": "automation",
        "name": "Go to sleep routines",
      },
      "state_schema": {
        "$ref": "goto_sleep_state.json#"
      },
      "supported_features": [
        "style_sunset_gts"
      ],
      "trigger_schema": {
        "$ref": "trigger.json#"
      },
      "type": "behavior_script",
      "version": "0.0.1"
    },
    {
      "configuration_schema": {
        "$ref": "basic_wake_up_config.json#"
      },
      "description": "Get your body in the mood to wake up by fading on the lights in the morning.",
      "id": "ff8957e3-2eb9-4699-a0c8-ad2cb3ede704",
      "metadata": {
        "category": "automation",
        "name": "Basic wake up routine"
      },
      "state_schema": {},
      "supported_features": [
        "style_sunrise",
        "intensity"
      ],
      "trigger_schema": {
        "$ref": "trigger.json#"
      },
      "type": "behavior_script",
      "version": "0.0.1"
    },
    {
      "configuration_schema": {
        "$ref": "schedule_config.json#"
      },
      "description": "Schedule turning on and off lights",
      "id": "7238c707-8693-4f19-9095-ccdc1444d228",
      "metadata": {
        "category": "automation",
        "name": "Schedule"
      },
      "state_schema": {},
      "supported_features": [],
      "trigger_schema": {
        "$ref": "trigger.json#"
      },
      "type": "behavior_script",
      "version": "0.0.1"
    },
    {
      "configuration_schema": {
        "$ref": "timer_config.json#"
      },
      "description": "Countdown Timer",
      "id": "e73bc72d-96b1-46f8-aa57-729861f80c78",
      "metadata": {
        "category": "automation",
        "name": "Timers"
      },
      "state_schema": {
        "$ref": "timer_state.json#"
      },
      "supported_features": [],
      "trigger_schema": {
        "$ref": "trigger.json#"
      },
      "type": "behavior_script",
      "version": "0.0.1"
    },
    {
      "configuration_schema": {
        "$ref": "lights_state_after_streaming_config.json#"
      },
      "description": "State of lights in the entertainment group after streaming ends",
      "id": "7719b841-6b3d-448d-a0e7-601ae9edb6a2",
      "metadata": {
        "category": "entertainment",
        "name": "Light state after streaming"
      },
      "state_schema": {},
      "supported_features": [],
      "trigger_schema": {},
      "type": "behavior_script",
      "version": "0.0.1"
    },
    {
      "configuration_schema": {
        "$ref": "natural_light_config.json#"
      },
      "description": "Natural light during the day",
      "id": "a4260b49-0c69-4926-a29c-417f4a38a352",
      "metadata": {
        "category": "",
        "name": "Natural Light"
      },
      "state_schema": {
        "$ref": "natural_light_state.json#"
      },
      "supported_features": [],
      "trigger_schema": {
        "$ref": "natural_light_trigger.json#"
      },
      "type": "behavior_script",
      "version": "0.0.1"
    },
    {
      "configuration_schema": {
        "$ref": "config.json#"
      },
      "description": "Contact Sensor script",
      "id": "049008e6-62d7-42ba-b473-d8488cfde600",
      "metadata": {
        "category": "accessory",
        "name": "Contact Sensor"
      },
      "state_schema": {
        "$ref": "state.json#"
      },
      "supported_features": [],
      "trigger_schema": {},
      "type": "behavior_script",
      "version": "0.0.1"
    },
    {
      "configuration_schema": {
        "$ref": "config.json#"
      },
      "description": "Generic switches script",
      "id": "67d9395b-4403-42cc-b5f0-740b699d67c6",
      "metadata": {
        "category": "accessory",
        "name": "Hue Switches"
      },
      "state_schema": {
        "$ref": "state.json#"
      },
      "supported_features": [],
      "trigger_schema": {},
      "type": "behavior_script",
      "version": "0.0.1"
    },
    {
      "configuration_schema": {
        "$ref": "motion_sensor_config.json#"
      },
      "description": "Motion sensor script",
      "id": "bba79770-19f1-11ec-9621-0242ac130002",
      "metadata": {
        "category": "accessory",
        "name": "Motion Sensor"
      },
      "state_schema": {
        "$ref": "motion_sensor_state.json#"
      },
      "supported_features": [],
      "trigger_schema": {},
      "type": "behavior_script",
      "version": "0.0.1"
    },
    {
      "configuration_schema": {
        "$ref": "pm_config.json#"
      },
      "description": "PM Automation",
      "id": "db06cabc-c752-4904-9e8f-4ebe98feaa1a",
      "metadata": {
        "category": "automation",
        "name": "PM"
      },
      "state_schema": {
        "$ref": "pm_state.json#"
      },
      "supported_features": [],
      "trigger_schema": {
        "$ref": "pm_trigger.json#"
      },
      "type": "behavior_script",
      "version": "0.0.1",
      "max_number_instances": 1
    },
    {
      "configuration_schema": {
        "$ref": "config.json#"
      },
      "description": "Tap Switch script",
      "id": "f306f634-acdb-4dd6-bdf5-48dd626d667e",
      "metadata": {
        "category": "accessory",
        "name": "Tap Switch",
      },
      "state_schema": {
        "$ref": "state.json#"
      },
      "supported_features": [],
      "trigger_schema": {},
      "type": "behavior_script",
      "version": "0.0.1",
    }]
