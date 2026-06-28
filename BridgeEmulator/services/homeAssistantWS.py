import json
import threading
import time
from typing import Any, List, Optional

from ws4py.client.threadedclient import WebSocketClient

import logManager

logging = logManager.logger.get_logger(__name__)

discovery_timeout_seconds = 60
discovery_result = threading.Event()
next_connection_error_log = 0
logging_backoff = 2  # 2 Second back off
homeassistant_token = ''
homeassistant_url = 'ws://127.0.0.1:8123/api/websocket'
homeassistant_ws_client = None
include_by_default = False
use_https = False

latest_states: dict[str, dict[str, Any]] = {}


class HomeAssistantClient(WebSocketClient):
    """
    WebSocket client for Home Assistant integration.
    """
    message_id = 1
    id_to_type: dict[int, str] = {}

    def opened(self) -> None:
        """Called when the WebSocket connection is opened."""
        logging.info("Home Assistant WebSocket Connection Opened")

    def closed(self, code: int, reason: Optional[str] = None) -> None:
        """
        Called when the WebSocket connection is closed.

        Args:
            code (int): The close code.
            reason (str, optional): The reason for closing. Defaults to None.
        """
        logging.info(
            "Home Assistant WebSocket Connection Closed. Code: {} Reason: {}".format(code, reason))
        for home_assistant_state in latest_states.values():
            if 'state' in home_assistant_state:
                home_assistant_state['state'] = 'unavailable'

    def received_message(self, m: Any) -> None:
        """
        Called when a message is received from the WebSocket.

        Args:
            m (Any): The received message.
        """
        try:
            message_text = m.data.decode(m.encoding)
            message = json.loads(message_text)
            message_type = message.get('type', None)
            if message_type == "auth_required":
                self.do_auth_required(message)
            elif message_type == "auth_ok":
                self.do_auth_complete()
            elif message_type == "auth_invalid":
                self.do_auth_invalid(message)
            elif message_type == "result":
                self.do_result(message)
            elif message_type == "event":
                self.do_event(message)
            elif message_type == "pong":
                self.do_pong(message)
            else:
                logging.warning("Unexpected message: {}".format(message))
        except Exception as e:
            logging.exception("Error processing received message: {}".format(e))

    def do_auth_required(self, m: dict[str, Any]) -> None:
        """
        Handle authentication required message.

        Args:
            m (dict[str, Any]): The message.
        """
        logging.info("Home Assistant Web Socket Authorisation required")
        payload = {
            'type': 'auth',
            'access_token': homeassistant_token
        }
        self._send(payload)

    def do_auth_invalid(self, message: dict[str, Any]) -> None:
        """
        Handle invalid authentication message.

        Args:
            message (dict[str, Any]): The message.
        """
        logging.error(
            "Home Assistant Web Socket Authorisation invalid: {}".format(message))

    def do_auth_complete(self) -> None:
        """Handle successful authentication message."""
        logging.info("Home Assistant Web Socket Authorisation complete")
        self.get_all_lights()
        self.subscribe_for_updates()

    def get_all_lights(self) -> None:
        """Request all light states from Home Assistant."""
        discovery_result.clear()
        payload = {
            'type': 'get_states'
        }
        self._send_with_id(payload, "getstates")

    def subscribe_for_updates(self) -> None:
        """Subscribe to state change events from Home Assistant."""
        payload = {
            "type": "subscribe_events",
            "event_type": "state_changed"
        }
        self._send_with_id(payload, "subscribe")

    def change_light(self, light: Any, data: dict[str, Any]) -> None:
        """
        Change the state of a light in Home Assistant.

        Args:
            light (Any): The light object.
            data (dict[str, Any]): The data to change the light state.
        """
        service_data: dict[str, Any] = {}
        service_data['entity_id'] = light.protocol_cfg['entity_id']
        if light.protocol_cfg['entity_id'].startswith("light."):
            payload = {
                "type": "call_service",
                "domain": "light",
                "service_data": service_data
            }
        elif light.protocol_cfg['entity_id'].startswith("switch."):
            payload = {
                "type": "call_service",
                "domain": "switch",
                "service_data": service_data
            }
        payload["service"] = "turn_on"
        if 'on' in data:
            if not data['on']:
                payload["service"] = "turn_off"

        color_from_hsv = False
        for key, value in data.items():
            if key == "ct":
                service_data['color_temp_kelvin'] = 1000000 / value
            if key == "bri":
                service_data['brightness'] = value
            if key == "xy":
                service_data['xy_color'] = [value[0], value[1]]
            if key == "hue" or key == "sat":
                color_from_hsv = True
            if key == "on":
                payload["service"] = "turn_on" if value else "turn_off"
            if key == "alert":
                service_data['flash'] = "long"
            if key == "transitiontime":
                service_data['transition'] = value / 10

        if color_from_hsv:
            service_data['hs_color'] = [data['hue'], data['sat']]

        self._send_with_id(payload, "service")

    def do_result(self, message: dict[str, Any]) -> None:
        """
        Handle result messages from Home Assistant.

        Args:
            message (dict[str, Any]): The message.
        """
        if 'result' in message and message['result']:
            message_type = self.id_to_type.pop(message['id'], None)
            if message_type == "getstates":
                latest_states.clear()
                for ha_state in message['result']:
                    if self._should_include(ha_state):
                        entity_id = ha_state.get('entity_id', None)
                        logging.info(f"Found {entity_id}")
                        latest_states[entity_id] = ha_state
                discovery_result.set()

    def do_pong(self, message: dict[str, Any]) -> None:
        """
        Handle pong messages from Home Assistant.

        Args:
            message (dict[str, Any]): The message.
        """
        logging.debug("Pong received from Home Assistant: {}".format(message))

    def do_event(self, message: dict[str, Any]) -> None:
        """
        Handle event messages from Home Assistant.

        Args:
            message (dict[str, Any]): The message.
        """
        try:
            event_type = message['event']['event_type']
            if event_type == 'state_changed':
                self.do_state_changed(message)
        except KeyError:
            logging.exception("No event_type in event")

    def do_state_changed(self, message: dict[str, Any]) -> None:
        """
        Handle state changed events from Home Assistant.

        Args:
            message (dict[str, Any]): The message.
        """
        try:
            entity_id = message['event']['data']['entity_id']
            new_state = message['event']['data']['new_state']
            if self._should_include(new_state):
                logging.debug("State update received for {}, new state {}".format(
                    entity_id, new_state))
                latest_states[entity_id] = new_state
        except KeyError as e:
            logging.exception("No state in event: {}".format(message))

    def _should_include(self, ha_state: dict[str, Any]) -> bool:
        """
        Determine if a Home Assistant state should be included.

        Args:
            ha_state (dict[str, Any]): The Home Assistant state.

        Returns:
            bool: True if the state should be included, False otherwise.
        """
        should_include = False
        diy_hue_flag = None
        entity_id = ha_state.get('entity_id', None)
        if entity_id and (entity_id.startswith("light.") or entity_id.startswith("switch.")):
            if 'attributes' in ha_state and 'diyhue' in ha_state['attributes']:
                diy_hue_flag = ha_state['attributes']['diyhue']

            if include_by_default:
                should_include = diy_hue_flag != "exclude"
            else:
                should_include = diy_hue_flag == "include"
        return should_include

    def _send_with_id(self, payload: dict[str, Any], type_of_call: str) -> None:
        """
        Send a message with an ID to Home Assistant.

        Args:
            payload (dict[str, Any]): The message payload.
            type_of_call (str): The type of call.
        """
        payload['id'] = self.message_id
        self.id_to_type[self.message_id] = type_of_call
        self.message_id += 1
        self._send(payload)

    def _send(self, payload: dict[str, Any]) -> None:
        """
        Send a message to Home Assistant.

        Args:
            payload (dict[str, Any]): The message payload.
        """
        json_payload = json.dumps(payload)
        self.send(json_payload)


def connect_if_required() -> Optional[HomeAssistantClient]:
    """
    Connect to Home Assistant WebSocket if not already connected.

    Returns:
        Optional[HomeAssistantClient]: The WebSocket client, or None if connection failed.
    """
    if homeassistant_ws_client is None or homeassistant_ws_client.client_terminated:
        create_websocket_client()

    return homeassistant_ws_client


def create_websocket_client() -> None:
    """
    Create a new WebSocket client for Home Assistant.
    """
    global homeassistant_ws_client
    global next_connection_error_log
    global logging_backoff
    if time.time() >= next_connection_error_log:
        logging.warning(
            "Home Assistant Web Socket Client disconnected trying to (re)connect")

    try:
        homeassistant_ws_client = HomeAssistantClient(
            homeassistant_url, protocols=['http-only', 'chat'])
        homeassistant_ws_client.connect()
        logging.info("Home Assistant Web Socket Client connected")
    except Exception as e:
        if time.time() >= next_connection_error_log:
            logging.exception("Error connecting to Home Assistant WebSocket: {}".format(e))
            next_connection_error_log = time.time() + logging_backoff
            logging_backoff *= 2
        homeassistant_ws_client = None


def create_ws_client(bridgeConfig: dict[str, Any]) -> None:
    """
    Create a WebSocket client for Home Assistant using the bridge configuration.

    Args:
        bridgeConfig (dict[str, Any]): The bridge configuration.
    """
    global homeassistant_token
    global homeassistant_url
    global include_by_default
    global use_https

    homeassistant_ip = bridgeConfig["config"]["homeassistant"].get('homeAssistantIp', '127.0.0.1')
    homeAssistant_port = bridgeConfig["config"]["homeassistant"].get('homeAssistantPort', 8123)
    homeassistant_token = bridgeConfig["config"]["homeassistant"].get('homeAssistantToken', '')
    include_by_default = bridgeConfig["config"]["homeassistant"].get('homeAssistantIncludeByDefault', False)
    use_https = bridgeConfig["config"]["homeassistant"].get('homeAssistantUseHttps', False)

    ws_prefix = "wss" if use_https else "ws"
    homeassistant_url = f'{ws_prefix}://{homeassistant_ip}:{homeAssistant_port}/api/websocket'
    connect_if_required()


def discover(detectedLights: List[dict[str, Any]]) -> None:
    """
    Discover lights from Home Assistant and add them to the detectedLights list.

    Args:
        detectedLights (List[dict[str, Any]]): The list to add discovered lights to.
    """
    logging.info("HomeAssistant WebSocket discovery called")
    client = connect_if_required()
    if client is None:
        logging.warning("HomeAssistant WebSocket discovery aborted: client not connected")
        return
    client.get_all_lights()
    logging.info("HomeAssistant WebSocket discovery waiting for devices")
    completed = discovery_result.wait(timeout=discovery_timeout_seconds)
    logging.info("HomeAssistant WebSocket discovery devices received, timeout? {}".format(
        not completed))
    # This only loops over discovered devices so we have already filtered out what we don't want
    for entity_id in latest_states.keys():
        ha_state = latest_states[entity_id]
        lightName = ha_state["attributes"].get("friendly_name", entity_id)

        logging.info("HomeAssistant_ws: found light {}".format(lightName))
        # From Home Assistant lights/__init.py__
        UNKNOWN = "unknown"  # Ambiguous color mode
        ONOFF = "onoff"  # Must be the only supported mode
        BRIGHTNESS = "brightness"  # Must be the only supported mode
        COLOR_TEMP = "color_temp"
        HS = "hs"
        XY = "xy"
        RGB = "rgb"
        RGBW = "rgbw"
        RGBWW = "rgbww"
        WHITE = "white"  # Must *NOT* be the only supported mode

        supported_colourmodes = ha_state.get('attributes', {}).get('supported_color_modes', [])

        model_id = None
        if HS in supported_colourmodes or XY in supported_colourmodes or RGB in supported_colourmodes or RGBW in supported_colourmodes or RGBWW in supported_colourmodes and COLOR_TEMP in supported_colourmodes:
            model_id = "LCT015"
        elif COLOR_TEMP in supported_colourmodes:
            model_id = "LTW001"
        elif XY in supported_colourmodes:
            model_id = "LLC010"
        elif BRIGHTNESS in supported_colourmodes:
            model_id = "LWB010"
        elif ONOFF in supported_colourmodes and BRIGHTNESS not in supported_colourmodes:
            model_id = "LOM001"
        else:
            logging.info("unknown model id " + str(supported_colourmodes))
            continue

        protocol_cfg = {"entity_id": entity_id, "ip": "none"}

        detectedLights.append({"protocol": "homeassistant_ws", "name": lightName, "modelid": model_id, "protocol_cfg": protocol_cfg})

    logging.info("HomeAssistant WebSocket discovery complete")
