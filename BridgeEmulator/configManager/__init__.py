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
bridgeConfig.configDir = args["CONFIG_PATH"]
bridgeConfig.runningDir = args["RUNNING_PATH"]

# Ensure config directory exists
bridgeConfig.ensure_config_dir()

argumentHandler.process_arguments(bridgeConfig, args)

# Restore configuration
bridgeConfig.load_config()

# Initialize bridge config
bridgeConfig.write_args(runtimeConfig.arg)
