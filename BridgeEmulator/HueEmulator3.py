#!/usr/bin/env python
import logManager
logManager.logger.enable_file_logging()
from flask import Flask
from threading import Thread
import ssl
import configManager
from functions.daylightSensor import daylightSensor
from services import LogWS
from flaskUI import create_app

bridgeConfig = configManager.bridgeConfig.yaml_config
logging = logManager.logger.get_logger(__name__)
werkzeug_logger = logManager.logger.get_logger("werkzeug")
cherrypy_logger = logManager.logger.get_logger("cherrypy")

app: Flask = create_app(bridgeConfig)

def runHttps(BIND_IP, HOST_HTTPS_PORT, CONFIG_PATH):
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(certfile=CONFIG_PATH + "/cert.pem")
    ctx.options |= ssl.OP_CIPHER_SERVER_PREFERENCE
    ctx.set_ciphers('ECDHE-ECDSA-AES128-GCM-SHA256')
    ctx.set_ecdh_curve('prime256v1')
    app.run(host=BIND_IP, port=HOST_HTTPS_PORT, ssl_context=ctx)

def runHttp(BIND_IP, HOST_HTTP_PORT):
    app.run(host=BIND_IP, port=HOST_HTTP_PORT)

def main():
    from services import mqtt, deconz, ssdp, mdns, scheduler, remoteApi, remoteDiscover, entertainment, stateFetch, eventStreamer, homeAssistantWS, updateManager
    BIND_IP = configManager.runtimeConfig.arg["BIND_IP"]
    HOST_IP = configManager.runtimeConfig.arg["HOST_IP"]
    mac = configManager.runtimeConfig.arg["MAC"]
    HOST_HTTP_PORT = configManager.runtimeConfig.arg["HTTP_PORT"]
    HOST_HTTPS_PORT = configManager.runtimeConfig.arg["HTTPS_PORT"]
    CONFIG_PATH = configManager.runtimeConfig.arg["CONFIG_PATH"]
    DISABLE_HTTPS = configManager.runtimeConfig.arg["noServeHttps"]
    updateManager.startupCheck()

    Thread(target=daylightSensor, args=[bridgeConfig["config"]["timezone"], bridgeConfig["sensors"]["1"]]).start()
    if bridgeConfig["config"]["deconz"]["enabled"]:
        Thread(target=deconz.websocketClient).start()
    if bridgeConfig["config"]["mqtt"]["enabled"]:
        Thread(target=mqtt.mqttServer).start()
    if bridgeConfig["config"]["homeassistant"]["enabled"]:
        homeAssistantWS.create_ws_client(bridgeConfig)
    if not ("discovery" in bridgeConfig["config"] and bridgeConfig["config"]["discovery"] == False):
        Thread(target=remoteDiscover.runRemoteDiscover).start()
    Thread(target=remoteApi.runRemoteApi).start()
    Thread(target=stateFetch.syncWithLights, args=[False]).start()
    Thread(target=ssdp.ssdpSearch, args=[HOST_IP, HOST_HTTP_PORT, mac, bridgeConfig["config"]["apiversion"]]).start()
    Thread(target=ssdp.ssdpBroadcast, args=[HOST_IP, HOST_HTTP_PORT, mac, bridgeConfig["config"]["apiversion"]]).start()
    Thread(target=mdns.mdnsListener, args=[HOST_IP, HOST_HTTPS_PORT, "BSB002", bridgeConfig["config"]["bridgeid"], mac]).start()
    Thread(target=scheduler.runScheduler).start()
    Thread(target=eventStreamer.messageBroker).start()
    Thread(target=LogWS.start_ws_server).start()
    if not DISABLE_HTTPS:
        Thread(target=runHttps, args=[BIND_IP, HOST_HTTPS_PORT, CONFIG_PATH]).start()
    runHttp(BIND_IP, HOST_HTTP_PORT)

if __name__ == '__main__':
    main()
