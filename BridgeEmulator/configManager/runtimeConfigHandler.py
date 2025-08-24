from dataclasses import dataclass, field
from typing import Any

@dataclass
class Config:
    newLights: dict[str, Any] = field(default_factory=dict)
    arg: dict[str, Any] = field(default_factory=dict)

    def clear_new_lights(self) -> None:
        """
        Clear the new lights dictionary.

        Args:
            None

        Returns:
            None
        """
        self.newLights.clear()
