"""
store.py -- Store base class

When a type inherits from Store, an instance of that class is a
store of state of that type. This means that in a running app there
may be mAny stores of different types.
"""
from __future__ import annotations
import asyncio
import inspect
import logging
import threading
import weakref
from datetime import datetime
from typing import Awaitable, Callable, Coroutine, Any, AsyncGenerator, AsyncIterator, Dict, List, TYPE_CHECKING
from concurrent.futures import Future
from .action import Action


if TYPE_CHECKING:
    from .saga import SagaMethod
    from .inspector.inspector import Inspector

type StoreTaskAwaitable = None|asyncio.Task[None]|Future[Any]

class Store:
    """
    Base class for stores of managed state

    Class attributes configure behavior:

    store_attrs: array of store attribute names. Each one
    will get an automatic class attribute and setter action.
    if the attr is "my_attr" in class MyStore, there will be
    a MyStore.MY_ATTR which is the string "my_attr", and
    an action type MyStore.SET_MY_ATTR with an automatic
    reducer.

    store_type: the type name for the store to be used
    when aggregating the application's stores. Defaults
    to the class __name__

    store_id_attr: the attribute to use as a type-unique
    id for the store, to be used when aggregating the
    application's stores. Defaults to "id". If no attr
    is provided and no "id" exists, "id" will be created.
    """

    _store_registry: Dict[str, Dict[str, Store]] = {}
    _store_tasks: List[StoreTaskAwaitable]  = []
    _store_types: Dict[str, type] = {}

    _store_sagas: List[tuple] = []
    _store_reducers: Dict[str, List[tuple]] = {}
    _store_subclass_initialized = False

    _store_asyncio_thread = None
    _store_asyncio_event_loop = None
    _store_activity_timestamp: datetime | None = None

    _store_logger = None
    _store_merged_attrs: List[str] = []

    _next_saga_id = 1
    _next_reducer_id = 1
    _next_default_id = 1

    store_attrs: List[str] = []
    store_type: str|None = None

    STORE_INIT = "STORE_INIT"
    STORE_DELETE = "STORE_DELETE"

    @classmethod
    def _setter_helper(cls, attr: str) -> Callable:
        def inner(self, newval: Any, previous: None | dict = None):
            oldval = getattr(self, attr)
            if previous:
                oldval = previous.get(attr, oldval)
            setattr(self, attr, newval)
            return (attr, oldval)
        return inner

    def __init_subclass__(cls):
        if "store_type" not in cls.__dict__:
            cls.store_type = cls.__name__

        Store._store_registry[cls.store_type] = weakref.WeakValueDictionary()
        if cls.store_type not in Store._store_types:
            Store._store_types[cls.store_type] = cls

        all_store_attrs = list(cls.__dict__.get('store_attrs', []))
        for parent_cls in cls.mro():
            if 'store_attrs' in parent_cls.__dict__:
                for attr in parent_cls.__dict__['store_attrs']:
                    all_store_attrs.append(attr)

        cls._store_merged_attrs = all_store_attrs
        if not cls._store_sagas:
            cls._store_sagas = []
        if not cls._store_reducers:
            cls._store_reducers = {}

        for attr in cls._store_merged_attrs:
            setter_action = f"SET_{attr.upper()}"
            setter_methodname = f"_{setter_action}"
            setter_dispatch = cls._setter_helper(attr)

            getter_statename = f"{attr.upper()}"

            # define the name as a symbol
            if not hasattr(cls, setter_action):
                setattr(cls, setter_action, setter_action)

            if not hasattr(cls, getter_statename):
                setattr(cls, getter_statename, attr)

            # define the setter as a method
            if not hasattr(cls, setter_methodname):
                setattr(cls, setter_methodname, setter_dispatch)
        Store._store_activity_timestamp = datetime.now()

    def __init__(self, *args, **kwargs):
        store_type = type(self)
        id_attr = getattr(self, "store_id_attr", None)
        if "id" in kwargs:
            id_value = kwargs.get("id")
        else:
            id_value = Store._next_default_id
            Store._next_default_id += 1

        if id_attr is None:
            id_attr = "id"

        setattr(self, id_attr, id_value)

        type_name = type(self).store_type
        type_registry = Store._store_registry.get(type_name)
        if type_registry is None:
            type_registry = weakref.WeakValueDictionary()
            Store._store_registry[type_name] = type_registry

        type_registry[str(getattr(self, id_attr))] = self

        # reducers and sagas can be defined up the MRO. Combine
        # them.
        all_reducers = {}
        all_sagas = []

        for base_cls in type(self).mro():
            if issubclass(base_cls, Store):
                all_reducers.update({**base_cls._store_reducers})
                all_sagas.extend([*base_cls._store_sagas])

        self._state_changes_pending = False
        store_type._store_reducers = all_reducers
        store_type._store_sagas = all_sagas
        Store._store_activity_timestamp = datetime.now()

        # STORE_INIT lets this new store get picked up
        # by the inspector
        self._launch_task(
            self.dispatch(
                Action(self, Store.STORE_INIT, kwargs)
            )
        )

    async def delete(self, **payload: Any) -> None:
        store_id = str(getattr(self, getattr(self, "store_id_attr", "id")))
        if store_id is not None:
            type_name = type(self).store_type
            if type_name is None:
                return
            type_registry = Store._store_registry.get(type_name)
            if type_registry is not None and store_id in type_registry:
                del type_registry[store_id]

            await self.dispatch(
                Action(
                    self, Store.STORE_DELETE, {
                        "state_diff": {
                            k: (v, None) for k, v in self.state().items()
                        },
                        **payload
                    }
                )
            )

    def store_id(self) -> str:
        obj_id = getattr(self, getattr(self, "store_id_attr", "id"))
        return f"{self.store_type}:{obj_id}"

    def action(self, action_label: str, **payload: Any) -> Action:
        return Action(self, action_label, payload)

    def state(self, label: None|str = None) -> Any:
        if not label:
            return {
                attr: getattr(self, attr)
                for attr in self._store_merged_attrs
            }
        return getattr(self, label)

    def description(self) -> str:
        """
        Return a short piece of text to describe the store
        Displayed in the inspector along with the ID, if implemented
        """
        return ""

    async def dispatch_setter(self, param_name, newvalue) -> None:
        """
        Shortcut to set a state element to a value
        """
        action = Action(
            self,
            f'SET_{param_name.upper()}',
            dict(value=newvalue)
        )
        await self.dispatch(action)

    async def dispatch(self, action, previous=None) -> None:
        """
        Dispatch an action to update the store's state
        """
        handlers = self._store_reducers.get(action.type_name, [])
        state_diff = {}
        for _, state_name, cb in handlers:
            old_value = getattr(self, state_name)
            if previous:
                old_value = previous.get(state_name, old_value)
            new_value = cb(self, action, state_name, old_value)
            setattr(self, state_name, new_value)

            if old_value != new_value:
                state_diff[state_name] = (old_value, new_value)

        if not handlers:
            auto_handler_name = f"_{action.type_name}"
            if hasattr(type(self), auto_handler_name):
                auto_handler = getattr(self, auto_handler_name)
                new_value = action.payload.get("value", None)
                state_name, old_value = auto_handler(new_value, previous=previous)
                if old_value != new_value:
                    state_diff[state_name] = (old_value, new_value)

        # STORE_INIT is dispatched when a new store is created,
        # and it needs a state diff that includes the initial
        # values of the whole state.
        if action.type_name == Store.STORE_INIT:
            initial_state = action.target.state()
            for key, value in initial_state.items():
                state_diff[key] = (None, value)

        changed_state_set = set(state_diff.keys())

        for _, callback, state_filter, on_store_init in self._store_sagas:
            if action.type_name == Store.STORE_INIT and not on_store_init:
                continue
            if state_filter and not set(state_filter) & changed_state_set:
                continue
            callback_res = callback(self, action, state_diff, previous)
            if (
                inspect.isasyncgen(callback_res)
                or inspect.isawaitable(callback_res)
            ):
                self._launch_task(
                    self._run_saga(callback_res)
                )
        Store._store_activity_timestamp = datetime.now()

    def _launch_task(self, task: Coroutine[Any, Any, Any]) -> None:
        # clean up completed tasks
        Store._store_tasks = [
            t for t in Store._store_tasks
            if t and not t.done()
        ]

        # launch the task, if needed
        launched: StoreTaskAwaitable = None
        if threading.get_ident() == Store._store_asyncio_thread:
            launched = asyncio.create_task(task)
        elif Store._store_asyncio_event_loop:
            launched = asyncio.run_coroutine_threadsafe(
                task, Store._store_asyncio_event_loop
            )
        else:
            return

        # save the new task for later cleanup
        Store._store_tasks.append(launched)

    @staticmethod
    async def drain_tasks():
        while(Store._store_tasks):
            await Store._store_tasks[0]

            Store._store_tasks = [
                t for t in Store._store_tasks
                if t and not t.done()
            ]


    async def _run_saga(self, saga: Any) -> None:
        try:
            if inspect.isasyncgen(saga):
                async for action in saga:
                    if action and isinstance(action, Action):
                        await action.target.dispatch(action)
            elif inspect.isawaitable(saga):
                action = await saga
                if action and isinstance(action, Action):
                    await action.target.dispatch(action)
        except Exception as e:  # noqa
            import traceback
            Store.log(f"Exception in saga {saga}: {e}")
            for l in traceback.format_exception(e):
                Store.log(l)

    # install reducer for states
    @classmethod
    def install_reducer(cls, action_name: str, states: List[str]) -> int:
        reducer_id = Store._next_reducer_id
        Store._next_reducer_id += 1

        handlers = cls._store_reducers.setdefault(action_name, [])
        reducer = getattr(cls, f"_{action_name}")

        for state in states:
            handlers.append((reducer_id, state, reducer))
        return reducer_id

    @classmethod
    def uninstall_reducer(cls, action_name: str, reducer_id: int) -> None:
        handlers = cls._store_reducers.setdefault(action_name, [])
        handlers[:] = [
            h for h in handlers
            if h[0] != reducer_id
        ]

    @classmethod
    def install_saga(cls, saga: SagaMethod, states: None | List[str]=None, on_store_init: bool=False):
        saga_id = Store._next_saga_id
        Store._next_saga_id += 1

        if not states:
            states = []

        cls._store_sagas.append((saga_id, saga, states, on_store_init))

        # if a saga is added dynamically -- as for the inspector -- need to
        # manually patch up the existing stores
        if not cls.store_type:
            raise ValueError("No store type set")

        type_registry = Store._store_registry[cls.store_type]
        for _, store_obj in type_registry.items():
            store_obj._store_sagas.append(
                (saga_id, saga, states, on_store_init)
            )

        return saga_id

    @classmethod
    def uninstall_saga(cls, saga_id: int) -> None:
        cls._store_sagas = [
            h for h in cls._store_sagas
            if h[0] != saga_id
        ]

    @classmethod
    def last_activity_time(cls) -> datetime:
        return cls._store_activity_timestamp or datetime.now()

    @staticmethod
    def all_store_types() -> List[type]:
        return list(Store._store_types.values())

    @staticmethod
    def all_stores() -> List[Store]:
        stores: List[Store] = []
        for typename, type_objects in Store._store_registry.items():
            stores = stores + list(type_objects.values())
        return stores

    @staticmethod
    def store() -> Dict[str, Any]:
        complete_state: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for typename, type_objects in Store._store_registry.items():
            typereg = complete_state.setdefault(typename, {})
            for obj_id, obj in type_objects.items():
                typereg[obj_id] = obj.state()
        return complete_state

    @staticmethod
    def find_store(store_type: str, store_id: str|None=None) -> Store|None:
        if store_id is None:
            store_type, store_id = store_type.split(':')
        return Store._store_registry.get(store_type, {}).get(store_id, None)

    @staticmethod
    def show_inspector(event_loop=None) -> Inspector:
        from .inspector.inspector import Inspector
        inspector = Inspector(
            event_loop=event_loop,
        )
        inspector.start()
        return inspector

    @staticmethod
    def log(*args):
        if not Store._store_logger:
            Store._store_logger = logging.getLogger(__name__)
        Store._store_logger.error(*args)

    @staticmethod
    def setup_asyncio():
        Store._store_asyncio_thread = threading.get_ident()
        Store._store_asyncio_event_loop = asyncio.get_event_loop()

    @staticmethod
    def flush_registry():
        Store._store_types = {}
        Store._store_registry = {}


class SyncedStore (Store):
    """
    A type of store with convenience actions for syncing
    with a remote source of truth.

    In addition to the normal setters, attr "my_attr" will
    also have a secondary setter action called
    MyStore.SYNC_MY_ATTR. This behaves like the setter in
    every way, except for the action type.

    This can be useful if you have an after_dispatch handler
    that pushes state to the remote source of truth. If the
    action is a SYNC_* one, you know you are receiving
    a state update so you don't need to push it.
    """
    def __init_subclass__(cls):
        super().__init_subclass__()

        if not hasattr(cls, 'store_attrs'):
            return

        for attr in cls.store_attrs:
            setter_action = f"SYNC_{attr.upper()}"
            setter_methodname = f"_{setter_action}"
            setter_dispatch = cls._setter_helper(attr)

            # define the name as a symbol
            setattr(cls, setter_action, setter_action)

            # define the setter as a method
            setattr(cls, setter_methodname, setter_dispatch)
