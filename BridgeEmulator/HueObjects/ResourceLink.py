import logManager
from typing import List, Any
from HueObjects import ApiUser

logging = logManager.logger.get_logger(__name__)

class ResourceLink:
    def __init__(self, data: dict[str, Any]) -> None:
        self.name: str = data["name"]
        self.id_v1: str = data["id_v1"]
        self.classid: int = data["classid"]
        self.description: str = data.get("description", "")
        self.links: List[str] = data.get("links", [])
        self.owner: ApiUser.ApiUser = data["owner"]
        self.recycle: bool = data.get("recycle", False)

    def __del__(self) -> None:
        logging.info(self.name + " ResourceLink was destroyed.")

    def add_link(self, link: Any) -> None:
        self.links.append("/" + link.getObjectPath()["resource"] + "/" + link.getObjectPath()["id"])

    def getObjectPath(self) -> dict[str, str]:
        return {"resource": "resourcelinks", "id": self.id_v1}

    def getV1Api(self) -> dict[str, Any]:
        result = {
            "name": self.name,
            "description": self.description,
            "type": "Link",
            "classid": self.classid,
            "owner": self.owner.username if hasattr(self.owner, 'username') else None,
            "recycle": self.recycle,
            "links": self.links
        }
        return result

    def update_attr(self, newdata: dict[str, Any]) -> None:
        for key, value in newdata.items():
            if hasattr(self, key):
                updateAttribute = getattr(self, key)
                if isinstance(updateAttribute, dict):
                    updateAttribute.update(value)
                    setattr(self, key, updateAttribute)
                else:
                    setattr(self, key, value)
            else:
                logging.warning(f"Attempted to update non-existent attribute {key} for ResourceLink {self.name}")

    def save(self) -> dict[str, Any]:
        return self.getV1Api()
