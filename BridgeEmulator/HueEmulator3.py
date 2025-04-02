#!/usr/bin/env python
from flask import Flask
from flask_cors import CORS
from flask_restful import Api
from werkzeug.security import check_password_hash
from threading import Thread
import ssl
import os
from hypercorn.asyncio import serve
from hypercorn.config import Config as HyperConfig
import asyncio

import configManager
import logManager
import flask_login
from flaskUI.core import User  # dummy import for flask_login module
from flaskUI.restful import (
    NewUser, ShortConfig, EntireConfig, ResourceElements, Element, 
    ElementParam, ElementParamId
)
from flaskUI.v2restapi import AuthV1, ClipV2, ClipV2Resource, ClipV2ResourceId
from flaskUI.espDevices import Switch
from flaskUI.Credits import Credits
from functions.daylightSensor import daylightSensor

# Initialize configurations and logging
bridgeConfig = configManager.bridgeConfig.yaml_config
logging = logManager.logger.get_logger(__name__)
hypercorn_logger = logManager.logger.get_logger('hypercorn')

# Initialize Flask app and API
app = Flask(__name__, template_folder='flaskUI/templates', static_url_path="/assets", static_folder='flaskUI/assets')
api = Api(app)
cors = CORS(app, resources={r"*": {"origins": "*"}})
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', os.urandom(24))  # Load from environment variable or generate a random key
api.app.config['RESTFUL_JSON'] = {'ensure_ascii': False}

# Initialize Flask-Login
login_manager = flask_login.LoginManager()
# We can now pass in our app to the login manager
login_manager.init_app(app)
# Tell users what view to go to when they need to login.
login_manager.login_view = "core.login"

@login_manager.user_loader
def user_loader(email):
    if email not in bridgeConfig["config"]["users"]:
        return None  # Explicitly return None

    user = User()
    user.id = email
    return user

@login_manager.request_loader
def request_loader(request):
    email = request.form.get('email')
    if email not in bridgeConfig["config"]["users"]:
        return None  # Explicitly return None

    user = User()
    user.id = email

    # DO NOT ever store passwords in plaintext and always compare password
    # hashes using constant-time comparison!
    # print(email)  # Remove print statement
    logging.info(f"Authentication attempt for user: {email}")
    user.is_authenticated = compare_passwords(request.form['password'], bridgeConfig["config"]["users"][email]["password"])
    return user

def compare_passwords(input_password, stored_password):
    # Implement a secure password comparison (e.g., using bcrypt)
    return check_password_hash(stored_password, input_password)

### Licence/credits
api.add_resource(Credits, '/licenses/<string:resource>', strict_slashes=False)
### ESP devices
api.add_resource(Switch, '/switch')
### HUE API
api.add_resource(NewUser, '/api/', strict_slashes=False)
api.add_resource(ShortConfig, '/api/config', strict_slashes=False)
api.add_resource(EntireConfig, '/api/<string:username>', strict_slashes=False)
api.add_resource(ResourceElements, '/api/<string:username>/<string:resource>', strict_slashes=False)
api.add_resource(Element, '/api/<string:username>/<string:resource>/<string:resourceid>', strict_slashes=False)
api.add_resource(ElementParam, '/api/<string:username>/<string:resource>/<string:resourceid>/<string:param>/', strict_slashes=False)
api.add_resource(ElementParamId, '/api/<string:username>/<string:resource>/<string:resourceid>/<string:param>/<string:paramid>/', strict_slashes=False)

### V2 API
api.add_resource(AuthV1, '/auth/v1', strict_slashes=False)
#api.add_resource(EventStream, '/eventstream/clip/v2', strict_slashes=False)
api.add_resource(ClipV2, '/clip/v2/resource', strict_slashes=False)
api.add_resource(ClipV2Resource, '/clip/v2/resource/<string:resource>', strict_slashes=False)
api.add_resource(ClipV2ResourceId, '/clip/v2/resource/<string:resource>/<string:resourceid>', strict_slashes=False)

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

def runHttp(BIND_IP, HOST_HTTP_PORT, HOST_HTTPS_PORT, DISABLE_HTTPS, CONFIG_PATH):
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
    
    while True:
        try:
            logging.info("Starting HTTP/HTTPS server")
            asyncio.run(asyncio.wait_for(serve(app, config), timeout=60))  # Add timeout to prevent indefinite hang
        except asyncio.TimeoutError:
            logging.warning("HTTP/HTTPS server timed out, restarting...")
        except ssl.SSLError as ssl_error:
            if ssl_error.reason == 'APPLICATION_DATA_AFTER_CLOSE_NOTIFY':
                logging.warning(f"SSL error occurred: {ssl_error} - Ignoring and continuing")
            else:
                logging.error(f"SSL error occurred: {ssl_error}")
        except ConnectionResetError as conn_error:
            logging.error(f"Connection reset error occurred: {conn_error}")
        except OSError as os_error:
            if os_error.winerror == 121:
                logging.warning(f"OSError occurred: {os_error} - Ignoring and continuing")
            else:
                logging.error(f"OSError occurred: {os_error}")
        except Exception as e:
            logging.error(f"Unexpected error occurred: {e}")
        finally:
            logging.info("HTTP/HTTPS server has stopped")

def main():
    from services import mqtt, deconz, ssdp, mdns, scheduler, remoteApi, remoteDiscover, entertainment, stateFetch, eventStreamer, homeAssistantWS, updateManager
    ### variables initialization
    BIND_IP = configManager.runtimeConfig.arg["BIND_IP"]
    HOST_IP = configManager.runtimeConfig.arg["HOST_IP"]
    mac = configManager.runtimeConfig.arg["MAC"]
    HOST_HTTP_PORT = configManager.runtimeConfig.arg["HTTP_PORT"]
    HOST_HTTPS_PORT = configManager.runtimeConfig.arg["HTTPS_PORT"]
    CONFIG_PATH = configManager.runtimeConfig.arg["CONFIG_PATH"]
    DISABLE_HTTPS = configManager.runtimeConfig.arg["noServeHttps"]
    check_cert(CONFIG_PATH)
    updateManager.startupCheck()

    logging.info("Starting daylight sensor thread")
    Thread(target=daylightSensor, args=[bridgeConfig["config"]["timezone"], bridgeConfig["sensors"]["1"]]).start()
    ### start services
    if bridgeConfig["config"]["deconz"]["enabled"]:
        logging.info("Starting deCONZ websocket client thread")
        Thread(target=deconz.websocketClient).start()
    if bridgeConfig["config"]["mqtt"]["enabled"]:
        logging.info("Starting MQTT server thread")
        Thread(target=mqtt.mqttServer).start()
    if bridgeConfig["config"]["homeassistant"]["enabled"]:
        logging.info("Starting Home Assistant WebSocket client")
        homeAssistantWS.create_ws_client(bridgeConfig)
    if not ("discovery" in bridgeConfig["config"] and bridgeConfig["config"]["discovery"] == False):
        logging.info("Starting remote discovery thread")
        Thread(target=remoteDiscover.runRemoteDiscover, args=[bridgeConfig["config"]]).start()
    logging.info("Starting remote API thread")
    Thread(target=remoteApi.runRemoteApi, args=[BIND_IP, bridgeConfig["config"]]).start()
    logging.info("Starting state fetch thread")
    Thread(target=stateFetch.syncWithLights, args=[False]).start()
    logging.info("Starting SSDP search thread")
    Thread(target=ssdp.ssdpSearch, args=[HOST_IP, HOST_HTTP_PORT, mac]).start()
    logging.info("Starting SSDP broadcast thread")
    Thread(target=ssdp.ssdpBroadcast, args=[HOST_IP, HOST_HTTP_PORT, mac]).start()
    logging.info("Starting mDNS listener thread")
    Thread(target=mdns.mdnsListener, args=[HOST_IP, HOST_HTTP_PORT, "BSB002", bridgeConfig["config"]["bridgeid"]]).start()
    logging.info("Starting scheduler thread")
    Thread(target=scheduler.runScheduler).start()
    logging.info("Starting event streamer thread")
    Thread(target=eventStreamer.messageBroker).start()

    logging.info("Starting HTTP/HTTPS server")
    runHttp(BIND_IP, HOST_HTTP_PORT, HOST_HTTPS_PORT, DISABLE_HTTPS, CONFIG_PATH)
    logging.info("HTTP/HTTPS server thread started")

if __name__ == '__main__':
    main()
