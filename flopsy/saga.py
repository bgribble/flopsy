"""
saga.py -- @saga decorator

Sagas are async generators that are started up after
reducers are dispatched for an action and the store's
state is updated. They yeild Actions and can run
indefinitely, similar to RxJS "epics"
"""

from __future__ import annotations
from typing import Callable, Awaitable, List, Dict, AsyncIterator, AsyncGenerator, Any, TYPE_CHECKING
from .action import Action

if TYPE_CHECKING:
    from .store import Store

type SagaMethod = Callable[[Action, Dict[str, Any], Dict[str, Any]], AsyncGenerator[Action]]

class saga:
    """
    class to be used as a decorator for saga methods.
    the name of the method is used as the saga name, and the
    method is reassigned to a new name with a preceding _

    @saga
    async def my_saga(self, action, state_diff):
        # this is a saga that runs after all dispatchers
        # for "action". It should be an async generator --
        # that is, an async function that uses yield to
        # return a sequence of values, or None.
        yield None

    if the decorator has args, they are interpreted as the state
    elements that are connected to the saga. The saga will only
    be run after an action that affects the named state items. If
    there are no args it will get run after any action.
    """
    def __init__(self, *args: SagaMethod | str, **kwargs: Any):
        self.owning_class: Store|None = None
        self.func: SagaMethod|None = None
        self.states: List[str]|None = None
        self.action_name: str|None = None
        self.method_name: str|None = None
        self.on_store_init: bool = kwargs.get("on_init", False)

        # if no args to @reducer
        if len(args) == 1 and callable(args[0]):
            self._assign_func(args[0])
        else:
            self.states = [str(a) for a in args]

    def __call__(self, *args, **kwargs):
        if len(args) == 1 and callable(args[0]):
            self._assign_func(args[0])
            return self
        else:
            return self.func(*args, **kwargs)

    def _assign_func(self, func: SagaMethod):
        self.func = func
        self.action_name = func.__name__.upper()
        self.method_name = '_' + self.action_name

    # __set_name__ gets called because @saga is a "descriptor",
    # at the right time in the init process.
    def __set_name__(self, owner: Store, name: str):
        from .store import Store

        self.owning_class = owner
        if self.method_name is None or self.action_name is None:
            return

        setattr(owner, self.method_name, self.func)
        setattr(owner, self.action_name, self.action_name)

        # __set_name__ is called before the parent
        # __init_subclass__ so these class attributes might not
        # be defined yet
        if '_next_saga_id' not in self.owning_class.__dict__:
            self.owning_class._next_saga_id = 1
        if '_store_sagas' not in self.owning_class.__dict__:
            self.owning_class._store_sagas = []

        saga_id = self.owning_class._next_saga_id
        self.owning_class._next_saga_id += 1
        saga_handler: SagaMethod = self

        self.owning_class._store_sagas.append((saga_id, self, self.states, self.on_store_init))

