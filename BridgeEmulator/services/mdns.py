import logManager
import socket
from zeroconf import IPVersion, ServiceInfo, Zeroconf
from quart import current_app

logging = logManager.logger.get_logger(__name__)

async def mdnsListener(app, ip, port, modelid, brigeid):
    logging.info('<MDNS> listener started')
    ip_version = IPVersion.V4Only
    zeroconf = Zeroconf(ip_version=ip_version)

    props = {
        'modelid': modelid,
        'bridgeid': brigeid
    }

    ctx = app.app_context()
    await ctx.push()
    try:
        info = ServiceInfo(
            "_hue._tcp.local.",
            "DIYHue-" + brigeid[-6:] + "._hue._tcp.local.",
            addresses=[socket.inet_aton(ip)],
            port=port,
            properties=props,
            server="DIYHue-" + brigeid + ".local."
        )
        zeroconf.register_service(info)
    finally:
        await ctx.pop()
