from time import sleep
from datetime import datetime, timedelta, timezone
from typing import Any

import configManager
from lights.protocols import protocols
import logManager
from HueObjects import Light, ApiUser

logging = logManager.logger.get_logger(__name__)
bridgeConfig = configManager.bridgeConfig.yaml_config

def syncWithLights(off_if_unreachable: bool) -> None:
    """
    Synchronize the state of the lights with their actual state.

    Args:
        off_if_unreachable (bool): If True, set state to off if the light is unreachable.
    """
    while True:
        logging.info("start lights sync")
        for key, light in bridgeConfig["lights"].items():
            light: Light.Light = light
            protocol_name: str = light.protocol
            if protocol_name in ["mqtt", "flex", "mi_box", "dummy", "wiz", "milight", "tpkasa", "hue_bl"]:
                continue
            for protocol in protocols:
                if "lights.protocols." + protocol_name == protocol.__name__:
                    try:
                        logging.debug("fetch " + light.name)
                        new_state: dict[str, Any] = protocol.get_light_state(light)
                        logging.debug(new_state)
                        light.state.update(new_state)
                        light.state["reachable"] = new_state.get("reachable", True)
                    except Exception as e:
                        light.state["reachable"] = False
                        if off_if_unreachable:
                            light.state["on"] = False
                        logging.warning(f"{light.name} is unreachable: {e}")
                    break

        sleep(10)  # wait at least 10 seconds before next sync
        i = 0
        while i < 300:  # sync with lights every 300 seconds or instant if one user is connected
            for key, user in bridgeConfig["apiUsers"].items():
                user: ApiUser.ApiUser = user
                last_use: str = user.last_use_date
                try:  # in case if last use is not a proper datetime
                    last_use_dt: datetime = datetime.strptime(last_use, "%Y-%m-%dT%H:%M:%S")
                    if abs(datetime.now(timezone.utc).replace(tzinfo=None) - last_use_dt) <= timedelta(seconds=2):
                        i = 300
                        break
                except Exception as e:
                    logging.warning(f"{user.last_use_date} is not a proper datetime: {e}")
            for key, light in bridgeConfig["lights"].items():
                protocol_name: str = light.protocol
                if protocol_name == "govee" and i > 30:  # if govee light is not used for 60 seconds, it will be turned off(use 30 seconds to be sure)
                    i = 300  # Reset i to 300 if govee light is not used
                else:
                    continue
                    
            i += 1
            sleep(1)
