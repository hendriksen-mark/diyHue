import logManager
from services.homeAssistantWS import connect_if_required, latest_states
from typing import Any

logging = logManager.logger.get_logger(__name__)

def translate_homeassistant_state_to_diyhue_state(existing_diy_hue_state: dict[str, Any], ha_state: dict[str, Any]) -> dict[str, Any]:
    """
    Translate Home Assistant state to Diy Hue state.

    Args:
        existing_diy_hue_state: The current state of the Diy Hue light.
        ha_state: The state of the Home Assistant light.

    Returns:
        A dictionary representing the translated Diy Hue state.
    """
    """
    Home Assistant:
    {
        "entity_id": "light.my_light",
        "state": "off",
        "attributes": {
            "min_mireds": 153,
            "max_mireds": 500,
            # If using color temp
            "brightness": 254, "color_temp": 345,
            # If using colour:
            "brightness": 254, "hs_color": [262.317, 64.314], "rgb_color": [151, 90, 255], "xy_color": [0.243, 0.129]
            "effect_list": ["colorloop", "random"],
            "friendly_name": "My Light",
            "supported_features": 63
        },
        "last_changed": "2020-12-09T17:46:40.569891+00:00",
        "last_updated": "2020-12-09T17:46:40.569891+00:00",
    }

    Diy Hue:
    "state": {
        "alert": "select",
        "bri": 249,
        # Either ct, hs or xy
        # If ct then uses ct
        # If xy uses xy
        # If hs uses hue/sat
        "colormode": "xy",
        "effect": "none",
        "ct": 454,
        "hue": 0,
        "on": true,
        "reachable": true,
        "sat": 0,
        "xy": [
            0.478056,
            0.435106
        ]
    },
    """

    try:
        diyhue_state = existing_diy_hue_state.copy()

        reachable = ha_state.get('state') in ['on', 'off']
        is_on = ha_state.get('state') == 'on'

        diyhue_state.update({
            "reachable": reachable,
            "on": is_on
        })

        if is_on and "attributes" in ha_state:
            attributes = ha_state['attributes']
            if "brightness" in attributes:
                diyhue_state['bri'] = attributes['brightness']
            if "color_temp" in attributes:
                diyhue_state.update({
                    'ct': attributes['color_temp'],
                    'colormode': 'ct'
                })
            if "xy_color" in attributes:
                diyhue_state.update({
                    'xy': attributes['xy_color'],
                    'colormode': 'xy'
                })

        return diyhue_state
    except Exception as e:
        logging.error(f"Error translating Home Assistant state to Diy Hue state: {e}")
        return existing_diy_hue_state

def set_light(light, data: dict[str, Any]) -> None:
    """
    Set the state of a light.

    Args:
        light: The light object to set the state for.
        data: The state data to set on the light.
    """
    try:
        connection = connect_if_required()
        if connection is None:
            logging.error("Error setting light state: Home Assistant WebSocket connection is not available")
            return
        connection.change_light(light, data)
    except Exception as e:
        logging.error(f"Error setting light state: {e}")

def get_light_state(light) -> dict[str, Any]:
    """
    Get the current state of a light.

    Args:
        light: The light object to get the state for.

    Returns:
        A dictionary representing the current state of the light.
    """
    try:
        connect_if_required()
        entity_id = light.protocol_cfg["entity_id"]
        homeassistant_state = latest_states.get(entity_id, {})
        existing_diy_hue_state = light.state
        return translate_homeassistant_state_to_diyhue_state(existing_diy_hue_state, homeassistant_state)
    except Exception as e:
        logging.error(f"Error getting light state: {e}")
        return light.state
