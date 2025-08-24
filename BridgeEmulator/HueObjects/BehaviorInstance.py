import uuid
import logManager
from HueObjects import genV2Uuid, StreamEvent
from datetime import datetime, timezone
from typing import Any, Optional

logging = logManager.logger.get_logger(__name__)

class BehaviorInstance:
    def __init__(self, data: dict[str, Any]) -> None:
        self.id_v2: str = data.get("id", genV2Uuid())
        self.id_v1: str = self.id_v2  # used for config save
        self.name: Optional[str] = data["metadata"].get("name")
        self.meta_type: Optional[str] = data["metadata"].get("type")
        self.configuration: dict[str, Any] = data["configuration"]
        self.enabled: bool = data.get("enabled", False)
        self.active: bool = data.get("active", False)
        self.script_id: str = data.get("script_id", "")

        self._send_stream_event(self.getV2Api(), "add")

    def __del__(self) -> None:
        self._send_stream_event({"id": self.id_v2, "type": "behavior_instance"}, "delete")
        logging.info(f"{self.name} behaviour instance was destroyed.")

    def activate(self, data: dict[str, Any]) -> None:
        if "recall" in data and data["recall"].get("action") == "deactive":
            self.active = False

    def getV2Api(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "configuration": self.configuration,
            "dependees": [],
            "enabled": self.enabled,
            "id": self.id_v2,
            "last_error": "",
            "metadata": {
                "name": self.name or "noname",
                "type": self.meta_type or "notype"
            },
            "script_id": self.script_id,
            "status": "running" if self.enabled else "disabled",
            "type": "behavior_instance"
        }

        if "where" in self.configuration:
            for resource in self.configuration["where"]:
                resource_key = list(resource.keys())[0]
                result["dependees"].append({
                    "level": "critical",
                    "target": {
                        "rid": resource[resource_key]["rid"],
                        "rtype": resource[resource_key]["rtype"]
                    },
                    "type": "ResourceDependee"
                })

        return result

    def update_attr(self, newdata: dict[str, Any]) -> None:
        for key, value in newdata.items():
            if key == "metadata" and "name" in value:
                self.name = value["name"]
                continue
            updateAttribute = getattr(self, key)
            if isinstance(updateAttribute, dict):
                updateAttribute.update(value)
                setattr(self, key, updateAttribute)
            else:
                setattr(self, key, value)
        self._send_stream_event(self.getV2Api(), "update")

    def _send_stream_event(self, data: dict[str, Any], event_type: str) -> None:
        streamMessage = {
            "creationtime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "data": [data],
            "id": str(uuid.uuid4()),
            "type": event_type,
        }
        StreamEvent(streamMessage)

    def save(self) -> dict[str, Any]:
        return {
            "id": self.id_v2,
            "metadata": {"name": self.name},
            "configuration": self.configuration,
            "enabled": self.enabled,
            "active": self.active,
            "script_id": self.script_id
        }
