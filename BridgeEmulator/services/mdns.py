import socket
import time
from typing import Dict, List, Optional

from zeroconf import IPVersion, ServiceInfo, Zeroconf

import logManager

logging = logManager.logger.get_logger(__name__)

class MDNSListener:
    """
    A class to manage mDNS service registration and updates.
    """

    def __init__(self, ip: str, port: int, modelid: str, bridgeid: str, mac: str) -> None:
        """
        Initialize the MDNSListener with the given parameters.
        
        Args:
            ip: IP address of the service
            port: Port number of the service
            modelid: Model ID of the service
            bridgeid: Bridge ID of the service
            mac: MAC address of the service
        """
        self.ip: str = ip
        self.port: int = port
        self.modelid: str = modelid
        self.bridgeid: str = bridgeid
        self.mac: str = mac
        self.zeroconf: Optional[Zeroconf] = None
        self.info: Optional[ServiceInfo] = None
        self.running: bool = False

    def __enter__(self) -> 'MDNSListener':
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.stop()

    def start(self) -> None:
        """
        Start the mDNS listener and register the service.
        """
        logging.info('<MDNS> listener started')
        ip_version = IPVersion.V4Only
        self.zeroconf = Zeroconf(ip_version=ip_version)

        try:
            props: Dict[str, str] = {
                'modelid': self.modelid,
                'bridgeid': self.bridgeid
            }

            self.info = ServiceInfo(
                "_hue._tcp.local.",
                f"DIYHue Bridge - {self.bridgeid[-6:]}._hue._tcp.local.",
                addresses=[socket.inet_aton(self.ip)],
                port=self.port,
                properties=props,
                server=f"{self.mac}.local."
            )
            self.zeroconf.register_service(self.info)
            logging.info('<MDNS> service registered successfully')
            
            self.running = True
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            logging.info('<MDNS> listener stopped by user')
        except Exception as e:
            logging.error(f'<MDNS> failed to register service: {e}')
            self.stop()
            raise
        finally:
            if not self.running:
                self.stop()

    def stop(self) -> None:
        """
        Stop the mDNS listener and unregister the service.
        """
        if self.zeroconf and self.info:
            try:
                self.zeroconf.unregister_service(self.info)
            except Exception as e:
                logging.error(f'<MDNS> failed to unregister service: {e}')
            finally:
                self.zeroconf.close()
                logging.info('<MDNS> service unregistered and Zeroconf closed')
        self.running = False

    def update_properties(self, new_props: Dict[str, str]) -> None:
        """
        Update the properties of the registered mDNS service.
        
        Args:
            new_props: Dictionary of new properties to update
        """
        if self.info:
            self.info.properties.update(new_props)
            self.zeroconf.update_service(self.info)
            logging.info('<MDNS> service properties updated')

    def stop_listener(self) -> None:
        """
        Stop the mDNS listener from running.
        """
        self.running = False

    def is_running(self) -> bool:
        """
        Check if the mDNS listener is running.
        
        :return: True if the listener is running, False otherwise
        """
        return self.running

    def restart(self) -> None:
        """
        Restart the mDNS listener.
        """
        logging.info('<MDNS> restarting listener')
        self.stop()
        self.start()

    def graceful_shutdown(self) -> None:
        """
        Handle graceful shutdown of the mDNS listener.
        """
        logging.info('<MDNS> initiating graceful shutdown')
        self.stop_listener()
        self.stop()

    def discover_services(self, service_type: str) -> List[str]:
        """
        Discover available mDNS services of a given type.
        
        Args:
            service_type: The type of service to discover
        
        Returns:
            List of discovered service names
        """
        logging.info(f'<MDNS> discovering services of type: {service_type}')
        services = self.zeroconf.get_service_info(service_type)
        if services:
            return [service.name for service in services]
        else:
            logging.info(f'<MDNS> no services found for type: {service_type}')
            return []

def mdnsListener(ip: str, port: int, modelid: str, bridgeid: str, mac: str) -> None:
    """
    Function to start the mDNS listener with the given parameters.
    
    Args:
        ip: IP address of the service
        port: Port number of the service
        modelid: Model ID of the service
        bridgeid: Bridge ID of the service
        mac: MAC address of the service
    """
    listener = MDNSListener(ip, port, modelid, bridgeid, mac)
    try:
        listener.start()
    except Exception as e:
        logging.error(f'<MDNS> listener encountered an error: {e}')
        listener.graceful_shutdown()
