import logManager
import json
from typing import Any

# External
import paho.mqtt.publish as publish

# internal functions
from functions.colors import hsv_to_rgb, convert_xy

logging = logManager.logger.get_logger(__name__)

def create_payload(lightsData: dict[str, Any], light) -> dict[str, Any]:
    """
    Create the payload for the MQTT message based on the light data.

    Args:
        lightsData (dict[str, Any]): The data for the lights.
        light (Any): The light object.

    Returns:
        dict[str, Any]: The payload for the MQTT message.
    """
    payload = {"transition": 0.3}
    colorFromHsv = False
    for key, value in lightsData.items():
        if key == "on":
            payload['state'] = "ON" if value else "OFF"
        elif key == "bri":
            if "brightness_scale" in light.protocol_cfg:
                value = value * light.protocol_cfg["brightness_scale"] / 254
            payload['brightness'] = value
        elif key == "xy":
            payload['color'] = {'x': value[0], 'y': value[1]}
        elif key == "gradient":
            rgbs = [convert_xy(xy_record['color']['xy']['x'], xy_record['color']['xy']['y'], 255) for xy_record in value['points']]
            hexes = ["#" + "".join(format(int(round(c)), '02x') for c in rgb) for rgb in rgbs]
            hexes.reverse()
            payload['gradient'] = hexes
        elif key == "ct":
            payload["color_temp"] = value
        elif key in {"hue", "sat"}:
            colorFromHsv = True
        elif key == "alert" and value != "none":
            payload['alert'] = value
        elif key == "transitiontime":
            payload['transition'] = value / 10
        elif key == "effect":
            payload["effect"] = value
    if colorFromHsv:
        color = hsv_to_rgb(lightsData['hue'], lightsData['sat'], light.state["bri"])
        payload['color'] = {'r': color[0], 'g': color[1], 'b': color[2]}
    return payload

def set_light(light, data: dict[str, Any]) -> None:
    """
    Set the light state via MQTT.

    Args:
        light : The light object.
        data (dict[str, Any]): The data to set the light state.
    """
    messages = []
    lightsData = data.get("lights", {light.protocol_cfg["command_topic"]: data})

    for topic, light_data in lightsData.items():
        payload = create_payload(light_data, light)
        messages.append({"topic": topic, "payload": json.dumps(payload)})

    logging.debug("MQTT publish to: " + json.dumps(messages))
    auth = None
    mqtt_server = light.protocol_cfg["mqtt_server"]
    if mqtt_server["mqttUser"] and mqtt_server["mqttPassword"]:
        auth = {'username': mqtt_server["mqttUser"], 'password': mqtt_server["mqttPassword"]}
    publish.multiple(messages, hostname=mqtt_server["mqttServer"], port=mqtt_server["mqttPort"], auth=auth)

def discover(mqtt_config: dict[str, Any]) -> None:
    """
    Discover devices via MQTT.

    Args:
        mqtt_config (dict[str, Any]): The MQTT configuration.
    """
    if mqtt_config["enabled"]:
        logging.info("MQTT discovery called")
        auth = None
        if mqtt_config["mqttUser"] and mqtt_config["mqttPassword"]:
            auth = {'username': mqtt_config["mqttUser"], 'password': mqtt_config["mqttPassword"]}
        try:
            publish.single("zigbee2mqtt/bridge/request/permit_join", json.dumps({"value": True, "time": 120}), hostname=mqtt_config["mqttServer"], port=mqtt_config["mqttPort"], auth=auth)
            publish.single("zigbee2mqtt/bridge/config/devices/get", hostname=mqtt_config["mqttServer"], port=mqtt_config["mqttPort"], auth=auth)
        except Exception as e:
            logging.error(str(e))
