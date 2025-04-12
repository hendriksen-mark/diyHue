from quart import render_template, request, Blueprint, redirect, url_for, make_response, send_file
from werkzeug.security import generate_password_hash,check_password_hash
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
import sys
import logManager
import subprocess
logging = logManager.logger.get_logger(__name__)
bridgeConfig = configManager.bridgeConfig.yaml_config
core = Blueprint('core',__name__)
@core.route('/')
@flask_login.login_required
async def index():
    return await render_template('index.html', groups=bridgeConfig["groups"], lights=bridgeConfig["lights"])

@core.route('/get-key')
#@flask_login.login_required
async def get_key():
    if len(bridgeConfig["apiUsers"]) == 0:
        # generate a new user for the web interface
        username = str(uuid.uuid1()).replace('-', '')
        bridgeConfig["apiUsers"][username] = ApiUser.ApiUser(username, 'WebUi', None)
        configManager.bridgeConfig.save_config()
    return list(bridgeConfig["apiUsers"])[0]

@core.route('/lights')
#@flask_login.login_required
async def get_lights():
    result = {}
    for light, object in bridgeConfig["lights"].items():
        result[light] = object.save()
    return result

@core.route('/sensors')
#@flask_login.login_required
async def get_sensors():
    result = {}
    for sensor, object in bridgeConfig["sensors"].items():
        result[sensor] = object.save()
    return result

@core.route('/light-types', methods=['GET', 'POST'])
#@flask_login.login_required
async def get_light_types():
    if request.method == 'GET':
        result = []
        for modelid in lightTypes.keys():
            result.append(modelid)
        return {"result": result}
    elif request.method == 'POST':
        data = await request.get_json(force=True)
        lightId = list(data)[0]
        modelId = data[lightId]
        bridgeConfig["lights"][lightId].modelid = modelId
        bridgeConfig["lights"][lightId].state = lightTypes[modelId]["state"]
        bridgeConfig["lights"][lightId].config = lightTypes[modelId]["config"]
        if modelId in ["LCX002", "915005987201", "LCX004", "LCX006"]:
            bridgeConfig["lights"][lightId].protocol_cfg["points_capable"] = 5
        return "success"

@core.route('/tradfri', methods=['POST'])
async def pairTradfri():
    try:
        data = await request.get_json(force=True)
        pprint(data)
        cmd = ["coap-client-gnutls", "-m", "post", "-u", "Client_identity", "-k", data["tradfriCode"], "-e", "{\"9090\":\"" + data["identity"] + "\"}", "coaps://" + data["tradfriGwIp"] + ":5684/15011/9063"]
        registration = json.loads(check_output(cmd).decode('utf-8').rstrip('\n').split("\n")[-1])
        if "9091" in registration:
            bridgeConfig["config"]["tradfri"] = {"psk": registration["9091"], "tradfriGwIp": data["tradfriGwIp"], "identity": data["identity"]}
            return {"result": "success", "psk": registration["9091"]}
        return {"result": registration}
    except Exception as e:
        return {"result": str(e)}

@core.route('/save')
async def save_config():
    if request.args.get('backup', type = str) == "True":
        configManager.bridgeConfig.save_config(backup=True)
        return "backup config\n"
    else:
        configManager.bridgeConfig.save_config()
        return "config saved\n"

@core.route('/reset_config')
@flask_login.login_required
async def reset_config():
    configManager.bridgeConfig.reset_config()
    return "config reset\n"

@core.route('/remove_cert')
@flask_login.login_required
async def remove_cert():
    configManager.bridgeConfig.remove_cert()
    logging.info("restart " + str(sys.executable) + " with args : " + str(sys.argv))
    os.execl(sys.executable, sys.executable, *sys.argv)
    return "Certificate removed, restart python with args"

@core.route('/restore_config')
@flask_login.login_required
async def restore_config():
    configManager.bridgeConfig.restore_backup()
    return "restore config\n"

@core.route('/download_config')
@flask_login.login_required
async def download_config():
    path = configManager.bridgeConfig.download_config()
    return await send_file(path, as_attachment=True)

@core.route('/download_log')
#@flask_login.login_required
async def download_log():
    path = configManager.bridgeConfig.download_log()
    return await send_file(path, as_attachment=True)

@core.route('/download_debug')
#@flask_login.login_required
async def download_debug():
    path = configManager.bridgeConfig.download_debug()
    return await send_file(path, as_attachment=True)

@core.route('/restart')
async def restart():
    logging.info("restart " + str(sys.executable) + " with args : " + str(sys.argv))
    os.execl(sys.executable, sys.executable, *sys.argv)
    return "restart python with args"

@core.route('/info')
#@flask_login.login_required
async def info():
    response = {}
    response["sysname"] = os.uname().sysname
    response["machine"] = os.uname().machine
    response["os_version"] = os.uname().version
    response["os_release"] = os.uname().release
    response["diyhue"] = subprocess.run("stat -c %y HueEmulator3.py", shell=True, capture_output=True, text=True).stdout.replace("\n", "")
    response["webui"] = subprocess.run("stat -c %y flaskUI/templates/index.html", shell=True, capture_output=True, text=True).stdout.replace("\n", "")
    return response

@core.route('/login', methods=['GET', 'POST'])
async def login():
    form = LoginForm()
    if request.method == 'GET':
        return await render_template('login.html', form=form)
    form_data = await request.form
    email = form_data['email']
    if email not in bridgeConfig["config"]["users"]:
        return 'User don\'t exist\n'
    if check_password_hash(bridgeConfig["config"]["users"][email]['password'], form_data['password']):
        user = User()
        user.id = email
        flask_login.login_user(user)
        return redirect(url_for('core.index'))
    return 'Bad login\n'

@core.route('/description.xml')
async def description_xml():
    HOST_HTTP_PORT = configManager.runtimeConfig.arg["HTTP_PORT"]
    mac = configManager.runtimeConfig.arg["MAC"]
    resp = make_response(await render_template('description.xml', mimetype='text/xml', port=HOST_HTTP_PORT, name=bridgeConfig["config"]["name"], ipaddress=bridgeConfig["config"]["ipaddress"], serial=mac))
    resp.headers['Content-type'] = 'text/xml'
    return resp

@core.route('/logout')
@flask_login.login_required
async def logout():
    flask_login.logout_user()
    return redirect(url_for('core.login'))
