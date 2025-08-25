from configManager import configInit
from configManager.argumentHandler import generate_certificate
import os
import subprocess
import logManager
import yaml
import uuid
import weakref
from copy import deepcopy
from HueObjects import Light, Group, EntertainmentConfiguration, Scene, ApiUser, Rule, ResourceLink, Schedule, Sensor, BehaviorInstance, SmartScene
from typing import Any, Optional, cast
import glob
import re
import sys

try:
    from time import tzset
except ImportError:
    tzset = None

logging = logManager.logger.get_logger(__name__)

class NoAliasDumper(yaml.SafeDumper):
    def ignore_aliases(self, data: Any) -> bool:
        return True

def _open_yaml(path: str) -> Any:
    """
    Open a YAML file and return its contents.

    Args:
        path (str): The path to the YAML file.

    Returns:
        Any: The contents of the YAML file.
    """
    with open(path, 'r', encoding="utf-8") as fp:
        return yaml.load(fp, Loader=yaml.FullLoader)

def _write_yaml(path: str, contents: Any) -> None:
    """
    Write contents to a YAML file.

    Args:
        path (str): The path to the YAML file.
        contents (Any): The contents to write to the YAML file.
    """
    with open(path, 'w', encoding="utf-8") as fp:
        yaml.dump(contents, fp, Dumper=NoAliasDumper, allow_unicode=True, sort_keys=False)

class Config:
    yaml_config: Optional[dict[str, Any]] = None
    argsDict: dict[str, Any] = {}
    configDir: str = ""
    runningDir: str = ""

    def __init__(self) -> None:
        """
        Initialize the Config class.
        """
        pass

    def ensure_config_dir(self) -> None:
        """
        Ensure the config directory exists.
        """
        if self.configDir and not os.path.exists(self.configDir):
            os.makedirs(self.configDir)

    def _set_default_config_values(self, config: dict[str, Any]) -> None:
        """
        Set default configuration values.

        Args:
            config (dict[str, Any]): The configuration dictionary.
        """
        defaults = {
            "Remote API enabled": False,
            "Hue Essentials key": str(uuid.uuid1()).replace('-', ''),
            "discovery": True,
            "IP_RANGE": {
                "IP_RANGE_START": 0,
                "IP_RANGE_END": 255,
                "SUB_IP_RANGE_START": int(self.argsDict["HOST_IP"].split('.')[2]),
                "SUB_IP_RANGE_END": int(self.argsDict["HOST_IP"].split('.')[2])
            },
            "scanonhostip": False,
            "factorynew": True,
            "mqtt":{"enabled":False},
            "deconz":{"enabled":False},
            "alarm":{"enabled": False,"lasttriggered": 0},
            "port":{"enabled": False,"ports": [80]},
            "apiUsers":{},
            "apiversion":"1.67.0",
            "name":"DiyHue Bridge",
            "netmask":"255.255.255.0",
            "swversion":"1967054020",
            "timezone": "Europe/London",
            "linkbutton":{"lastlinkbuttonpushed": 1599398980},
            "users":{"admin@diyhue.org":{"password":"pbkdf2:sha256:150000$bqqXSOkI$199acdaf81c18f6ff2f29296872356f4eb78827784ce4b3f3b6262589c788742"}},
            "hue": {},
            "tradfri": {},
            "homeassistant": {"enabled": False},
            "govee": {"enabled": False},
            "yeelight": {"enabled": True},
            "native_multi": {"enabled": True},
            "tasmota": {"enabled": True},
            "wled": {"enabled": True},
            "shelly": {"enabled": True},
            "esphome": {"enabled": True},
            "hyperion": {"enabled": True},
            "tpkasa": {"enabled": True},
            "elgato": {"enabled": True},
            "zigbee_device_discovery_info": {"status": "ready"},
            "swupdate2": {
                "autoinstall": {"on": False, "updatetime": "T14:00:00"},
                "bridge": {"lastinstall": "2020-12-11T17:08:55", "state": "noupdates"},
                "checkforupdate": False,
                "lastchange": "2020-12-13T10:30:15",
                "state": "noupdates",
                "install": False
            },
            "branch": "main",
            "entertainment_fps": 60
        }
        for key, value in defaults.items():
            if key not in config:
                config[key] = value
        return config

    def _upgrade_config(self, config: dict[str, Any]) -> None:
        """
        Upgrade the configuration if necessary.

        Args:
            config (dict[str, Any]): The configuration dictionary.
        """
        if "configDir" in config:
            del config["configDir"]
        if "runningDir" in config:
            del config["runningDir"]
        if int(config["swversion"]) < 1958077010:
            config["swversion"] = "1967054020"
        if float(config["apiversion"][:3]) < 1.56:
            config["apiversion"] = "1.67.0"
        if "linkbutton" not in config or type(config["linkbutton"]) == bool or "lastlinkbuttonpushed" not in config["linkbutton"]:
            config["linkbutton"] = {"lastlinkbuttonpushed": 1599398980}
        return config

    def _load_yaml_file(self, filename: str, default: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        """
        Load a YAML file and return its contents.

        Args:
            filename (str): The name of the YAML file.
            default (Optional[dict[str, Any]]): The default value if the file does not exist.

        Returns:
            Optional[dict[str, Any]]: The contents of the YAML file or the default value.
        """
        path = os.path.join(self.configDir, filename)
        if os.path.exists(path):
            return _open_yaml(path)
        return default

    def _load_lights(self) -> None:
        """
        Load lights from the YAML configuration.
        """
        lights = self._load_yaml_file("lights.yaml", {})
        for light, data in lights.items():
            data["id_v1"] = light
            self.yaml_config["lights"][light] = Light.Light(data)

    def _load_groups(self) -> None:
        """
        Load groups from the YAML configuration.
        """
        #create group 0
        self.yaml_config["groups"]["0"] = Group.Group({"name":"Group 0","id_v1": "0","type":"LightGroup","state":{"all_on":False,"any_on":True},"recycle":False,"action":{"on":False,"bri":165,"hue":8418,"sat":140,"effect":"none","xy":[0.6635,0.2825],"ct":366,"alert":"select","colormode":"hs"}})
        for key, light in self.yaml_config["lights"].items():
            group_0: Group.Group = self.yaml_config["groups"]["0"]
            group_0.add_light(light)
        # create groups
        groups = self._load_yaml_file("groups.yaml", {})
        for group, data in groups.items():
            data["id_v1"] = group
            if data["type"] == "Entertainment":
                self.yaml_config["groups"][group] = EntertainmentConfiguration.EntertainmentConfiguration(data)
                e_group: EntertainmentConfiguration.EntertainmentConfiguration = self.yaml_config["groups"][group]
                for light in data["lights"]:
                    e_group.add_light(self.yaml_config["lights"][light])
                if "locations" in data:
                    for light, location in data["locations"].items():
                        lightObj = self.yaml_config["lights"][light]
                        e_group.locations[lightObj] = location
            else:
                if "owner" in data and isinstance(data["owner"], dict):
                    data["owner"] = self.yaml_config["apiUsers"][list(self.yaml_config["apiUsers"])[0]]
                elif "owner" not in data:
                    data["owner"] = self.yaml_config["apiUsers"][list(self.yaml_config["apiUsers"])[0]]
                else:
                    data["owner"] = self.yaml_config["apiUsers"][data["owner"]]
                self.yaml_config["groups"][group] = Group.Group(data)
                group_obj: Group.Group = self.yaml_config["groups"][group]
                for light in data["lights"]:
                    group_obj.add_light(self.yaml_config["lights"][light])

    def _load_scenes(self) -> None:
        """
        Load scenes from the YAML configuration.
        """
        scenes = self._load_yaml_file("scenes.yaml", {})
        for scene, data in scenes.items():
            data["id_v1"] = scene
            if data["type"] == "GroupScene":
                group_ref = weakref.ref(self.yaml_config["groups"][data["group"]])
                group = cast(Group.Group, group_ref())
                if group is not None:
                    data["lights"] = group.lights
                    data["group"] = group_ref
            else:
                data["lights"] = [weakref.ref(self.yaml_config["lights"][light]) for light in data["lights"]]
            data["owner"] = self.yaml_config["apiUsers"][data["owner"]]
            self.yaml_config["scenes"][scene] = Scene.Scene(data)
            scene_obj: Scene.Scene = self.yaml_config["scenes"][scene]
            for light, lightstate in data["lightstates"].items():
                lightObj = self.yaml_config["lights"][light]
                scene_obj.lightstates[lightObj] = lightstate

    def _load_smart_scenes(self) -> None:
        """
        Load smart scenes from the YAML configuration.
        """
        smart_scenes = self._load_yaml_file("smart_scene.yaml", {})
        for scene, data in smart_scenes.items():
            data["id_v1"] = scene
            self.yaml_config["smart_scene"][scene] = SmartScene.SmartScene(data)

    def _load_rules(self) -> None:
        """
        Load rules from the YAML configuration.
        """
        rules = self._load_yaml_file("rules.yaml", {})
        for rule, data in rules.items():
            data["id_v1"] = rule
            data["owner"] = self.yaml_config["apiUsers"][data["owner"]]
            self.yaml_config["rules"][rule] = Rule.Rule(data)

    def _load_schedules(self) -> None:
        """
        Load schedules from the YAML configuration.
        """
        schedules = self._load_yaml_file("schedules.yaml", {})
        for schedule, data in schedules.items():
            data["id_v1"] = schedule
            self.yaml_config["schedules"][schedule] = Schedule.Schedule(data)

    def _load_sensors(self) -> None:
        """
        Load sensors from the YAML configuration.
        """
        sensors = self._load_yaml_file("sensors.yaml", {})
        for sensor, data in sensors.items():
            data["id_v1"] = sensor
            self.yaml_config["sensors"][sensor] = Sensor.Sensor(data)
            self.yaml_config["groups"]["0"].add_sensor(self.yaml_config["sensors"][sensor])
        if not sensors:
            data = {"modelid": "PHDL00", "name": "Daylight", "type": "Daylight", "id_v1": "1"}
            self.yaml_config["sensors"]["1"] = Sensor.Sensor(data)
            self.yaml_config["groups"]["0"].add_sensor(self.yaml_config["sensors"]["1"])

    def _load_resourcelinks(self) -> None:
        """
        Load resource links from the YAML configuration.
        """
        resourcelinks = self._load_yaml_file("resourcelinks.yaml", {})
        for resourcelink, data in resourcelinks.items():
            data["id_v1"] = resourcelink
            data["owner"] = self.yaml_config["apiUsers"][data["owner"]]
            self.yaml_config["resourcelinks"][resourcelink] = ResourceLink.ResourceLink(data)

    def _load_behavior_instances(self) -> None:
        """
        Load behavior instances from the YAML configuration.
        """
        behavior_instances = self._load_yaml_file("behavior_instance.yaml", {})
        for behavior_instance, data in behavior_instances.items():
            self.yaml_config["behavior_instance"][behavior_instance] = BehaviorInstance.BehaviorInstance(data)

    def load_config(self) -> None:
        """
        Load the entire configuration from YAML files.
        """
        self.yaml_config = {
            "apiUsers": {}, "lights": {}, "groups": {}, "scenes": {}, "config": {}, "rules": {}, "resourcelinks": {}, "schedules": {}, "sensors": {}, "behavior_instance": {}, "geofence_clients": {}, "smart_scene": {}, "temp": {"eventstream": [], "scanResult": {"lastscan": "none"}, "detectedLights": [], "gradientStripLights": {}}
        }
        try:
            config = self._load_yaml_file("config.yaml", {})
            if "timezone" not in config:
                logging.warning("No Time Zone in config, please set Time Zone in webui, default to Europe/London")
                config["timezone"] = "Europe/London"
            os.environ['TZ'] = config["timezone"]
            if tzset is not None:
                tzset()
            if "whitelist" in config:
                for user, data in config["whitelist"].items():

                    self.yaml_config["apiUsers"][user] = ApiUser.ApiUser(user, data["name"], data["client_key"], data["create_date"], data["last_use_date"])
                del config["whitelist"]
            config = self._set_default_config_values(config)
            config = self._upgrade_config(config)
            self.yaml_config["config"] = config

            self._load_lights()
            self._load_groups()
            self._load_scenes()
            self._load_smart_scenes()
            self._load_rules()
            self._load_schedules()
            self._load_sensors()
            self._load_resourcelinks()
            self._load_behavior_instances()

            logging.info("Config loaded")
        except Exception:
            logging.exception("CRITICAL! Config file was not loaded")
            raise SystemExit("CRITICAL! Config file was not loaded")
        bridgeConfig = self.yaml_config

    def save_config(self, backup: bool = False, resource: str = "all") -> None:
        """
        Save the current configuration to YAML files.

        Args:
            backup (bool): Whether to save a backup of the configuration.
            resource (str): The specific resource to save or "all" to save everything.
        """
        path = self.configDir + '/'
        if backup:
            path = self.configDir + '/backup/'
            if not os.path.exists(path):
                os.makedirs(path)
        if resource in ["all", "config"]:
            config = self.yaml_config["config"]
            config["whitelist"] = {}
            for user, obj in self.yaml_config["apiUsers"].items():
                config["whitelist"][user] = obj.save()
            _write_yaml(path + "config.yaml", config)
            logging.debug("Dump config file " + path + "config.yaml")
            if resource == "config":
                return
        saveResources = []
        if resource == "all":
            saveResources = ["lights", "groups", "scenes", "rules", "resourcelinks", "schedules", "sensors", "behavior_instance", "smart_scene"]
        else:
            saveResources.append(resource)
        for object in saveResources:
            filePath = path + object + ".yaml"
            dumpDict = {}
            for element in self.yaml_config[object]:
                if element != "0":
                    savedData = self.yaml_config[object][element].save()
                    if savedData:
                        dumpDict[self.yaml_config[object][element].id_v1] = savedData
            _write_yaml(filePath, dumpDict)
            logging.debug("Dump config file " + filePath)

    def reset_config(self) -> None:
        """
        Reset the configuration to default values.
        """
        self.save_config(backup=True)
        try:
            subprocess.run(f'rm -r {self.configDir}/*.yaml', check=True)
        except subprocess.CalledProcessError:
            logging.exception("Something went wrong when deleting the config")
        self.load_config()

    def remove_cert(self) -> None:
        """
        Remove the current certificate and generate a new one.
        """
        try:
            subprocess.run(f'mv {self.configDir}/cert.pem {self.configDir}/backup/', check=True)
            logging.info("Certificate removed")
        except subprocess.CalledProcessError:
            logging.exception("Something went wrong when deleting the certificate")
        generate_certificate(self.argsDict["MAC"], self.argsDict["CONFIG_PATH"])

    def restore_backup(self) -> None:
        """
        Restore the configuration from a backup.
        """
        try:
            subprocess.run(f'rm -r {self.configDir}/*.yaml', check=True)
        except subprocess.CalledProcessError:
            logging.exception("Something went wrong when deleting the config")
        subprocess.run(f'cp -r {self.configDir}/backup/*.yaml {self.configDir}/', shell=True, check=True)
        self.load_config()

    def download_config(self) -> str:
        """
        Download the current configuration as a tar file.

        Returns:
            str: The path to the tar file containing the configuration.
        """
        self.save_config()
        subprocess.run(f'tar --exclude=\'config_debug.yaml\' -cvf {self.configDir}/config.tar ' + self.configDir + '/*.yaml', shell=True, capture_output=True, text=True)
        return f"{self.configDir}/config.tar"

    def download_log(self) -> str:
        """
        Download the log files as a tar file.

        Returns:
            str: The path to the tar file containing the log files.
        """
        debug_logs_dir = self.create_debug_logs()
        log_path = f"{debug_logs_dir}/*.log*"
        subprocess.run(f'tar -cvf {self.configDir}/diyhue_log.tar {log_path}', shell=True, check=True)
        subprocess.run(f'rm -r {debug_logs_dir}', shell=True, check=True)
        return f"{self.configDir}/diyhue_log.tar"

    def download_debug(self) -> str:
        """
        Download the debug information as a tar file.

        Args:
            include_debug_logs (bool): Whether to include debug logs with API keys replaced by names.

        Returns:
            str: The path to the tar file containing the debug information.
        """
        debug = deepcopy(self.yaml_config["config"])
        debug["whitelist"] = "privately"
        debug["apiUsers"] = [user_obj.name for user_obj in self.yaml_config["apiUsers"].values()]
        debug["Hue Essentials key"] = "privately"
        debug["users"] = "privately"
        if debug["mqtt"]["enabled"] or "mqttPassword" in debug["mqtt"]:
            debug["mqtt"]["mqttPassword"] = "privately"
        if debug["homeassistant"]["enabled"] or "homeAssistantToken" in debug["homeassistant"]:
            debug["homeassistant"]["homeAssistantToken"] = "privately"
        if debug["hue"]:
            debug["hue"]["hueUser"] = "privately"
            debug["hue"]["hueKey"] = "privately"
        if debug["tradfri"]:
            debug["tradfri"]["psk"] = "privately"
        if debug["alarm"]["enabled"] or "email" in debug["alarm"]:
            debug["alarm"]["email"] = "privately"
        if debug["govee"]["enabled"] or "api_key" in debug["govee"]:
            debug["govee"]["api_key"] = "privately"
        info = {}
        info["OS"] = os.uname().sysname
        info["Architecture"] = os.uname().machine
        info["os_version"] = os.uname().version
        info["os_release"] = os.uname().release
        info["Hue-Emulator Version"] = subprocess.run("stat -c %y HueEmulator3.py", shell=True, capture_output=True, text=True).stdout.replace("\n", "")
        info["WebUI Version"] = subprocess.run("stat -c %y flaskUI/templates/index.html", shell=True, capture_output=True, text=True).stdout.replace("\n", "")
        info["arguments"] = {k: str(v) for k, v in self.argsDict.items()}
        _write_yaml(f"{self.configDir}/config_debug.yaml", debug)
        _write_yaml(f"{self.configDir}/system_info.yaml", info)

        debug_logs_dir = self.create_debug_logs()
        log_path = f"{debug_logs_dir}/*.log*"
        
        subprocess.run(f'tar --exclude=\'config.yaml\' -cvf {self.configDir}/config_debug.tar {self.configDir}/*.yaml {log_path} ', shell=True, capture_output=True, text=True)
        subprocess.run(f'rm -r {self.configDir}/config_debug.yaml {debug_logs_dir}', shell=True, capture_output=True, text=True)
        return f"{self.configDir}/config_debug.tar"

    def write_args(self, args: dict[str, Any]) -> None:
        """
        Write arguments to the configuration.

        Args:
            args (dict[str, Any]): The arguments to write.
        """
        self.yaml_config = configInit.write_args(args, self.yaml_config)

    def create_debug_logs(self) -> str:
        """
        Create debug versions of log files with API user keys replaced by names.

        Scans all log files in {self.runningDir}/*.log* for API user keys from 
        self.yaml_config["apiUsers"] and replaces them with the corresponding 
        user names, then creates new debug log files with the suffix '-debug'.

        Returns:
            str: The directory path containing the debug log files.
        """
        debug_dir = os.path.join(self.configDir, 'debug_logs')
        if not os.path.exists(debug_dir):
            os.makedirs(debug_dir)

        # Get all log files
        log_pattern = os.path.join(self.runningDir, '*.log*')
        log_files = glob.glob(log_pattern)

        if not log_files:
            logging.warning(f"No log files found in {self.runningDir}")
            return debug_dir

        # Create mapping of API keys to names
        api_key_map = {}
        for key, user_obj in self.yaml_config["apiUsers"].items():
            api_key_map[key] = user_obj.name

        logging.info(f"Processing {len(log_files)} log files for debug output")

        for log_file in log_files:
            try:
                # Read the original log file
                with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()

                # Replace API keys with names
                modified_content = content
                replacements_made = 0

                for api_key, user_name in api_key_map.items():
                    if api_key in modified_content:
                        # Use word boundaries to avoid partial matches
                        pattern = re.escape(api_key)
                        replacement_count = len(re.findall(pattern, modified_content))
                        modified_content = re.sub(pattern, user_name, modified_content)
                        replacements_made += replacement_count
                        if replacement_count > 0:
                            logging.debug(f"Replaced {replacement_count} occurrences of '{user_name}' in {os.path.basename(log_file)}")

                # Create debug log file name
                base_name = os.path.basename(log_file)
                if '.' in base_name:
                    name_parts = base_name.rsplit('.', 1)
                    debug_name = f"{name_parts[0]}-debug.{name_parts[1]}"
                else:
                    debug_name = f"{base_name}-debug"

                debug_file_path = os.path.join(debug_dir, debug_name)

                # Write the debug log file
                with open(debug_file_path, 'w', encoding='utf-8') as f:
                    f.write(modified_content)

                logging.info(f"Created debug log: {debug_name} ({replacements_made} API key replacements)")

            except Exception as e:
                logging.error(f"Error processing log file {log_file}: {str(e)}")

        return debug_dir

    def is_docker_environment(self) -> bool:
        """Check if we're running in a Docker container."""
        try:
            with open('/proc/1/cgroup', 'r') as f:
                return 'docker' in f.read() or 'containerd' in f.read()
        except FileNotFoundError:
            # Check for .dockerenv file as alternative method
            return os.path.exists('/.dockerenv')

    def try_systemctl_restart(self) -> bool:
        """Try to restart using systemctl with appropriate permissions."""
        # Check if we're in Docker first
        if self.is_docker_environment():
            logging.info("Docker environment detected, systemctl not available")
            return False
            
        # In regular environments, try systemctl commands
        commands_to_try = [
            ['systemctl', 'restart', 'hue-emulator.service'],
            ['sudo', 'systemctl', 'restart', 'hue-emulator.service']
        ]

        for cmd in commands_to_try:
            try:
                restart_result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                if restart_result.returncode == 0:
                    logging.info(f"diyHue restarted successfully using: {' '.join(cmd)}")
                    return True
                else:
                    logging.debug(f"Command '{' '.join(cmd)}' failed: {restart_result.stderr}")
            except FileNotFoundError:
                logging.debug(f"Command not found: {cmd[0]}")
                continue
            except subprocess.TimeoutExpired:
                logging.warning(f"Command '{' '.join(cmd)}' timed out")
                continue
            except Exception as e:
                logging.debug(f"Error with command '{' '.join(cmd)}': {e}")
                continue
        return False

    def restart_python(self) -> None:
        """
        Restart the Python process or systemd service.
        """
        import signal
        
        # Check if we're in Docker environment
        if self.is_docker_environment():
            logging.info("Docker environment detected, restarting via os.execl")
            logging.info(f"restart {sys.executable} with args: {sys.argv}")
            os.execl(sys.executable, sys.executable, *sys.argv)
            return
        
        try:
            logging.info("Attempting restart using systemctl")
            if self.try_systemctl_restart():
                return  # Successfully restarted
            else:
                # systemctl restart failed, fall back to os.execl
                logging.info("systemctl restart failed or not available, falling back to os.execl")
                logging.info(f"restart {sys.executable} with args: {sys.argv}")
                os.execl(sys.executable, sys.executable, *sys.argv)
        except subprocess.CalledProcessError as e:
            # If the process was killed by SIGTERM, do nothing (systemd is restarting us)
            if e.returncode == -signal.SIGTERM:
                logging.info("Process terminated by SIGTERM (expected during systemctl restart). Not falling back to os.execl.")
                sys.exit(0)
            logging.error(f"systemctl restart failed: {e}, falling back to os.execl")
            logging.info(f"restart {sys.executable} with args: {sys.argv}")
            os.execl(sys.executable, sys.executable, *sys.argv)
        except Exception as e:
            logging.error(f"systemctl restart failed: {e}, falling back to os.execl")
            logging.info(f"restart {sys.executable} with args: {sys.argv}")
            os.execl(sys.executable, sys.executable, *sys.argv)
