from dataclasses import dataclass, field
from typing import Dict, Any

@dataclass
class Config:
    newLights: Dict[str, Any] = field(default_factory=dict)
    arg: Dict[str, Any] = field(default_factory=dict)

    def clear_new_lights(self) -> None:
        """
        Clear the new lights dictionary.

        Args:
            None

        Returns:
            None
        """
        self.newLights.clear()
