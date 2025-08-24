import logManager
import requests
from time import sleep

logging = logManager.logger.get_logger(__name__)

def send_request(url: str, payload: dict) -> None:
    try:
        response = requests.put(url, json=payload, timeout=3)
        response.raise_for_status()
    except requests.RequestException as e:
        logging.error("Error sending request to %s: %s", url, e)

def set_light(light, data: dict) -> None:
    base_url = f"http://{light.protocol_cfg['ip']}/api/{light.protocol_cfg['deconzUser']}/lights/{light.protocol_cfg['deconzId']}/state"
    payload = {}
    payload.update(data)
    color = {}
    if "xy" in payload:
        color["xy"] = payload.pop("xy")
    elif "ct" in payload:
        color["ct"] = payload.pop("ct")
    elif "hue" in payload:
        color["hue"] = payload.pop("hue")
    elif "sat" in payload:
        color["sat"] = payload.pop("sat")
    if payload:
        send_request(base_url, payload)
        sleep(0.7)
    if color:
        send_request(base_url, color)

def get_light_state(light) -> dict:
    url = f"http://{light.protocol_cfg['ip']}/api/{light.protocol_cfg['deconzUser']}/lights/{light.protocol_cfg['deconzId']}"
    try:
        response = requests.get(url, timeout=3)
        response.raise_for_status()
        return response.json()["state"]
    except requests.RequestException as e:
        logging.error("Error getting light state from %s: %s", url, e)
        return {}

def discover(detectedLights: list, credentials: dict) -> None:
    if "deconzUser" in credentials and credentials["deconzUser"]:
        logging.debug("deconz: <discover> invoked!")
        url = f"http://{credentials['deconzHost']}:{credentials['deconzPort']}/api/{credentials['deconzUser']}/lights"
        try:
            response = requests.get(url, timeout=3)
            response.raise_for_status()
            lights = response.json()
            for id, light in lights.items():
                modelid = "LCT015"
                if light["type"] == "Dimmable light":
                    modelid = "LWB010"
                elif light["type"] == "Color temperature light":
                    modelid = "LTW001"
                elif light["type"] == "On/Off plug-in unit":
                    modelid = "LOM001"
                elif light["type"] == "Color light":
                    modelid = "LLC010"
                detectedLights.append({
                    "protocol": "deconz",
                    "name": light["name"],
                    "modelid": modelid,
                    "protocol_cfg": {
                        "ip": f"{credentials['deconzHost']}:{credentials['deconzPort']}",
                        "deconzUser": credentials["deconzUser"],
                        "modelid": light["modelid"],
                        "deconzId": id,
                        "uniqueid": light["uniqueid"]
                    }
                })
        except requests.RequestException as e:
            logging.info("Error connecting to Deconz: %s", e)
