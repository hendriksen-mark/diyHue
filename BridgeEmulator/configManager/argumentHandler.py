import argparse
import logManager
from os import getenv, path
from functions.network import getIpAddress
from subprocess import check_output
from typing import Union
import pathlib
from services.genCert import gen_cert_python

logging = logManager.logger.get_logger(__name__)

def get_environment_variable(var: str, boolean: bool = False) -> Union[str, bool]:
    """
    Retrieve the value of an environment variable.

    Args:
        var (str): The name of the environment variable.
        boolean (bool): If True, interpret the value as a boolean.

    Returns:
        str or bool: The value of the environment variable, or False if boolean is True and the value is not "true".
    """
    value = getenv(var)
    if boolean and value:
        value = value.lower() == "true"
    return value

def generate_certificate(mac: str, configPath: str, runningPath: str) -> None:
    """
    Generate a certificate using the provided MAC address and save it to the specified path.

    Args:
        mac (str): The MAC address to use for certificate generation.
        path (str): The path where the certificate will be saved.
    """
    logging.info("Generating certificate")
    serial: str = mac[:6] + "fffe" + mac[-6:]
    success: bool = gen_cert_python(serial, configPath, runningPath)
    if success:
        logging.info("Certificate created")
    else:
        logging.error("Certificate generation failed")
        raise Exception("Certificate generation failed")

def process_arguments(config, args: dict[str, Union[str, bool]]) -> None:
    """
    Process the provided arguments and configure logging and certificate generation.

    Args:
        config (configHandler.Config): The configuration object.
        args (dict): A dictionary of arguments.
    """
    log_level: str = "DEBUG" if args["DEBUG"] else "INFO"
    logManager.logger.configure_logger(log_level)
    logging.info(f"Debug logging {'enabled' if args['DEBUG'] else 'disabled'}!")

    if not path.isfile(path.join(config.configDir, "cert.pem")):
        generate_certificate(args["MAC"], config.configDir, config.runningDir)

def parse_arguments() -> dict[str, Union[str, int, bool]]:
    """
    Parse command-line arguments and environment variables to configure the application.

    Returns:
        dict: A dictionary containing the parsed arguments and their values.
    """
    argumentDict: dict[str, Union[str, int, bool]] = {
        "BIND_IP": '0.0.0.0', "HOST_IP": '', "HTTP_PORT": 80, "HTTPS_PORT": 443,
        "FULLMAC": '', "MAC": '', "DEBUG": False, "DOCKER": False,
        "noLinkButton": False, "noServeHttps": False
    }
    ap: argparse.ArgumentParser = argparse.ArgumentParser()

    # Arguments can also be passed as Environment Variables.
    ap.add_argument("--debug", action='store_true', help="Enables debug output")
    ap.add_argument("--bind-ip", help="The IP address to listen on", type=str)
    ap.add_argument("--config_path", help="Set certificate and config files location", type=str)
    ap.add_argument("--docker", action='store_true', help="Enables setup for use in docker container")
    ap.add_argument("--ip", help="The IP address of the host system (Docker)", type=str)
    ap.add_argument("--http-port", help="The port to listen on for HTTP (Docker)", type=int)
    ap.add_argument("--https-port", help="The port to listen on for HTTPS (Docker)", type=int)
    ap.add_argument("--mac", help="The MAC address of the host system (Docker)", type=str)
    ap.add_argument("--no-serve-https", action='store_true', help="Don't listen on port 443 with SSL")
    ap.add_argument("--no-link-button", action='store_true', help="DANGEROUS! Don't require the link button to be pressed to pair the Hue app, just allow any app to connect")

    args: argparse.Namespace = ap.parse_args()

    argumentDict["noLinkButton"] = args.no_link_button
    argumentDict["noServeHttps"] = args.no_serve_https
    argumentDict["DEBUG"] = args.debug or get_environment_variable('DEBUG', True)
    argumentDict["CONFIG_PATH"] = args.config_path or get_environment_variable('CONFIG_PATH') or '/opt/hue-emulator/config'
    argumentDict["BIND_IP"] = args.bind_ip or get_environment_variable('BIND_IP') or '0.0.0.0'
    argumentDict["HOST_IP"] = args.ip or get_environment_variable('IP') or argumentDict["BIND_IP"] if argumentDict["BIND_IP"] != '0.0.0.0' else getIpAddress()
    argumentDict["HTTP_PORT"] = args.http_port or get_environment_variable('HTTP_PORT') or 80
    argumentDict["HTTPS_PORT"] = args.https_port or get_environment_variable('HTTPS_PORT') or 443
    argumentDict["RUNNING_PATH"] = str(pathlib.Path(__file__).parent.parent)


    logging.info("Using Host %s:%s" % (argumentDict["HOST_IP"], argumentDict["HTTP_PORT"]))
    logging.info("Using Host %s:%s" % (argumentDict["HOST_IP"], argumentDict["HTTPS_PORT"]))

    if args.mac and str(args.mac).replace(":", "").capitalize() != "XXXXXXXXXXXX":
        dockerMAC: str = args.mac  # keeps : for cert generation
        mac: str = str(args.mac).replace(":", "")
    elif get_environment_variable('MAC') and get_environment_variable('MAC').strip('\u200e').replace(":", "").capitalize() != "XXXXXXXXXXXX":
        dockerMAC: str = get_environment_variable('MAC').strip('\u200e')
        mac: str = str(dockerMAC).replace(":", "")
    else:
        dockerMAC: str = check_output("cat /sys/class/net/$(ip -o addr | grep %s | awk '{print $2}')/address" % argumentDict["HOST_IP"],
                                 shell=True).decode('utf-8')[:-1]
        mac: str = str(dockerMAC).replace(":", "")

    argumentDict["FULLMAC"] = dockerMAC
    argumentDict["MAC"] = mac
    argumentDict["DOCKER"] = args.docker or get_environment_variable('DOCKER', True)

    if mac.capitalize() == "XXXXXXXXXXXX" or not mac:
        logging.exception(f"No valid MAC address provided {mac}")
        logging.exception("To fix this visit: https://diyhue.readthedocs.io/en/latest/getting_started.html")
        raise SystemExit(f"CRITICAL! No valid MAC address provided {mac}")
    else:
        logging.info(f"Host MAC given as {mac}")

    if argumentDict['noServeHttps']:
        logging.info("HTTPS Port Disabled")

    return argumentDict
