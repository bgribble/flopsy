"""
action.py -- the Action type
"""

from __future__ import annotations
from typing import TYPE_CHECKING, Dict, Any

if TYPE_CHECKING:
    from .store import Store


class Action:
    """
    Actions change the state of the target when processed by a reducer
    """
    def __init__(self, target: Store, type_name: str, payload: Dict[str, Any]):
        self.target = target
        self.type_name = type_name
        self.payload = payload

    def __str__(self) -> str:
        return f"<Action {self.type_name} {self.payload}>"

    def __repr__(self) -> str:
        return f"<Action {self.type_name} {self.payload}>"

    def dispatch(self):
        return self.target.dispatch(self)
