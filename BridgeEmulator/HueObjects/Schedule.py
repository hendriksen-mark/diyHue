import logManager
from datetime import datetime, timezone
from typing import Any, Optional

logging = logManager.logger.get_logger(__name__)

class Schedule:
    def __init__(self, data: dict[str, Any]) -> None:
        self.name: str = data.get("name", "schedule " + data["id_v1"])
        self.id_v1: str = data["id_v1"]
        self.description: str = data.get("description", "none")
        self.command: dict[str, Any] = data.get("command", {})
        self.localtime: Optional[str] = data.get("localtime")
        self.created: str = data.get("created", datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S"))
        self.status: str = data.get("status", "disabled")
        self.autodelete: bool = data.get("autodelete", False)
        starttime: Optional[str] = None
        if self.localtime and (self.localtime.startswith("PT") or self.localtime.startswith("R")):
            starttime = self.created
        self.starttime: Optional[str] = data.get("starttime", starttime)
        self.recycle: bool = data.get("recycle", False)

    def __del__(self) -> None:
        logging.info(self.name + " schedule was destroyed.")

    def getV1Api(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        result["name"] = self.name
        result["description"] = self.description
        result["command"] = self.command
        if self.localtime is not None:
            result["localtime"] = self.localtime
            result["time"] = self.localtime
        result["created"] = self.created
        result["status"] = self.status
        if self.localtime and not self.localtime.startswith("W"):
            result["autodelete"] = self.autodelete
        if self.starttime is not None:
            result["starttime"] = self.starttime
        result["recycle"] = self.recycle
        return result

    def update_attr(self, newdata: dict[str, Any]) -> None:
        for key, value in newdata.items():
            updateAttribute = getattr(self, key)
            if isinstance(updateAttribute, dict):
                updateAttribute.update(value)
                setattr(self, key, updateAttribute)
            else:
                setattr(self, key, value)
            if key == "status" and value == "enabled":
                logging.debug("enable timer " + self.name)
                self.starttime = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    def getObjectPath(self) -> dict[str, str]:
        return {"resource": "schedules", "id": self.id_v1}

    def save(self) -> dict[str, Any]:
        return self.getV1Api()
