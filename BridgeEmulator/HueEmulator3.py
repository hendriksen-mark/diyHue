#!/usr/bin/env python
from quart import Quart, request
from quart_cors import cors
import quart.flask_patch
from threading import Thread
import ssl
import configManager
import logManager
import flask_login
from flaskUI.core import User #dummy import for flaks_login module
from flaskUI.restful import NewUser, ShortConfig, EntireConfig, ResourceElements, Element, ElementParam, ElementParamId
from flaskUI.v2restapi import AuthV1, ClipV2, ClipV2Resource, ClipV2ResourceId
from flaskUI.espDevices import Switch
from flaskUI.Credits import Credits
from werkzeug.serving import WSGIRequestHandler
from functions.daylightSensor import daylightSensor
import hypercorn.asyncio
from hypercorn.config import Config as HyperConfig
import os
import asyncio
from asyncio import get_event_loop

bridgeConfig = configManager.bridgeConfig.yaml_config
logging = logManager.logger.get_logger(__name__)
hypercorn_logger = logManager.logger.get_logger('hypercorn')
app = Quart(__name__, template_folder='flaskUI/templates', static_url_path="/assets", static_folder='flaskUI/assets')
app = cors(app, allow_origin="*")

app.config['SECRET_KEY'] = 'change_this_to_be_secure'

login_manager = flask_login.LoginManager()
# We can now pass in our app to the login manager
login_manager.init_app(app)
# Tell users what view to go to when they need to login.
login_manager.login_view = "core.login"

@login_manager.user_loader
def user_loader(email):
    if email not in bridgeConfig["config"]["users"]:
        return

    user = User()
    user.id = email
    return user

@login_manager.request_loader
def request_loader(request):
    email = request.form.get('email')
    if email not in bridgeConfig["config"]["users"]:
        return

    user = User()
    user.id = email

    # DO NOT ever store passwords in plaintext and always compare password
    # hashes using constant-time comparison!
    print(email)
    user.is_authenticated = request.form['password'] == bridgeConfig["config"]["users"][email]["password"]

    return user

# Replace flask_restful API endpoints with Quart routes
@app.route('/api/', methods=['POST'])
async def new_user():
    return await NewUser().post()

@app.route('/api/config', methods=['GET'])
async def short_config():
    return ShortConfig().get()

@app.route('/api/<string:username>', methods=['GET'])
async def entire_config(username):
    return EntireConfig().get(username)

@app.route('/api/<string:username>/<string:resource>', methods=['GET', 'POST'])
async def resource_elements(username, resource):
    if request.method == 'GET':
        return ResourceElements().get(username, resource)
    elif request.method == 'POST':
        return ResourceElements().post(username, resource)

@app.route('/api/<string:username>/<string:resource>/<string:resourceid>', methods=['GET', 'PUT', 'DELETE'])
async def element(username, resource, resourceid):
    if request.method == 'GET':
        return Element().get(username, resource, resourceid)
    elif request.method == 'PUT':
        return Element().put(username, resource, resourceid)
    elif request.method == 'DELETE':
        return Element().delete(username, resource, resourceid)

@app.route('/api/<string:username>/<string:resource>/<string:resourceid>/<string:param>/', methods=['GET', 'PUT', 'DELETE'])
async def element_param(username, resource, resourceid, param):
    if request.method == 'GET':
        return ElementParam().get(username, resource, resourceid, param)
    elif request.method == 'PUT':
        return ElementParam().put(username, resource, resourceid, param)
    elif request.method == 'DELETE':
        return ElementParam().delete(username, resource, resourceid, param)

@app.route('/api/<string:username>/<string:resource>/<string:resourceid>/<string:param>/<string:paramid>/', methods=['GET', 'PUT'])
async def element_param_id(username, resource, resourceid, param, paramid):
    if request.method == 'GET':
        return ElementParamId().get(username, resource, resourceid, param, paramid)
    elif request.method == 'PUT':
        return ElementParamId().put(username, resource, resourceid, param, paramid)

@app.route('/licenses/<string:resource>', methods=['GET'])
async def credits(resource):
    return await Credits().get(resource)

@app.route('/switch', methods=['GET'])
async def switch():
    return await Switch().get()

### WEB INTERFACE
from flaskUI.core.views import core
from flaskUI.devices.views import devices
from flaskUI.error_pages.handlers import error_pages
from services.eventStreamer import stream

app.register_blueprint(core)
app.register_blueprint(devices)
app.register_blueprint(error_pages)
app.register_blueprint(stream)

def check_cert(CONFIG_PATH):
    private_key_path = os.path.join(CONFIG_PATH, "private.key")
    public_crt_path = os.path.join(CONFIG_PATH, "public.crt")
    cert_pem_path = os.path.join(CONFIG_PATH, "cert.pem")

    if not os.path.exists(private_key_path) and not os.path.exists(public_crt_path) and os.path.exists(cert_pem_path):
        try:
            with open(cert_pem_path, 'r') as file:
                lines = file.readlines()

            private_key_content = ''.join(lines[:lines.index('-----END PRIVATE KEY-----\n') + 1])
            certificate_content = ''.join(lines[lines.index('-----BEGIN CERTIFICATE-----\n'):])

            with open(private_key_path, 'w') as file:
                file.write(private_key_content)
            logging.info(f"Private key written to {private_key_path}")

            with open(public_crt_path, 'w') as file:
                file.write(certificate_content)
            logging.info(f"Public certificate written to {public_crt_path}")

        except Exception as e:
            logging.error(f"Error processing certificate files: {e}")

async def runHttp(BIND_IP, HOST_HTTP_PORT, HOST_HTTPS_PORT, DISABLE_HTTPS, CONFIG_PATH):
    config = HyperConfig()
    config.accesslog = hypercorn_logger
    config.errorlog = hypercorn_logger
    config.loglevel = 'DEBUG'
    config.access_log_format = '%(h)s %(r)s %(s)s'
    config.insecure_bind = [f"{BIND_IP}:{HOST_HTTP_PORT}"]
    config.alpn_protocols = ["h2"]
    if not DISABLE_HTTPS:
        config.bind = [f"{BIND_IP}:{HOST_HTTPS_PORT}"]
        config.certfile = CONFIG_PATH + "/public.crt"
        config.keyfile = CONFIG_PATH + "/private.key"

    await hypercorn.asyncio.serve(app, config)

async def main():
    from services import mqtt, deconz, ssdp, mdns, scheduler, remoteApi, remoteDiscover, entertainment, stateFetch, eventStreamer, homeAssistantWS, updateManager
    ### variables initialization
    BIND_IP = configManager.runtimeConfig.arg["BIND_IP"]
    HOST_IP = configManager.runtimeConfig.arg["HOST_IP"]
    mac = configManager.runtimeConfig.arg["MAC"]
    HOST_HTTP_PORT = configManager.runtimeConfig.arg["HTTP_PORT"]
    HOST_HTTPS_PORT = configManager.runtimeConfig.arg["HTTPS_PORT"]
    CONFIG_PATH = configManager.runtimeConfig.arg["CONFIG_PATH"]
    DISABLE_HTTPS = configManager.runtimeConfig.arg["noServeHttps"]
    updateManager.startupCheck()

    Thread(target=daylightSensor, args=[bridgeConfig["config"]["timezone"], bridgeConfig["sensors"]["1"]]).start()
    ### start services
    if bridgeConfig["config"]["deconz"]["enabled"]:
        Thread(target=deconz.websocketClient).start()
    if bridgeConfig["config"]["mqtt"]["enabled"]:
        Thread(target=mqtt.mqttServer).start()
    if bridgeConfig["config"]["homeassistant"]["enabled"]:
        homeAssistantWS.create_ws_client(bridgeConfig)
    if not ("discovery" in bridgeConfig["config"] and bridgeConfig["config"]["discovery"] == False):
        Thread(target=remoteDiscover.runRemoteDiscover, args=[bridgeConfig["config"]]).start()
    Thread(target=remoteApi.runRemoteApi, args=[BIND_IP, bridgeConfig["config"]]).start()
    Thread(target=stateFetch.syncWithLights, args=[False]).start()
    Thread(target=ssdp.ssdpSearch, args=[HOST_IP, HOST_HTTP_PORT, mac]).start()
    Thread(target=ssdp.ssdpBroadcast, args=[HOST_IP, HOST_HTTP_PORT, mac]).start()
    loop = get_event_loop()
    Thread(target=lambda: asyncio.run_coroutine_threadsafe(
        mdns.mdnsListener(app, HOST_IP, HOST_HTTP_PORT, "BSB002", bridgeConfig["config"]["bridgeid"]), loop)).start()
    Thread(target=scheduler.runScheduler).start()
    Thread(target=eventStreamer.messageBroker).start()
    await runHttp(BIND_IP, HOST_HTTP_PORT, HOST_HTTPS_PORT, DISABLE_HTTPS, CONFIG_PATH)

if __name__ == '__main__':
    asyncio.run(main())
