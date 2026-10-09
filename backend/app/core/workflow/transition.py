from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

GuardType = Callable[[Any, Any, Session], tuple[bool, str | None] | bool]
EffectType = Callable[[Any, Any, Session], None]


@dataclass
class Transition:
    from_state: str | list[str] | set[str] | tuple[str, ...]
    to_state: str
    permission: str | None = None
    guards: list[GuardType] = field(default_factory=list)
    effects: list[EffectType] = field(default_factory=list)
    description: str | None = None

    def matches(self, current_state: str | None, target_state: str) -> bool:
        if target_state != self.to_state:
            return False
        if self.from_state == "*":
            return True
        if isinstance(self.from_state, (list, set, tuple)):
            return current_state in self.from_state
        return current_state == self.from_state

    @property
    def source_states(self) -> set[str]:
        if self.from_state == "*":
            return {"*"}
        if isinstance(self.from_state, (list, set, tuple)):
            return set(self.from_state)
        return {str(self.from_state)}
