import os
import zoneinfo
from typing import Any
import subprocess

def nextFreeId(bridgeConfig: dict[str, Any], element: str) -> str:
    """
    Find the next free ID for a given element in the bridge configuration.

    Args:
        bridgeConfig (dict[str, Any]): The bridge configuration.
        element (str): The element to find the next free ID for.

    Returns:
        str: The next free ID as a string.
    """
    i = 1
    while str(i) in bridgeConfig[element]:
        i += 1
    return str(i)

def get_pi_temp() -> float:
    """Read the CPU temperature and return it as a float in degrees Celsius."""
    base_path = "/sys/class/thermal"

    if os.path.exists(base_path):
        # Search for a thermal zone matching known CPU sensor type names
        for folder in os.listdir(base_path):
            if folder.startswith("thermal_zone"):
                zone_path = os.path.join(base_path, folder)
                type_file = os.path.join(zone_path, "type")
                temp_file = os.path.join(zone_path, "temp")

                if os.path.exists(type_file) and os.path.exists(temp_file):
                    with open(type_file, "r") as f:
                        zone_type = f.read().strip().lower()

                    if any(kw in zone_type for kw in ["x86_pkg_temp", "cpu-thermal", "soc_thermal", "coretemp"]):
                        with open(temp_file, "r") as tf:
                            try:
                                return round(float(tf.read().strip()) / 1000.0, 2)
                            except ValueError:
                                continue

        # Fallback: return the highest plausible temperature zone
        highest_temp = -1.0
        for folder in os.listdir(base_path):
            if folder.startswith("thermal_zone"):
                temp_file = os.path.join(base_path, folder, "temp")
                if os.path.exists(temp_file):
                    try:
                        with open(temp_file, "r") as tf:
                            t = float(tf.read().strip()) / 1000.0
                            if 5.0 < t < 100.0 and t > highest_temp:
                                highest_temp = t
                    except ValueError:
                        continue

        if highest_temp > -1.0:
            return round(highest_temp, 2)

    # Fall back to vcgencmd (works on Raspberry Pi host)
    try:
        output = subprocess.run(['vcgencmd', 'measure_temp'], capture_output=True, check=True)
        temp_str: str = output.stdout.decode()
        return float(temp_str.split('=')[1].split('\'')[0])
    except (IndexError, ValueError, subprocess.CalledProcessError, FileNotFoundError):
        pass

    raise RuntimeError('Could not get temperature')


def staticConfig() -> dict[str, Any]:
    """
    Return the static configuration for the bridge.

    Returns:
        dict[str, Any]: The static configuration.
    """
    return {
        "backup": {
            "errorcode": 0,
            "status": "idle"
        },
        "datastoreversion": "126",
        "dhcp": True,
        "factorynew": False,
        "internetservices": {
            "internet": "disconnected",
            "remoteaccess": "disconnected",
            "swupdate": "disconnected",
            "time": "disconnected"
        },
        "linkbutton": False,
        "modelid": "BSB002",
        "portalconnection": "disconnected",
        "portalservices": False,
        "portalstate": {
            "communication": "disconnected",
            "incoming": False,
            "outgoing": False,
            "signedon": False
        },
        "proxyaddress": "none",
        "proxyport": 0,
        "replacesbridgeid": None,
        "swupdate": {
            "checkforupdate": False,
            "devicetypes": {
                "bridge": False,
                "lights": [],
                "sensors": []
            },
            "notify": True,
            "text": "",
            "updatestate": 0,
            "url": ""
        },
        "swupdate2": {
            "autoinstall": {
                "on": True,
                "updatetime": "T14:00:00"
            },
            "bridge": {
                "lastinstall": "2020-12-11T17:08:55",
                "state": "noupdates"
            },
            "checkforupdate": False,
            "lastchange": "2020-12-13T10:30:15",
            "state": "noupdates"
        },
        "zigbeechannel": 25
    }

def capabilities() -> dict[str, Any]:
    """
    Return the capabilities of the bridge.

    Returns:
        dict[str, Any]: The capabilities of the bridge.
    """
    return {
        "lights": {
            "available": 60,
            "total": 63
        },
        "sensors": {
            "available": 240,
            "total": 250,
            "clip": {
                "available": 240,
                "total": 250
            },
            "zll": {
                "available": 63,
                "total": 64
            },
            "zgp": {
                "available": 63,
                "total": 64
            }
        },
        "groups": {
            "available": 60,
            "total": 64
        },
        "scenes": {
            "available": 172,
            "total": 200,
            "lightstates": {
                "available": 10836,
                "total": 12600
            }
        },
        "schedules": {
            "available": 95,
            "total": 100
        },
        "rules": {
            "available": 233,
            "total": 250,
            "conditions": {
                "available": 1451,
                "total": 1500
            },
            "actions": {
                "available": 964,
                "total": 1000
            }
        },
        "resourcelinks": {
            "available": 59,
            "total": 64
        },
        "streaming": {
            "available": 1,
            "total": 1,
            "channels": 20
        },
        "timezones": {
            "values": sorted(zoneinfo.available_timezones())
        }
    }
