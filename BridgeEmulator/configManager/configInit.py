import logManager
import subprocess
from typing import Any, Optional

logging = logManager.logger.get_logger(__name__)

def _get_default_gateway() -> Optional[str]:
    """
    Get the default gateway IP address.

    Returns:
        Optional[str]: The default gateway IP address or None if not found.
    """
    result = subprocess.run(
        ["ip route | grep default | head -n 1 | cut -d ' ' -f 3"],
        shell=True,
        capture_output=True, 
        text=True
    )
    default_route = next((line for line in result.stdout.splitlines() if "default" in line), None)
    return default_route.split()[2] if default_route else None

def write_args(args: dict[str, str], yaml_config: dict[str, Any]) -> dict[str, Any]:
    """
    Write arguments to the YAML configuration.
    
    Args:
        args (dict[str, str]): Arguments containing HOST_IP, FULLMAC, and MAC.
        yaml_config (dict[str, Any]): The YAML configuration to update.
    
    Returns:
        dict[str, Any]: The updated YAML configuration.
    """
    gateway_ip = _get_default_gateway()
    host_ip = args["HOST_IP"]
    ip_pieces = gateway_ip if gateway_ip else f"{host_ip.rsplit('.', 1)[0]}.1"
    
    yaml_config["config"]["ipaddress"] = host_ip
    yaml_config["config"]["gateway"] = ip_pieces
    yaml_config["config"]["mac"] = args["FULLMAC"]
    yaml_config["config"]["bridgeid"] = (args["MAC"][:6] + 'FFFE' + args["MAC"][-6:]).upper()
    return yaml_config
