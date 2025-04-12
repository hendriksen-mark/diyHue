import logManager
from quart import Response, stream_with_context, Blueprint
import json
from time import sleep, time
import asyncio
import HueObjects

logging = logManager.logger.get_logger(__name__)
stream = Blueprint('stream', __name__)

def messageBroker():
    while True:
        if len(HueObjects.eventstream) > 0:
            for event in HueObjects.eventstream:
                logging.debug(event)
            sleep(0.3)  # ensure all devices connected receive the events
            HueObjects.eventstream = []
        sleep(0.2)

@stream.route('/eventstream/clip/v2')
async def streamV2Events():
    async def generate():
        counter = 1000
        yield f": hi\n\n"
        while counter > 0:
            if len(HueObjects.eventstream) > 0:
                for index, messages in enumerate(HueObjects.eventstream):
                    yield f"id: {int(time()) }:{index}\ndata: {json.dumps([messages], separators=(',', ':'))}\n\n"
                await asyncio.sleep(0.2)
            await asyncio.sleep(0.2)
            counter -= 1

    return Response(stream_with_context(generate()), mimetype='text/event-stream; charset=utf-8')
