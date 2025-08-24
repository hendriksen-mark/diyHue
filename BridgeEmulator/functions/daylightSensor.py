from astral.sun import sun
from astral import LocationInfo
from functions.rules import rulesProcessor
from datetime import datetime, timezone
from time import sleep
from threading import Thread
from functions.scripts import triggerScript
import logManager
import configManager
from typing import Any
from HueObjects import Sensor, BehaviorInstance

bridgeConfig = configManager.bridgeConfig.yaml_config
logging = logManager.logger.get_logger(__name__)

def runBackgroundSleep(instance: dict[str, Any], seconds: float) -> None:
    """
    Run a background sleep for a specified number of seconds and then trigger a script.

    Args:
        instance (dict[str, Any]): The instance configuration.
        seconds (float): The number of seconds to sleep.
    """
    sleep(seconds)
    triggerScript(instance)

def calculate_offsets(sensor: Sensor.Sensor, sun_times: dict[str, datetime]) -> dict[str, float]:
    """
    Calculate the offsets for sunset and sunrise based on the sensor configuration.

    Args:
        sensor (Sensor.Sensor): The sensor object containing configuration.
        sun_times (dict[str, datetime]): The dictionary containing sunrise and sunset times.

    Returns:
        dict[str, float]: A dictionary with calculated offsets for sunset and sunrise.
    """
    delta_sunset = sun_times['sunset'].replace(tzinfo=None) - datetime.now(timezone.utc).replace(tzinfo=None)
    delta_sunrise = sun_times['sunrise'].replace(tzinfo=None) - datetime.now(timezone.utc).replace(tzinfo=None)
    return {
        "sunset": delta_sunset.total_seconds() + sensor.config["sunsetoffset"] * 60,
        "sunrise": delta_sunrise.total_seconds() + sensor.config["sunriseoffset"] * 60
    }

def update_sensor_state(sensor: Sensor.Sensor, is_daylight: bool, current_time: datetime) -> None:
    """
    Update the sensor state and process rules based on the current time.

    Args:
        sensor (Sensor.Sensor): The sensor object to update.
        is_daylight (bool): The daylight state to set.
        current_time (datetime): The current time.
    """
    sensor.state = {"daylight": is_daylight, "lastupdated": current_time.strftime("%Y-%m-%dT%H:%M:%S")}
    sensor.dxState["daylight"] = current_time
    rulesProcessor(sensor, current_time)

def handle_sleep(offset: float, sensor: Sensor.Sensor, is_daylight: bool, current_time: datetime) -> None:
    """
    Handle the sleep for the specified offset and update the sensor state.

    Args:
        offset (float): The number of seconds to sleep.
        sensor (Sensor.Sensor): The sensor object to update.
        is_daylight (bool): The daylight state to set after sleep.
        current_time (datetime): The current time.
    """
    sleep(offset)
    logging.debug(f"sleep finish at {current_time.strftime('%Y-%m-%dT%H:%M:%S')}")
    update_sensor_state(sensor, is_daylight, current_time)

def daylightSensor(tz: str, sensor: Sensor.Sensor) -> None:
    """
    Main function to handle the daylight sensor logic.

    Args:
        tz (str): The timezone string.
        sensor (Sensor.Sensor): The sensor object containing configuration and state.
    """
    if not sensor.config["configured"]:
        logging.debug("Daylight Sensor: location is not configured")
        return

    localzone = LocationInfo('localzone', tz.split("/")[1], tz, sensor.protocol_cfg["lat"], sensor.protocol_cfg["long"])
    sun_times = sun(localzone.observer, date=datetime.now(timezone.utc).replace(tzinfo=None))
    offsets = calculate_offsets(sensor, sun_times)
    logging.info(f"deltaSunsetOffset: {offsets['sunset']}")
    logging.info(f"deltaSunriseOffset: {offsets['sunrise']}")
    sensor.config["sunset"] = sun_times['sunset'].astimezone().strftime("%H:%M:%S")
    current_time = datetime.now(timezone.utc).replace(tzinfo=None)

    sensor.state["daylight"] = offsets["sunrise"] < 0 < offsets["sunset"]
    logging.info(f"set daylight sensor to {'true' if sensor.state['daylight'] else 'false'}")

    if 0 < offsets["sunset"] < 3600:
        logging.info("will start the sleep for sunset")
        handle_sleep(offsets["sunset"], sensor, False, current_time)
    elif 0 < offsets["sunrise"] < 3600:
        logging.info("will start the sleep for sunrise")
        handle_sleep(offsets["sunrise"], sensor, True, current_time)

    # v2 api routines
    for key, instance in bridgeConfig["behavior_instance"].items():
        instance: BehaviorInstance.BehaviorInstance = instance
        if instance.enabled and "when_extended" in instance.configuration:
            offset = 0
            time_point = instance.configuration["when_extended"]["start_at"]["time_point"]
            if "offset" in time_point:
                offset = 60 * time_point["offset"]["minutes"]
            if time_point["type"] == "sunrise" and 0 < offsets["sunrise"] + offset < 3600:
                Thread(target=runBackgroundSleep, args=[instance, offsets["sunrise"] + offset]).start()
            elif time_point["type"] == "sunset" and 0 < offsets["sunset"] + offset < 3600:
                Thread(target=runBackgroundSleep, args=[instance, offsets["sunset"] + offset]).start()
