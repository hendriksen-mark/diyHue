import logManager
import asyncio
from functions.colors import convert_xy
from typing import Any, Optional

logging = logManager.logger.get_logger(__name__)
Connections = {}

loop = asyncio.new_event_loop()
asyncio.set_event_loop(loop)

### libhueble ###
### https://github.com/alexhorn/libhueble/ ###
from bleak import BleakClient
from rgbxy import Converter, GamutC, get_light_gamut
from struct import pack, unpack

# model number as an ASCII string
CHAR_MODEL = '00002a24-0000-1000-8000-00805f9b34fb'
# power state (0 or 1)
CHAR_POWER = '932c32bd-0002-47a2-835a-a8d455b859dd'
# brightness (1 to 254)
CHAR_BRIGHTNESS = '932c32bd-0003-47a2-835a-a8d455b859dd'
# color (CIE XY coordinates converted to two 16-bit little-endian integers)
CHAR_COLOR = '932c32bd-0005-47a2-835a-a8d455b859dd'

class Lamp(object):
    """A wrapper for the Philips Hue BLE protocol"""

    def __init__(self, address: str) -> None:
        self.address = address
        self.client: Optional[BleakClient] = None

    def _require_client(self) -> BleakClient:
        if self.client is None:
            raise RuntimeError("BLE client is not connected")
        return self.client

    @property
    def is_connected(self) -> bool:
        return bool(self.client and self.client.is_connected)

    async def connect(self) -> None:
        # reinitialize BleakClient for every connection to avoid errors
        self.client = BleakClient(self.address)
        await self.client.connect()

        model = await self.get_model()
        try:
            self.converter = Converter(get_light_gamut(model))
        except ValueError:
            self.converter = Converter(GamutC)

    async def disconnect(self) -> None:
        if self.client is None:
            return
        await self.client.disconnect()
        self.client = None

    async def get_model(self) -> str:
        """Returns the model string"""
        client = self._require_client()
        model = await client.read_gatt_char(CHAR_MODEL)
        return model.decode('ascii')

    async def get_power(self) -> bool:
        """Gets the current power state"""
        client = self._require_client()
        power = await client.read_gatt_char(CHAR_POWER)
        return bool(power[0])

    async def set_power(self, on: bool) -> None:
        """Sets the power state"""
        client = self._require_client()
        await client.write_gatt_char(CHAR_POWER, bytes([1 if on else 0]), response=True)

    async def get_brightness(self) -> float:
        """Gets the current brightness as a float between 0.0 and 1.0"""
        client = self._require_client()
        brightness = await client.read_gatt_char(CHAR_BRIGHTNESS)
        return brightness[0] / 255

    async def set_brightness(self, brightness: float) -> None:
        """Sets the brightness from a float between 0.0 and 1.0"""
        client = self._require_client()
        await client.write_gatt_char(CHAR_BRIGHTNESS, bytes([max(min(int(brightness * 255), 254), 1)]), response=True)

    async def get_color_xy(self) -> tuple[float, float]:
        """Gets the current XY color coordinates as floats between 0.0 and 1.0"""
        client = self._require_client()
        buf = await client.read_gatt_char(CHAR_COLOR)
        x, y = unpack('<HH', buf)
        return x / 0xFFFF, y / 0xFFFF

    async def set_color_xy(self, x: float, y: float) -> None:
        """Sets the XY color coordinates from floats between 0.0 and 1.0"""
        client = self._require_client()
        buf = pack('<HH', int(x * 0xFFFF), int(y * 0xFFFF))
        await client.write_gatt_char(CHAR_COLOR, buf, response=True)

    async def get_color_rgb(self) -> tuple[float, float, float]:
        """Gets the RGB color as floats between 0.0 and 1.0"""
        x, y = await self.get_color_xy()
        return self.converter.xy_to_rgb(x, y)

    async def set_color_rgb(self, r: float, g: float, b: float) -> None:
        """Sets the RGB color from floats between 0.0 and 1.0"""
        x, y = self.converter.rgb_to_xy(r, g, b)
        await self.set_color_xy(x, y)

async def connect(light, reconnect=False) -> Lamp:
    ip = light.protocol_cfg["ip"]
    if ip in Connections and not reconnect:
        c = Connections[ip]
    else:
        c = Lamp(ip)
        await c.connect()
        Connections[ip] = c
    return c

async def set_light_async(light, data: dict[str, Any], retry=False) -> None:
    c = await connect(light)
    try:
        for key, value in data.items():
            if key == "on":
                await c.set_power(value)
            if key == "bri":
                await c.set_brightness(value / 254)
            if key == "xy":
                # not all models support color
                try:
                    color = convert_xy(value[0], value[1], light.state["bri"])
                    await c.set_color_rgb(color[0] / 254, color[1] / 254, color[2] / 254)
                except Exception as e:
                    logging.debug(e)
    except:
        # reconnect and try again once
        await connect(light, reconnect=True)
        if not retry:
            await set_light_async(light, data, retry=True)

def set_light(light, data: dict[str, Any]) -> None:
    loop.run_until_complete(set_light_async(light, data))

def get_light_state(light) -> dict[str, Any]:
    return {}

def discover(detectedLights: list, credentials: dict[str, Any]) -> dict[str, Any]:
    return {}
