import json
import random
from copy import deepcopy
from datetime import datetime, timedelta, time, timezone
from threading import Thread
from time import sleep
from typing import Tuple

import configManager
import logManager
from flaskUI.v2restapi import getObject
from functions.daylightSensor import daylightSensor
from functions.request import sendRequest
from functions.scripts import findGroup, triggerScript
from services import updateManager
from HueObjects import Group, Scene, Schedule, Sensor, BehaviorInstance, SmartScene

bridgeConfig = configManager.bridgeConfig.yaml_config
logging = logManager.logger.get_logger(__name__)

def execute_schedule(schedule: str, obj: Schedule.Schedule, delay: int) -> None:
    """
    Execute a schedule command with a specified delay.

    Args:
        schedule (str): The schedule identifier.
        obj (Any): The schedule object containing command details.
        delay (int): The delay in seconds before executing the command.
    """
    logging.info(f"execute schedule: {schedule} with delay {delay}")
    sendRequest(obj.command["address"], obj.command["method"], json.dumps(obj.command["body"]), 1, delay)

def execute_timer(schedule: str, obj: Schedule.Schedule, delay: int) -> None:
    """
    Execute a timer command with a specified delay.

    Args:
        schedule (str): The schedule identifier.
        obj (Any): The timer object containing command details.
        delay (int): The delay in seconds before executing the command.
    """
    logging.info(f"execute timer: {schedule} with delay {delay}")
    sendRequest(obj.command["address"], obj.command["method"], json.dumps(obj.command["body"]), 1, delay)

def check_time_match(time_object: datetime) -> bool:
    """
    Check if the current time matches the given time object.

    Args:
        time_object (datetime): The time object to match against the current time.

    Returns:
        bool: True if the current time matches the time object, False otherwise.
    """
    now = datetime.now()
    return now.second == time_object.second and now.minute == time_object.minute and now.hour == time_object.hour

def get_schedule_time(obj: Schedule.Schedule) -> Tuple[str, int]:
    """
    Get the schedule time and delay from the schedule object.

    Args:
        obj (Schedule.Schedule): The schedule object containing time details.

    Returns:
        Tuple[str, int]: The schedule time string and delay in seconds.
    """
    if obj.localtime[-9:-8] == "A":
        delay = random.randrange(0, int(obj.localtime[-8:-6]) * 3600 + int(obj.localtime[-5:-3]) * 60 + int(obj.localtime[-2:]))
        return obj.localtime[:-9], delay
    return obj.localtime, 0

def process_schedule(schedule: str, obj: Schedule.Schedule) -> None:
    """
    Process and execute the schedule based on its configuration.

    Args:
        schedule (str): The schedule identifier.
        obj (Any): The schedule object containing configuration details.
    """
    schedule_time, delay = get_schedule_time(obj)
    if obj.status == "enabled":
        if schedule_time.startswith("W"):
            pieces = schedule_time.split('/T')
            if int(pieces[0][1:]) & (1 << 6 - datetime.today().weekday()):
                if pieces[1] == datetime.now().strftime("%H:%M:%S"):
                    execute_schedule(schedule, obj, delay)
        elif schedule_time.startswith("PT"):
            timer = schedule_time[2:]
            (h, m, s) = timer.split(':')
            d = timedelta(hours=int(h), minutes=int(m), seconds=int(s))
            if obj.starttime == (datetime.now(timezone.utc).replace(tzinfo=None) - d).replace(microsecond=0).isoformat():
                execute_timer(schedule, obj, delay)
                obj.status = "disabled"
        elif schedule_time.startswith("R/PT"):
            timer = schedule_time[4:]
            (h, m, s) = timer.split(':')
            d = timedelta(hours=int(h), minutes=int(m), seconds=int(s))
            if obj.starttime == (datetime.now(timezone.utc).replace(tzinfo=None) - d).replace(microsecond=0).isoformat():
                obj.starttime = datetime.now(timezone.utc).replace(tzinfo=None).replace(microsecond=0).isoformat()
                execute_timer(schedule, obj, delay)
        else:
            if schedule_time == datetime.now().strftime("%Y-%m-%dT%H:%M:%S"):
                execute_schedule(schedule, obj, delay)
                if obj.autodelete:
                    del obj

def process_behavior_instance(instance: str, obj: BehaviorInstance.BehaviorInstance) -> None:
    """
    Process and execute the behavior instance based on its configuration.

    Args:
        instance (str): The behavior instance identifier.
        obj (Any): The behavior instance object containing configuration details.
    """
    if obj.enabled:
        if "when" in obj.configuration:
            if "recurrence_days" in obj.configuration["when"]:
                if datetime.now().strftime("%A").lower() not in obj.configuration["when"]["recurrence_days"]:
                    return
            if "time_point" in obj.configuration["when"] and obj.configuration["when"]["time_point"]["type"] == "time":
                triggerTime: dict[str, int] = obj.configuration["when"]["time_point"]["time"]
                time_object = datetime(
                    year=1,
                    month=1,
                    day=1,
                    hour=triggerTime["hour"],
                    minute=triggerTime["minute"],
                    second=triggerTime.get("second", 0))
                if "fade_in_duration" in obj.configuration or "turn_lights_off_after" in obj.configuration:
                    fade_duration: dict[str, int] = obj.configuration.get("turn_lights_off_after", obj.configuration["fade_in_duration"])
                    delta = timedelta(
                        hours=fade_duration.get("hours", 0),
                        minutes=fade_duration.get("minutes", 0),
                        seconds=fade_duration.get("seconds", 0))
                    time_object = time_object + delta if "turn_lights_off_after" in obj.configuration and obj.active else time_object - delta
                if check_time_match(time_object):
                    logging.info(f"execute timer: {obj.name}")
                    Thread(target=triggerScript, args=[obj]).start()

        elif "when_extended" in obj.configuration:
            if "recurrence_days" in obj.configuration["when_extended"]:
                if datetime.now().strftime("%A").lower() not in obj.configuration["when_extended"]["recurrence_days"]:
                    return
            if obj.active:
                if "end_at" in obj.configuration["when_extended"] and "time_point" in obj.configuration["when_extended"]["end_at"] and obj.configuration["when_extended"]["end_at"]["time_point"]["type"] == "time":
                    triggerTime: dict[str, int] = obj.configuration["when_extended"]["end_at"]["time_point"]["time"]
                    time_object = time(
                        hour=triggerTime["hour"],
                        minute=triggerTime["minute"],
                        second=triggerTime.get("second", 0))
                    if check_time_match(time_object):
                        logging.info(f"end routine: {obj.name}")
                        Thread(target=triggerScript, args=[obj]).start()
            else:
                if "start_at" in obj.configuration["when_extended"] and "time_point" in obj.configuration["when_extended"]["start_at"] and obj.configuration["when_extended"]["start_at"]["time_point"]["type"] == "time":
                    triggerTime: dict[str, int] = obj.configuration["when_extended"]["start_at"]["time_point"]["time"]
                    time_object = time(
                        hour=triggerTime["hour"],
                        minute=triggerTime["minute"],
                        second=triggerTime.get("second", 0))
                    if check_time_match(time_object):
                        logging.info(f"execute routine: {obj.name}")
                        Thread(target=triggerScript, args=[obj]).start()
        elif "duration" in obj.configuration:
            if not obj.active and obj.enabled:
                logging.info(f"execute timer: {obj.name}")
                obj.active = True
                Thread(target=triggerScript, args=[obj]).start()

def process_smart_scene(smartscene: str, obj: SmartScene.SmartScene) -> None:
    """
    Process and execute the smart scene based on its configuration.

    Args:
        smartscene (str): The smart scene identifier.
        obj (Any): The smart scene object containing configuration details.
    """
    if hasattr(obj, "timeslots"):
        sunset_slot = -1
        sensor_obj: Sensor.Sensor = bridgeConfig["sensors"]["1"]
        sunset = sensor_obj.config["sunset"] if "lat" in sensor_obj.protocol_cfg else "21:00:00"
        slots = deepcopy(obj.timeslots)
        if hasattr(obj, "recurrence"):
            if datetime.now().strftime("%A").lower() not in obj.recurrence:
                return
        for instance, slot in enumerate(slots):
            time_object = ""
            if slot["start_time"]["kind"] == "time":
                time_object = datetime(
                    year=1,
                    month=1,
                    day=1,
                    hour=slot["start_time"]["time"]["hour"],
                    minute=slot["start_time"]["time"]["minute"],
                    second=slot["start_time"]["time"].get("second", 0)).strftime("%H:%M:%S")
            elif slot["start_time"]["kind"] == "sunset":
                sunset_slot = instance
                time_object = sunset
            if sunset_slot > 0 and instance == sunset_slot + 1:
                if sunset > time_object:
                    time_object = (datetime.strptime(sunset, "%H:%M:%S") + timedelta(minutes=30)).strftime("%H:%M:%S")
            slots[instance]["start_time"]["time"] = time_object
            slots[instance]["start_time"]["instance"] = instance

        slots = sorted(slots, key=lambda x: datetime.strptime(x["start_time"]["time"], "%H:%M:%S"))
        active_timeslot = obj.active_timeslot
        for slot in slots:
            if datetime.now().strftime("%H:%M:%S") >= slot["start_time"]["time"]:
                active_timeslot = slot["start_time"]["instance"]
        if obj.active_timeslot != active_timeslot:
            obj.active_timeslot = active_timeslot
            if obj.state == "active":
                if active_timeslot == len(obj.timeslots) - 1:
                    logging.info(f"stop smart_scene: {obj.name}")
                    group: Group.Group = findGroup(obj.group["rid"])
                    group.setV1Action(state={"on": False})
                else:
                    logging.info(f"execute smart_scene: {obj.name} scene: {obj.active_timeslot}")
                    putDict = {"recall": {"action": "active", "duration": obj.speed}, "controlled_service": "smart_scene"}
                    target_object: Scene.Scene = getObject(obj.timeslots[active_timeslot]["target"]["rtype"], obj.timeslots[active_timeslot]["target"]["rid"])
                    target_object.activate(putDict)

def runScheduler() -> None:
    """
    Run the scheduler to process schedules, behavior instances, and smart scenes.
    """
    while True:
        for schedule, obj in bridgeConfig["schedules"].items():
            obj: Schedule.Schedule = obj
            try:
                process_schedule(schedule, obj)
            except Exception as e:
                logging.info(f"Exception while processing the schedule {schedule} | {e}")

        for instance, obj in bridgeConfig["behavior_instance"].items():
            obj: BehaviorInstance.BehaviorInstance = obj
            try:
                process_behavior_instance(instance, obj)
            except Exception as e:
                logging.info(f"Exception while processing the behavior_instance {obj.name} | {e}")

        for smartscene, obj in bridgeConfig["smart_scene"].items():
            obj: SmartScene.SmartScene = obj
            try:
                process_smart_scene(smartscene, obj)
            except Exception as e:
                logging.info(f"Exception while processing the smart_scene {obj.name} | {e}")

        if "updatetime" not in bridgeConfig["config"]["swupdate2"]["autoinstall"]:
            bridgeConfig["config"]["swupdate2"]["autoinstall"]["updatetime"] = "T14:00:00"
        if datetime.now().strftime("T%H:%M:%S") == bridgeConfig["config"]["swupdate2"]["autoinstall"]["updatetime"]:
            updateManager.versionCheck()
            updateManager.githubCheck()
            if bridgeConfig["config"]["swupdate2"]["autoinstall"]["on"]:
                updateManager.githubInstall()
        if datetime.now().strftime("%M:%S") == "00:10":
            configManager.bridgeConfig.save_config()
            Thread(target=daylightSensor, args=[bridgeConfig["config"]["timezone"], bridgeConfig["sensors"]["1"]]).start()
            if datetime.now().strftime("%H") == "23" and datetime.now().strftime("%A") == "Sunday":
                configManager.bridgeConfig.save_config(backup=True)
        sleep(1)
