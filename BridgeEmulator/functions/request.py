import requests
from time import sleep
from typing import Union, Optional
import logManager

logging = logManager.logger.get_logger(__name__)

def sendRequest(url: str, method: str, data: Optional[Union[dict, str]] = None, timeout: int = 3, delay: int = 0, retries: int = 3, retry_delay: int = 1) -> str:
    """
    Send an HTTP request with the specified method to the given URL.

    Args:
        url (str): The URL to send the request to.
        method (str): The HTTP method to use ('GET', 'POST', 'PUT').
        data (Optional[Union[dict, str]]): The data to send with the request (for POST and PUT).
        timeout (int): The timeout for the request in seconds.
        delay (int): The delay before sending the request in seconds.
        retries (int): The number of retry attempts in case of failure.
        retry_delay (int): The delay between retry attempts in seconds.

    Returns:
        str: The response text from the request.
    """
    if delay > 0:
        sleep(delay)
    
    if not url.startswith('http'):
        url = "http://127.0.0.1" + url
    
    headers = {"Content-type": "application/json"}
    method = method.upper()
    
    if method not in {"POST", "PUT", "GET"}:
        raise ValueError(f"Unsupported method: {method}")
    
    request_func = getattr(requests, method.lower())
    
    for attempt in range(retries):
        try:
            response: Optional[requests.Response] = None
            if method in {"POST", "PUT"}:
                data = data.encode("utf8") if isinstance(data, str) else data
                response = request_func(url, json=data if isinstance(data, dict) else data, timeout=timeout, headers=headers)
            else:
                response = request_func(url, timeout=timeout, headers=headers)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logging.error(f"Request failed: {e}")
            if attempt < retries - 1:
                logging.info(f"Retrying... ({attempt + 1}/{retries})")
                sleep(retry_delay)
            else:
                logging.error(f"Request failed after {retries} attempts: {e}")
                return
