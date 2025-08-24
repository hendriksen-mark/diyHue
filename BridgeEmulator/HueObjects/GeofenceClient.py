import uuid
import logManager
from datetime import datetime, timezone
from HueObjects import genV2Uuid, StreamEvent
from typing import Any, Optional

logging = logManager.logger.get_logger(__name__)

class GeofenceClient:
    def __init__(self, data: dict[str, Any]) -> None:
        self.name: str = data.get('name', f'Geofence {data.get("id_v1")}')
        self.id_v2: str = data["id_v2"] if "id_v2" in data else genV2Uuid()
        self.is_at_home: bool = data.get('is_at_home', False)
        self.id_v1: Optional[str] = data.get("id_v1")

        self._send_stream_event(self.getV2GeofenceClient(), "add")

    def __del__(self) -> None:
        self._send_stream_event({"id": self.id_v2, "type": "geofence_client"}, "delete")
        logging.info(f"{self.name} geofence client was destroyed.")

    def update_attr(self, newdata: dict[str, Any]) -> None:
        for key, value in newdata.items():
            if hasattr(self, key):
                updateAttribute = getattr(self, key)
                if isinstance(updateAttribute, dict):
                    updateAttribute.update(value)
                    setattr(self, key, updateAttribute)
                else:
                    setattr(self, key, value)

        self._send_stream_event(self.getV2GeofenceClient(), "update")

    def _send_stream_event(self, data: dict[str, Any], event_type: str) -> None:
        streamMessage = {
            "creationtime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data": [data],
            "id": str(uuid.uuid4()),
            "type": event_type,
        }
        StreamEvent(streamMessage)

    def getV2GeofenceClient(self) -> dict[str, str]:
        return {
            "id": str(uuid.uuid5(uuid.NAMESPACE_URL, self.id_v2 + 'geofence_client')),
            "name": self.name,
            "type": "geofence_client"
        }
