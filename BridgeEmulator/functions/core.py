import zoneinfo
from typing import Dict, Any
import subprocess

def nextFreeId(bridgeConfig: Dict[str, Any], element: str) -> str:
    """
    Find the next free ID for a given element in the bridge configuration.

    Args:
        bridgeConfig (Dict[str, Any]): The bridge configuration.
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
    try:
        output: subprocess.CompletedProcess = subprocess.run(['vcgencmd', 'measure_temp'], capture_output=True, check=True)
        temp_str: str = output.stdout.decode()
        return float(temp_str.split('=')[1].split('\'')[0])
    except (IndexError, ValueError, subprocess.CalledProcessError, FileNotFoundError):
        raise RuntimeError('Could not get temperature')


def staticConfig() -> Dict[str, Any]:
    """
    Return the static configuration for the bridge.

    Returns:
        Dict[str, Any]: The static configuration.
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

def capabilities() -> Dict[str, Any]:
    """
    Return the capabilities of the bridge.

    Returns:
        Dict[str, Any]: The capabilities of the bridge.
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
