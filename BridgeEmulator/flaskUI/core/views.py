from flask import render_template, request, Blueprint, redirect, url_for, make_response, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.wrappers.response import Response
from flaskUI.core.forms import LoginForm
import flask_login
import uuid
import json
import configManager
from HueObjects import ApiUser
from flaskUI.core import User
from lights.light_types import lightTypes
from subprocess import check_output
from pprint import pprint
import os
import logManager
import subprocess
from typing import Any, Union
from HueObjects import Light

logging = logManager.logger.get_logger(__name__)
bridgeConfig = configManager.bridgeConfig.yaml_config
core = Blueprint('core', __name__)

@core.route('/')
@flask_login.login_required
def index() -> str:
    """
    Render the index page.

    Args:
        None

    Returns:
        str: The rendered index page.
    """
    return render_template('index.html', groups=bridgeConfig["groups"], lights=bridgeConfig["lights"])

@core.route('/get-key')
def get_key() -> str:
    """
    Get the API key for the web interface.

    Args:
        None

    Returns:
        str: The API key.
    """
    if not bridgeConfig["apiUsers"]:
        username = str(uuid.uuid1()).replace('-', '')
        bridgeConfig["apiUsers"][username] = ApiUser.ApiUser(username, 'WebUi', '')
        configManager.bridgeConfig.save_config()
    return list(bridgeConfig["apiUsers"])[0]

@core.route('/lights')
def get_lights() -> dict[str, Any]:
    """
    Get the lights configuration.

    Args:
        None

    Returns:
        dict[str, Any]: The lights configuration.
    """
    return {light: obj.save() for light, obj in bridgeConfig["lights"].items()}

@core.route('/sensors')
def get_sensors() -> dict[str, Any]:
    """
    Get the sensors configuration.

    Args:
        None

    Returns:
        dict[str, Any]: The sensors configuration.
    """
    return {sensor: obj.save() for sensor, obj in bridgeConfig["sensors"].items()}

@core.route('/light-types', methods=['GET', 'POST'])
def get_light_types() -> Union[dict[str, Any], str]:
    """
    Get or update the light types.

    Args:
        None

    Returns:
        Union[dict[str, Any], str]: The light types or a success message.
    """
    if request.method == 'GET':
        return {"result": list(lightTypes.keys())}
    else:
        data = request.get_json(force=True)
        lightId, modelId = list(data.items())[0]
        light: Light.Light = bridgeConfig["lights"][lightId]
        light.modelid = modelId
        light.state = lightTypes[modelId]["state"]
        light.config = lightTypes[modelId]["config"]
        if modelId in ["LCX002", "915005987201", "LCX004", "LCX006"]:
            light.protocol_cfg["points_capable"] = 5
        return "success"

@core.route('/tradfri', methods=['POST'])
def pairTradfri() -> dict[str, Any]:
    """
    Pair with a Tradfri gateway.

    Args:
        None

    Returns:
        dict[str, Any]: The result of the pairing process.
    """
    try:
        data = request.get_json(force=True)
        pprint(data)
        cmd = [
            "coap-client-gnutls", "-m", "post", "-u", "Client_identity", "-k", data["tradfriCode"],
            "-e", "{\"9090\":\"" + data["identity"] + "\"}", "coaps://" + data["tradfriGwIp"] + ":5684/15011/9063"
        ]
        registration = json.loads(check_output(cmd).decode('utf-8').rstrip('\n').split("\n")[-1])
        if "9091" in registration:
            bridgeConfig["config"]["tradfri"] = {
                "psk": registration["9091"],
                "tradfriGwIp": data["tradfriGwIp"],
                "identity": data["identity"]
            }
            return {"result": "success", "psk": registration["9091"]}
        return {"result": registration}
    except Exception as e:
        return {"result": str(e)}

@core.route('/save')
def save_config() -> str:
    """
    Save the bridge configuration.

    Args:
        None

    Returns:
        str: A message indicating whether the configuration was saved or backed up.
    """
    backup = request.args.get('backup', type=str) == "True"
    configManager.bridgeConfig.save_config(backup=backup)
    return "backup config\n" if backup else "config saved\n"

@core.route('/reset_config')
@flask_login.login_required
def reset_config() -> str:
    """
    Reset the bridge configuration.

    Args:
        None

    Returns:
        str: A message indicating that the configuration was reset.
    """
    configManager.bridgeConfig.reset_config()
    return "config reset\n"

@core.route('/remove_cert')
@flask_login.login_required
def remove_cert() -> str:
    """
    Remove the certificate and restart the Python process.

    Args:
        None

    Returns:
        str: A message indicating that the certificate was removed and the process was restarted.
    """
    configManager.bridgeConfig.remove_cert()
    configManager.bridgeConfig.restart_python()
    return "Certificate removed, restart python with args"

@core.route('/restore_config')
@flask_login.login_required
def restore_config() -> str:
    """
    Restore the bridge configuration from a backup.

    Args:
        None

    Returns:
        str: A message indicating that the configuration was restored.
    """
    configManager.bridgeConfig.restore_backup()
    return "restore config\n"

@core.route('/download_config')
@flask_login.login_required
def download_config() -> Response:
    """
    Download the bridge configuration.

    Args:
        None

    Returns:
        Response: The bridge configuration file.
    """
    path = configManager.bridgeConfig.download_config()
    return send_file(path, as_attachment=True)

@core.route('/download_log')
def download_log() -> Response:
    """
    Download the log file.

    Args:
        None

    Returns:
        Response: The log file.
    """
    path = configManager.bridgeConfig.download_log()
    return send_file(path, as_attachment=True)

@core.route('/download_debug')
def download_debug() -> Response:
    """
    Download the debug file.

    Args:
        None

    Returns:
        Response: The debug file.
    """
    path = configManager.bridgeConfig.download_debug()
    return send_file(path, as_attachment=True)

@core.route('/restart')
def restart() -> str:
    """
    Restart the Python process.

    Args:
        None

    Returns:
        str: A message indicating that the process was restarted.
    """
    configManager.bridgeConfig.restart_python()
    return "restart python with args"

@core.route('/info')
def info() -> dict[str, str]:
    """
    Get system information.

    Args:
        None

    Returns:
        dict[str, str]: The system information.
    """
    uname = os.uname()
    return {
        "sysname": uname.sysname,
        "machine": uname.machine,
        "os_version": uname.version,
        "os_release": uname.release,
        "diyhue": subprocess.run("stat -c %y HueEmulator3.py", shell=True, capture_output=True, text=True).stdout.strip(),
        "webui": subprocess.run("stat -c %y flaskUI/templates/index.html", shell=True, capture_output=True, text=True).stdout.strip()
    }

@core.route('/login', methods=['GET', 'POST'])
def login() -> Union[str, Response]:
    """
    Handle user login.

    Args:
        None

    Returns:
        Union[str, Response]: The login page or a redirect to the index page.
    """
    form = LoginForm()
    if request.method == 'GET':
        return render_template('login.html', form=form)
    email = form.email.data
    password = form.password.data
    if email not in bridgeConfig["config"]["users"]:
        return 'User don\'t exist\n'
    if password is not None and check_password_hash(bridgeConfig["config"]["users"][email]['password'], password):
        user = User()
        user.get_id = lambda: email or ""
        flask_login.login_user(user)
        return redirect(url_for('core.index'))

    if password is not None:
        logging.info(f"Hashed pass: {generate_password_hash(password)}")
    return 'Bad login\n'

@core.route('/description.xml')
def description_xml() -> Response:
    """
    Serve the description XML file.

    Args:
        None

    Returns:
        Response: The description XML file.
    """
    HOST_HTTP_PORT = configManager.runtimeConfig.arg["HTTP_PORT"]
    mac = configManager.runtimeConfig.arg["MAC"]
    resp = make_response(render_template('description.xml', mimetype='text/xml', port=HOST_HTTP_PORT, name=bridgeConfig["config"]["name"], ipaddress=bridgeConfig["config"]["ipaddress"], serial=mac))
    resp.headers['Content-type'] = 'text/xml'
    return resp

@core.route('/logout')
@flask_login.login_required
def logout() -> Response:
    """
    Handle user logout.

    Args:
        None

    Returns:
        Response: A redirect to the login page.
    """
    flask_login.logout_user()
    return redirect(url_for('core.login'))
