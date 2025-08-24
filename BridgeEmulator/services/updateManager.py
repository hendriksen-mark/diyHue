import requests
import subprocess
from datetime import datetime, timezone
import os
from pathlib import Path

import configManager
import logManager
from .github_installer import install_github_updates

bridgeConfig = configManager.bridgeConfig.yaml_config
logging = logManager.logger.get_logger(__name__)

def versionCheck() -> None:
    """
    Check for firmware updates from Philips and update the bridge configuration if a new version is available.
    """
    swversion = bridgeConfig["config"]["swversion"]
    url = f"https://firmware.meethue.com/v1/checkupdate/?deviceTypeId=BSB002&version={swversion}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        device_data = response.json()
        if device_data["updates"]:
            new_version = str(device_data["updates"][-1]["version"])
            new_versionName = str(device_data["updates"][-1]["versionName"][:4] + ".0")
            if new_version > swversion:
                logging.info(f"swversion number update from Philips, old: {swversion} new: {new_version}")
                bridgeConfig["config"]["swversion"] = new_version
                bridgeConfig["config"]["apiversion"] = new_versionName
                update_swupdate2_timestamps()
            else:
                logging.info("swversion higher than Philips")
        else:
            logging.info("no swversion number update from Philips")
    except requests.RequestException as e:
        logging.error(f"No connection to Philips: {e}")

def githubCheck() -> None:
    """
    Check for updates on GitHub for both the main diyHue repository and the UI repository.
    Update the bridge configuration based on the availability of updates.
    """
    branch = bridgeConfig['config']['branch']
    creation_time = get_file_creation_time("HueEmulator3.py")
    # publish_time = get_github_publish_time("https://api.github.com/repos/diyhue/diyhue/branches/master")
    publish_time = get_github_publish_time(f"https://api.github.com/repos/hendriksen-mark/diyhue/branches/{branch}")

    logging.debug(f"creation_time diyHue : {creation_time}")
    logging.debug(f"publish_time  diyHue : {publish_time}")

    if publish_time > creation_time:
        logging.info("update on github")
        bridgeConfig["config"]["swupdate2"]["state"] = "allreadytoinstall"
    elif githubUICheck():
        logging.info("UI update on github")
        bridgeConfig["config"]["swupdate2"]["state"] = "anyreadytoinstall"
    else:
        logging.info("no update for diyHue or UI on github")
        bridgeConfig["config"]["swupdate2"]["state"] = "noupdates"
        bridgeConfig["config"]["swupdate2"]["bridge"]["state"] = "noupdates"

    bridgeConfig["config"]["swupdate2"]["checkforupdate"] = False

def githubUICheck() -> bool:
    """
    Check for updates on the GitHub UI repository.
    
    Returns:
        bool: True if there is a new update available, False otherwise.
    """
    creation_time = get_file_creation_time("flaskUI/templates/index.html")
    # publish_time = get_github_publish_time("https://api.github.com/repos/diyhue/diyHueUI/releases/latest")
    publish_time = get_github_publish_time("https://api.github.com/repos/hendriksen-mark/diyHueUI/releases/latest")

    logging.debug(f"creation_time UI : {creation_time}")
    logging.debug(f"publish_time  UI : {publish_time}")

    return publish_time > creation_time

def get_file_creation_time(filepath: str) -> str:
    """
    Get the creation time of a file.
    
    Args:
        filepath (str): The path to the file.
    
    Returns:
        str: The creation time of the file in the format "%Y-%m-%d %H".
    """
    try:
        uname = os.uname()
        running_dir = Path(configManager.bridgeConfig.runningDir)
        # Use consistent time format for both Linux and macOS
        if uname.sysname == "Linux":
            stat_cmd = f"stat -c %y {running_dir}/{filepath}"
        else:  # macOS and other Unix systems
            stat_cmd = f'stat -f "%Sm" -t "%Y-%m-%d %H:%M:%S" {running_dir}/{filepath}'

        creation_time = subprocess.run(stat_cmd, shell=True, capture_output=True, text=True)
        if creation_time.returncode != 0:
            logging.error(f"Error getting file creation time for {running_dir}/{filepath}: {creation_time.stderr}")
            logging.error(f"stat output for {running_dir}/{filepath}: {creation_time.stdout}")
            return "2999-01-01 01:01:01"

        if creation_time.stdout:
            return parse_creation_time(creation_time.stdout.strip())
        else:
            logging.error(f"No output from stat command for {running_dir}/{filepath}")
            return "2999-01-01 01:01:01"
    except subprocess.SubprocessError as e:
        logging.error(f"Error getting file creation time: {e}")
        return "2999-01-01 01:01:01"

def get_github_publish_time(url: str) -> str:
    """
    Get the publish time of the latest commit or release from a GitHub repository.
    
    Args:
        url (str): The API URL to fetch the publish time from.
    
    Returns:
        str: The publish time in the format "%Y-%m-%d %H".
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        device_data = response.json()
        if "commit" in device_data:
            return datetime.strptime(device_data["commit"]["commit"]["author"]["date"], "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d %H")
        elif "published_at" in device_data:
            return datetime.strptime(device_data["published_at"], "%Y-%m-%dT%H:%M:%SZ").strftime("%Y-%m-%d %H")
    except requests.RequestException as e:
        logging.error(f"No connection to GitHub: {e}")
        return "1970-01-01 00:00:00"

def parse_creation_time(creation_time_str: str) -> str:
    """
    Parse the creation time from the output of the stat command.
    
    Args:
        creation_time_str (str): The string representing the creation time in format "YYYY-MM-DD HH:MM:SS"
    
    Returns:
        str: The parsed creation time in the format "%Y-%m-%d %H".
    """
    try:
        time_parts = creation_time_str.split()
        if len(time_parts) >= 2:
            date_part = time_parts[0]
            time_part = time_parts[1]
            if '.' in time_part:
                time_part = time_part.split('.')[0]

            date_time = f"{date_part} {time_part}"

            if len(time_parts) > 2:
                timezone_str = time_parts[2] if time_parts[2].startswith(('+', '-')) else None
                if timezone_str:
                    date_time += f" {timezone_str}"
                    return datetime.strptime(date_time, "%Y-%m-%d %H:%M:%S %z").astimezone(timezone.utc).strftime("%Y-%m-%d %H")
            return datetime.strptime(date_time, "%Y-%m-%d %H:%M:%S").astimezone(timezone.utc).strftime("%Y-%m-%d %H")
        else:
            return "2999-01-01 01:01:01"
    except ValueError as e:
        logging.error(f"Error parsing creation time: {e}, input: {creation_time_str}")
        return "2999-01-01 01:01:01"

def update_swupdate2_timestamps() -> None:
    """
    Update the timestamps for the last change and last install in the bridge configuration.
    """
    current_time = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    bridgeConfig["config"]["swupdate2"]["lastchange"] = current_time
    bridgeConfig["config"]["swupdate2"]["bridge"]["lastinstall"] = current_time

def githubInstall() -> None:
    """
    Install updates from GitHub if they are ready to be installed.
    """
    if bridgeConfig["config"]["swupdate2"]["state"] in ["allreadytoinstall", "anyreadytoinstall"]:
        configManager.bridgeConfig.save_config()
        state = bridgeConfig['config']['swupdate2']['state']
        branch = bridgeConfig['config']['branch']
        try:
            success = install_github_updates(state, branch)
            if success:
                logging.info("Update installation successful, restarting server")
                bridgeConfig["config"]["swupdate2"]["state"] = "noupdates"
                bridgeConfig["config"]["swupdate2"]["install"] = False
                configManager.bridgeConfig.restart_python()
                # Code after restart_python() will not execute
            else:
                logging.error("Update installation failed")
                bridgeConfig["config"]["swupdate2"]["state"] = "unknown"
        except Exception as e:
            logging.error(f"Error during update installation: {e}")
            bridgeConfig["config"]["swupdate2"]["state"] = "unknown"

def startupCheck() -> None:
    """
    Perform a startup check for updates.
    """
    if bridgeConfig["config"]["swupdate2"]["install"]:
        bridgeConfig["config"]["swupdate2"]["install"] = False
        update_swupdate2_timestamps()
    versionCheck()
    githubCheck()
