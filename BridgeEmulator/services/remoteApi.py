import base64
import json
from time import sleep
from typing import Any, Optional

import requests

import configManager
import logManager

bridgeConfig = configManager.bridgeConfig.yaml_config
logging = logManager.logger.get_logger(__name__)

def runRemoteApi() -> None:
    """
    Runs the remote API service to communicate with the remote server.

    Args:
        BIND_IP (str): The IP address to bind to.
        config (dict[str, Any]): Configuration dictionary containing API keys and settings.
    """
    BIND_IP = configManager.runtimeConfig.arg["BIND_IP"]
    config = bridgeConfig["config"]
    ip = "localhost" if BIND_IP == '' else BIND_IP
    url = 'https://remote.diyhue.org/devices'

    try:
        api_key = base64.urlsafe_b64encode(bytes(config["Hue Essentials key"], "utf8")).decode("utf-8")
    except KeyError:
        logging.error("Configuration missing 'Hue Essentials key'")
        return

    def send_request(method: str, address: str, body: Optional[dict[str, Any]] = None) -> None:
        """
        Sends a request to the bridge and posts the response to the remote server.

        Args:
            method (str): HTTP method ('GET', 'POST', 'PUT').
            address (str): The address to send the request to.
            body (Optional[dict[str, Any]], optional): The body of the request for POST and PUT methods.
        """
        try:
            if method == 'GET':
                bridgeReq = requests.get(f'http://{ip}/{address}', timeout=5)
            elif method == 'POST':
                bridgeReq = requests.post(f'http://{ip}/{address}', json=body, timeout=5)
            elif method == 'PUT':
                bridgeReq = requests.put(f'http://{ip}/{address}', json=body, timeout=5)
            else:
                logging.debug(f"Unsupported method: {method}")
                return

            requests.post(f'{url}?apikey={api_key}', timeout=5, json=json.loads(bridgeReq.text))
        except requests.RequestException as e:
            logging.error(f"Error sending request to bridge: {e}")
        except json.JSONDecodeError as e:
            logging.error(f"Error decoding JSON response from bridge: {e}")

    while config.get("Remote API enabled", False):
        try:
            response = requests.get(f'{url}?apikey={api_key}', timeout=35)
            if response.status_code == 200:
                if response.text != '{renew}':
                    try:
                        data = json.loads(response.text)
                        send_request(data["method"], data['address'], data.get("body"))
                    except json.JSONDecodeError as e:
                        logging.error(f"Error decoding JSON response from remote server: {e}")
            else:
                logging.error(f"Remote server error: {response.status_code}, {response.text}")
                sleep(30)  # don't overload the remote server
        except requests.RequestException as e:
            logging.error(f"Remote server is down: {e}")
            sleep(60)  # don't overload the remote server
