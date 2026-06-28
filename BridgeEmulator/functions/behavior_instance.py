import logManager
import configManager
import uuid
import random
from datetime import datetime
from threading import Thread
from time import sleep
from typing import List, Any, Optional
from HueObjects import Group, Light, Scene

logging = logManager.logger.get_logger(__name__)
bridgeConfig = configManager.bridgeConfig.yaml_config

def findTriggerTime(times: List[dict[str, Any]]) -> Any:
    """
    Find the trigger time based on the current time.

    Args:
        times (List[dict[str, Any]]): List of time intervals with actions.

    Returns:
        Any: Actions corresponding to the current time interval.
    """
    now = datetime.now()
    for i in range(len(times) - 1):
        start = now.replace(hour=times[i]["hour"], minute=times[i]["minute"], second=0)
        end = now.replace(hour=times[i + 1]["hour"], minute=times[i + 1]["minute"], second=0)
        if start <= now <= end:
            return times[i]["actions"]
    return times[-1]["actions"]

def callScene(scene: str) -> None:
    """
    Call a scene by its ID.

    Args:
        scene (str): The ID of the scene to call.
    """
    logging.info(f"Calling scene {scene}")
    for obj in bridgeConfig["scenes"].values():
        obj: Scene.Scene = obj
        if obj.id_v2 == scene:
            obj.activate({"seconds": 1, "minutes": 0})

def findGroup(rid: str, rtype: str) -> Optional[Any]:
    """
    Find a group by its RID and type.

    Args:
        rid (str): The RID of the group.
        rtype (str): The type of the group.

    Returns:
        Optional[Any]: The group object if found, otherwise None.
    """
    for obj in bridgeConfig["groups"].values():
        obj: Group.Group = obj
        if str(uuid.uuid5(uuid.NAMESPACE_URL, obj.id_v2 + rtype)) == rid:
            return obj
    logging.info("Group not found!!!!")
    return None

def findLight(rid: str, rtype: str) -> Optional[Any]:
    """
    Find a light by its RID and type.

    Args:
        rid (str): The RID of the light.
        rtype (str): The type of the light.

    Returns:
        Optional[Any]: The light object if found, otherwise None.
    """
    for obj in bridgeConfig["lights"].values():
        obj: Light.Light = obj
        if str(uuid.uuid5(uuid.NAMESPACE_URL, obj.id_v2)) == rid:
            return obj
    logging.info("Light not found!!!!")
    return None

def threadDelayAction(actionsToExecute: dict[str, Any], device: Any, monitoredKey: str, monitoredValue: Any, groupsAndLights: List[Any]) -> None:
    """
    Execute actions after a delay if the monitored value remains unchanged.

    Args:
        actionsToExecute (dict[str, Any]): Actions to execute.
        device (Any): The device to monitor.
        monitoredKey (str): The key to monitor in the device state.
        monitoredValue (Any): The value to monitor in the device state.
        groupsAndLights (List[Any]): List of groups and lights to control.
    """
    secondsCounter = 0
    if "after" in actionsToExecute:
        secondsCounter = actionsToExecute["after"].get("minutes", 0) * 60 + actionsToExecute["after"].get("seconds", 0)
    elif "timer" in actionsToExecute:
        secondsCounter = actionsToExecute["timer"]["duration"].get("minutes", 0) * 60 + actionsToExecute["timer"]["duration"].get("seconds", 0)
    
    logging.debug(f"Waiting for {secondsCounter} seconds")
    while device.state[monitoredKey] == monitoredValue:
        if secondsCounter == 0:
            executeActions(actionsToExecute, groupsAndLights)
            return  
        secondsCounter -= 1
        sleep(1)
    logging.info("Motion detected, canceling the counter...")

def executeActions(actionsToExecute: dict[str, Any], groupsAndLights: List[Any]) -> None:
    """
    Execute the specified actions on the groups and lights.

    Args:
        actionsToExecute (dict[str, Any]): Actions to execute.
        groupsAndLights (List[Any]): List of groups and lights to control.
    """
    recall = "recall_single" if "recall_single" in actionsToExecute else "recall"
    logging.info("Executing routine action")
    if recall in actionsToExecute:
        for action in actionsToExecute[recall]:
            if action["action"] == "all_off":
                for resource in groupsAndLights:
                    resource.setV1Action({"on": False, "transistiontime": 100})
                    logging.info(f"Routine turning lights off {resource.name}")
            elif "recall" in action["action"] and action["action"]["recall"]["rtype"] == "scene":
                callScene(action["action"]["recall"]["rid"])

def checkBehaviorInstances(device: Any) -> None:
    """
    Check and handle behavior instances for the given device.

    Args:
        device (Any): The device to check behavior instances for.
    """
    logging.debug("Entering checkBehaviorInstances")
    deviceUuid = device.id_v2 
    matchedInstances = [
        instance for instance in bridgeConfig["behavior_instance"].values()
        if instance.enabled and (
            ("source" in instance.configuration and instance.configuration["source"]["rtype"] == "device" and instance.configuration["source"]["rid"] == deviceUuid) or
            ("device" in instance.configuration and instance.configuration["device"]["rtype"] == "device" and instance.configuration["device"]["rid"] == deviceUuid)
        )
    ]

    for instance in matchedInstances:
        lightsAndGroups = [
            findGroup(resource["group"]["rid"], resource["group"]["rtype"]) if "group" in resource else findLight(resource["light"]["rid"], resource["light"]["rtype"])
            for resource in instance.configuration["where"]
        ]
        if device.modelid in ["RWL022", "RWL021", "RWL020"]: # Hue dimmer switch
            handleDimmerSwitch(instance, device, lightsAndGroups)
        elif device.modelid == "SML001": # Motion Sensor
            handleMotionSensor(instance, device, lightsAndGroups)
        elif device.modelid == "SOC001": # Secure contact sensor
            handleContactSensor(instance, device, lightsAndGroups)
        elif device.modelid == "RDM002": # Hue rotary switch
            handleRotarySwitch(instance, device, lightsAndGroups)

def handleDimmerSwitch(instance: Any, device: Any, lightsAndGroups: List[Any]) -> None:
    """
    Handle actions for a Hue dimmer switch.

    Args:
        instance (Any): The behavior instance.
        device (Any): The device to handle.
        lightsAndGroups (List[Any]): List of groups and lights to control.
    """
    button = getButton(device)
    if button in instance.configuration["buttons"]:
        buttonAction = getButtonAction(device)
        if buttonAction in instance.configuration["buttons"][button]:
            handleButtonAction(instance, button, buttonAction, lightsAndGroups)

def getButton(device: Any) -> str:
    """
    Get the button identifier based on the device state.

    Args:
        device (Any): The device to get the button identifier from.

    Returns:
        str: The button identifier.
    """
    buttonevent = device.firstElement().state["buttonevent"]
    if buttonevent < 2000:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, device.id_v2 + 'button1'))
    elif buttonevent < 3000:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, device.id_v2 + 'button2'))
    elif buttonevent < 4000:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, device.id_v2 + 'button3'))
    else:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, device.id_v2 + 'button4'))

def getButtonAction(device: Any) -> str:
    """
    Get the button action based on the device state.

    Args:
        device (Any): The device to get the button action from.

    Returns:
        str: The button action.
    """
    lastDigit = device.firstElement().state["buttonevent"] % 1000
    if lastDigit == 0:
        return "on_short_press"
    elif lastDigit == 1:
        return "on_repeat"
    elif lastDigit == 2:
        return "on_short_release"
    elif lastDigit == 3:
        return "on_long_press"
    return ""

def handleButtonAction(instance: Any, button: str, buttonAction: str, lightsAndGroups: List[Any]) -> None:
    """
    Handle the button action for a Hue dimmer switch.

    Args:
        instance (Any): The behavior instance.
        button (str): The button identifier.
        buttonAction (str): The button action.
        lightsAndGroups (List[Any]): List of groups and lights to control.
    """
    if "time_based" in instance.configuration["buttons"][button][buttonAction]:
        handleTimeBasedAction(instance, button, buttonAction, lightsAndGroups)
    elif "scene_cycle" in instance.configuration["buttons"][button][buttonAction]:
        callScene(random.choice(instance.configuration["buttons"][button][buttonAction]["scene_cycle"])[0]["action"]["recall"]["rid"])
    elif "action" in instance.configuration["buttons"][button][buttonAction]:
        handleDirectAction(instance, button, buttonAction, lightsAndGroups)

def handleTimeBasedAction(instance: Any, button: str, buttonAction: str, lightsAndGroups: List[Any]) -> None:
    """
    Handle time-based actions for a Hue dimmer switch.

    Args:
        instance (Any): The behavior instance.
        button (str): The button identifier.
        buttonAction (str): The button action.
        lightsAndGroups (List[Any]): List of groups and lights to control.
    """
    any_on = any(
        resource.state.get("any_on", False) or resource.state.get("on", False)
        for resource in lightsAndGroups
    )
    if any_on:
        for resource in lightsAndGroups:
            resource.setV1Action({"on": False})
        return

    allTimes = [
        {"hour": time["start_time"]["hour"], "minute": time["start_time"]["minute"], "actions": time["actions"]}
        for time in instance.configuration["buttons"][button][buttonAction]["time_based"]
    ]
    actions = findTriggerTime(allTimes)
    for action in actions:
        if "recall" in action["action"] and action["action"]["recall"]["rtype"] == "scene":
            callScene(action["action"]["recall"]["rid"])

def handleDirectAction(instance: Any, button: str, buttonAction: str, lightsAndGroups: List[Any]) -> None:
    """
    Handle direct actions for a Hue dimmer switch.

    Args:
        instance (Any): The behavior instance.
        button (str): The button identifier.
        buttonAction (str): The button action.
        lightsAndGroups (List[Any]): List of groups and lights to control.
    """
    action = instance.configuration["buttons"][button][buttonAction]["action"]
    for resource in lightsAndGroups:
        if action == "all_off":
            resource.setV1Action({"on": False})
        elif action == "dim_up":
            resource.setV1Action({"bri_inc": +30})
        elif action == "dim_down":
            resource.setV1Action({"bri_inc": -30})

def handleMotionSensor(instance: Any, device: Any, lightsAndGroups: List[Any]) -> None:
    """
    Handle actions for a motion sensor.

    Args:
        instance (Any): The behavior instance.
        device (Any): The device to handle.
        lightsAndGroups (List[Any]): List of groups and lights to control.
    """
    if "settings" in instance.configuration and "daylight_sensitivity" in instance.configuration["settings"]:
        handleDaylightSensitivity(instance, device)
    motion = device.elements["ZLLPresence"]().state["presence"]
    any_on = any(
        resource.update_state().get("any_on", False)
        for resource in lightsAndGroups
    )
    if "timeslots" in instance.configuration["when"]:
        allSlots = [
            {"hour": slot["start_time"]["time"]["hour"], "minute": slot["start_time"]["time"]["minute"], "actions": {"on_motion": slot["on_motion"], "on_no_motion": slot["on_no_motion"]}}
            for slot in instance.configuration["when"]["timeslots"]
        ]
        actions: dict[str, Any] = findTriggerTime(allSlots)
        if motion:
            if not any_on: # motion triggered and lights are off
                logging.info(f"Trigger motion routine {instance.name}")
                executeActions(actions["on_motion"], [])
        else:
            logging.info("No motion")
            if any_on:
                Thread(target=threadDelayAction, args=[actions["on_no_motion"], device.elements["ZLLPresence"](), "presence", False, lightsAndGroups]).start()

def handleDaylightSensitivity(instance: Any, device: Any) -> None:
    """
    Handle daylight sensitivity settings for a motion sensor.

    Args:
        instance (Any): The behavior instance.
        device (Any): The device to handle.
    """
    if device.elements["ZLLLightLevel"]().protocol_cfg["lightSensor"] == "on":
        device.elements["ZLLLightLevel"]().state["lightlevel"] = 25000 if bridgeConfig["sensors"]["1"].state["daylight"] else 6000
    if instance.configuration["settings"]["daylight_sensitivity"]["dark_threshold"] >= device.elements["ZLLLightLevel"]().state["lightlevel"]:
        logging.debug("Light ok")
    else:
        logging.debug("Light not ok")
        return

def handleContactSensor(instance: Any, device: Any, lightsAndGroups: List[Any]) -> None:
    """
    Handle actions for a contact sensor.

    Args:
        instance (Any): The behavior instance.
        device (Any): The device to handle.
        lightsAndGroups (List[Any]): List of groups and lights to control.
    """
    actions = getContactSensorActions(instance)
    contact = "on_close" if device.elements["ZLLContact"]().state["contact"] == "contact" else "on_open"
    if "timer" in actions[contact]:
        monitoredValue = "contact" if contact == "on_close" else "no_contact"
        logging.info(f"Trigger timer routine {instance.name}")
        Thread(target=threadDelayAction, args=[actions[contact], device.elements["ZLLContact"](), "contact", monitoredValue, lightsAndGroups]).start()
    else:
        logging.info(f"Trigger routine {instance.name}")
        executeActions(actions[contact], lightsAndGroups)

def getContactSensorActions(instance: Any) -> dict[str, Any]:
    """
    Get the actions for a contact sensor based on the configuration.

    Args:
        instance (Any): The behavior instance.

    Returns:
        dict[str, Any]: The actions for the contact sensor.
    """
    if "timeslots" in instance.configuration["when"]:
        allSlots = [
            {"hour": slot["start_time"]["time"]["hour"], "minute": slot["start_time"]["time"]["minute"], "actions": {"on_open": slot["on_open"], "on_close": slot["on_close"]}}
            for slot in instance.configuration["when"]["timeslots"]
        ]
        return findTriggerTime(allSlots)
    elif "always" in instance.configuration["when"]:
        return {"on_open": instance.configuration["when"]["always"]["on_open"], "on_close": instance.configuration["when"]["always"]["on_close"]}
    return {}

def handleRotarySwitch(instance: Any, device: Any, lightsAndGroups: List[Any]) -> None:
    """
    Handle actions for a rotary switch.

    Args:
        instance (Any): The behavior instance.
        device (Any): The device to handle.
        lightsAndGroups (List[Any]): List of groups and lights to control.
    """
    buttonDevice = device.elements["ZLLSwitch"]()
    button = getRotaryButton(buttonDevice)
    if button in instance.configuration:
        buttonAction = getButtonAction(buttonDevice)
        if buttonAction in instance.configuration[button]:
            lightsAndGroups = [
                findGroup(resource["group"]["rid"], resource["group"]["rtype"]) if "group" in resource else findLight(resource["light"]["rid"], resource["light"]["rtype"])
                for resource in instance.configuration[button]["where"]
            ]
            if "time_based_extended" in instance.configuration[button][buttonAction]:
                handleTimeBasedExtendedAction(instance, button, buttonAction, lightsAndGroups)
            elif "time_based" in instance.configuration[button][buttonAction]:
                logging.debug("To be done")

def getRotaryButton(buttonDevice: Any) -> str:
    """
    Get the button identifier for a rotary switch based on the device state.

    Args:
        buttonDevice (Any): The button device to get the identifier from.

    Returns:
        str: The button identifier.
    """
    buttonevent = buttonDevice.state["buttonevent"]
    if buttonevent < 2000:
        return 'button1'
    elif buttonevent < 3000:
        return 'button2'
    elif buttonevent < 4000:
        return 'button3'
    else:
        return 'button4'

def handleTimeBasedExtendedAction(instance: Any, button: str, buttonAction: str, lightsAndGroups: List[Any]) -> None:
    """
    Handle time-based extended actions for a rotary switch.

    Args:
        instance (Any): The behavior instance.
        button (str): The button identifier.
        buttonAction (str): The button action.
        lightsAndGroups (List[Any]): List of groups and lights to control.
    """
    allSlots = [
        {"hour": slot["start_time"]["hour"], "minute": slot["start_time"]["minute"], "actions": slot["actions"]}
        for slot in instance.configuration[button][buttonAction]["time_based_extended"]["slots"]
    ]
    actions = findTriggerTime(allSlots)
    executeActions(actions, lightsAndGroups)
