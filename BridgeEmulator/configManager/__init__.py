from typing import cast
from datetime import datetime, timezone
import os
from configManager import configHandler
from configManager import argumentHandler
from configManager import runtimeConfigHandler

bridgeConfig = configHandler.Config()
runtimeConfig = runtimeConfigHandler.Config()

# Parse arguments once and process them
runtimeConfig.clear_new_lights()
args = argumentHandler.parse_arguments()
runtimeConfig.arg.update(args)

# Set the config directories and args in bridgeConfig
bridgeConfig.argsDict = args
config_path = args["CONFIG_PATH"]
running_path = args["RUNNING_PATH"]

if not isinstance(config_path, str):
	raise TypeError("CONFIG_PATH must be a string")
if not isinstance(running_path, str):
	raise TypeError("RUNNING_PATH must be a string")

bridgeConfig.configDir = config_path
bridgeConfig.runningDir = running_path
serverCreateEpoch = os.stat(f"{bridgeConfig.runningDir}/HueEmulator3.py").st_mtime
bridgeConfig.serverCreateTime = datetime.fromtimestamp(serverCreateEpoch, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
webUICreateEpoch = os.stat(f"{bridgeConfig.runningDir}/flaskUI/templates/index.html").st_mtime
bridgeConfig.WebUICreateTime = datetime.fromtimestamp(webUICreateEpoch, timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

# Ensure config directory exists
bridgeConfig.ensure_config_dir()

process_args = cast(dict[str, str | bool], args)
argumentHandler.process_arguments(bridgeConfig, process_args)

# Restore configuration
bridgeConfig.load_config()

# Initialize bridge config
bridgeConfig.write_args(runtimeConfig.arg)
