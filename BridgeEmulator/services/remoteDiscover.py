import requests
from time import sleep
from typing import Any
import signal

import configManager
import logManager

bridgeConfig = configManager.bridgeConfig.yaml_config
logging = logManager.logger.get_logger(__name__)

### This service is needed for Hue Essentials to automatically discover the diyhue instance.

SLEEP_INTERVAL = 60
DISCOVERY_URL = 'https://discovery.diyhue.org'
running = True

def runRemoteDiscover(timeout: int = 5) -> None:
    """
    Run the remote discovery service to allow Hue Essentials to discover the diyhue instance.
    
    Args:
        config (dict[str, Any]): Configuration dictionary.
        timeout (int): Timeout for the requests in seconds.
    """
    logging.info("Starting discovery service")
    config = bridgeConfig["config"]

    if not validate_config(config):
        return

    retry_delay = SLEEP_INTERVAL
    while running:
        try:
            payload = {
                "id": config["bridgeid"],
                "internalipaddress": config["ipaddress"],
                "macaddress": config["mac"],
                "name": config["name"]
            }
            response = requests.post(DISCOVERY_URL, timeout=timeout, json=payload)
            response.raise_for_status()
            if response.status_code != 200:
                logging.debug(f"Discovery service response status code: {response.status_code}")
            retry_delay = SLEEP_INTERVAL  # Reset retry delay on success
            sleep(SLEEP_INTERVAL)
        except requests.exceptions.RequestException as e:
            handle_request_exception(e, retry_delay)
            retry_delay = min(retry_delay * 2, 3600)  # Exponential backoff, max 1 hour
        except Exception as e:
            handle_unexpected_exception(e, retry_delay)
            retry_delay = min(retry_delay * 2, 3600)  # Exponential backoff, max 1 hour

def validate_config(config: dict[str, Any]) -> bool:
    """
    Validate that the required keys are present in the config dictionary.
    
    Args:
        config (dict[str, Any]): Configuration dictionary.
    
    Returns:
        bool: True if all required keys are present, False otherwise.
    """
    required_keys = ["bridgeid", "ipaddress", "mac", "name"]
    for key in required_keys:
        if key not in config:
            logging.error(f"Missing required config key: {key}")
            return False
    return True

def handle_request_exception(e: requests.exceptions.RequestException, retry_delay: int) -> None:
    """
    Handle exceptions raised by the requests library.
    
    Args:
        e (requests.exceptions.RequestException): The exception raised.
        retry_delay (int): The current retry delay in seconds.
    """
    logging.error(f"Request failed: {e}. Retrying in {retry_delay} seconds.")
    sleep(retry_delay)

def handle_unexpected_exception(e: Exception, retry_delay: int) -> None:
    """
    Handle unexpected exceptions.
    
    Args:
        e (Exception): The exception raised.
        retry_delay (int): The current retry delay in seconds.
    """
    logging.error(f"An unexpected error occurred: {e}. Retrying in {retry_delay} seconds.")
    sleep(retry_delay)

def signal_handler(sig: int, frame: Any) -> None:
    """
    Handle termination signals to stop the discovery service.
    
    Args:
        sig (int): Signal number.
        frame (Any): Current stack frame.
    """
    global running
    logging.info("Stopping discovery service")
    running = False

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)
