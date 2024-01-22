
import asyncio
import logging
import threading
import weakref

from .action import Action


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
    application's stores. Defaults to "id"

    """
    _store_registry = {}
    _store_tasks = []
    _store_types = {}

    _store_asyncio_thread = None
    _store_asyncio_event_loop = None

    _store_logger = None
    _store_merged_attrs = []

    _next_saga_id = 1
    _next_reducer_id = 1
    _next_default_id = 1

    store_attrs = []

    STORE_INIT = "STORE_INIT"

    @classmethod
    def _setter_helper(cls, attr):
        def inner(self, newval, previous=None):
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

        all_store_attrs = [a for a in cls.__dict__.get('store_attrs', [])]
        for parent_cls in cls.mro():
            if 'store_attrs' in parent_cls.__dict__:
                for attr in parent_cls.__dict__['store_attrs']:
                    all_store_attrs.append(attr)

        cls._store_merged_attrs = all_store_attrs
        cls._store_sagas = []
        cls._store_reducers = {}

        for attr in cls._store_merged_attrs:
            setter_action = f"SET_{attr.upper()}"
            setter_methodname = f"_{setter_action}"
            setter_dispatch = cls._setter_helper(attr)

            getter_statename = f"{attr.upper()}"

            # define the name as a symbol
            setattr(cls, setter_action, setter_action)
            setattr(cls, getter_statename, attr)

            # define the setter as a method
            setattr(cls, setter_methodname, setter_dispatch)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        id_attr = getattr(self, "store_id_attr", None)
        if id_attr is None:
            id_attr = "id"
            id_value = Store._next_default_id
            Store._next_default_id += 1
            setattr(self, id_attr, id_value)

        type_name = type(self).store_type
        type_registry = Store._store_registry.get(type_name)
        if type_registry is None:
            Store.log(f"No store registry found for {type_name}, creating")
            type_registry = weakref.WeakValueDictionary()
            Store._store_registry[type_name] = type_registry

        type_registry[getattr(self, id_attr)] = self

        # STORE_INIT lets this new store get picked up
        # by the inspector
        self._launch_task(
            self.dispatch(
                Action(self, Store.STORE_INIT, {})
            )
        )

    def action(self, action_label, **kwargs):
        return Action(self, action_label, kwargs)

    def state(self, label=None):
        if not label:
            return {
                attr: getattr(self, attr)
                for attr in self._store_merged_attrs
            }
        return getattr(self, label)

    def description(self):
        """
        Return a short piece of text to describe the store
        Displayed in the inspector along with the ID, if implemented
        """
        return None

    async def dispatch(self, action, previous=None):
        """
        Dispatch an action to update the store's state
        """
        handlers = self._store_reducers.get(action.type_name, [])
        state_diff = {}

        for callback_id, state_name, cb in handlers:
            old_value = getattr(self, state_name)
            if previous:
                old_value = previous.get(state_name, old_value)
            new_value = cb(self, action, state_name, old_value)
            setattr(self, state_name, new_value)

            if old_value != new_value:
                state_diff[state_name] = (old_value, new_value)

        if not handlers:
            magic_handler_name = f"_{action.type_name}"
            if hasattr(type(self), magic_handler_name):
                magic_handler = getattr(self, magic_handler_name)
                new_value = action.payload.get("value", None)
                state_name, old_value = magic_handler(new_value, previous=previous)
                if old_value != new_value:
                    state_diff[state_name] = (old_value, new_value)

        # STORE_INIT is magic. This is dispatched when a new store
        # is created, and it needs a state diff that includes the initial
        # values of the whole state.
        if action.type_name == Store.STORE_INIT:
            initial_state = action.target.state()
            for key, value in initial_state.items():
                state_diff[key] = (None, value)

        changed_state_set = set(state_diff.keys())

        for callback_id, callback, state_filter in self._store_sagas:
            if state_filter and not (set(state_filter) & changed_state_set):
                continue
            self._launch_task(
                self._run_saga(
                    callback(self, action, state_diff)
                )
            )

    def _launch_task(self, task):
        # clean up completed tasks
        Store._store_tasks = [
            t for t in Store._store_tasks
            if t and not t.done()
        ]

        # launch the task, if needed
        if threading.get_ident() == Store._store_asyncio_thread:
            launched = asyncio.create_task(task)
        else:
            launched = asyncio.run_coroutine_threadsafe(
                task, Store._store_asyncio_loop
            )

        # save the new task for later cleanup
        Store._store_tasks.append(launched)

    async def _run_saga(self, saga):
        try:
            async for action in saga:
                if action and isinstance(action, Action):
                    await self.dispatch(action)
        except Exception as e:  # noqa
            Store.log(f"Exception in saga {saga}: {e}")

    # install reducer for states
    @classmethod
    def install_reducer(cls, action_name, states):

        reducer_id = Store._next_reducer_id
        Store._next_reducer_id += 1

        handlers = cls._store_reducers.setdefault(action_name, [])
        reducer = getattr(cls, f"_{action_name}")

        for state in states:
            handlers.append((reducer_id, state, reducer))
        return reducer_id

    @classmethod
    def uninstall_reducer(cls, action_name, reducer_id):
        handlers = cls._store_reducers.setdefault(action_name, [])
        handlers[:] = [
            h for h in handlers
            if h[0] != reducer_id
        ]

    @classmethod
    def install_saga(cls, saga, states=None):
        saga_id = Store._next_saga_id
        Store._next_saga_id += 1

        if not states:
            states = []

        cls._store_sagas.append((saga_id, saga, states))
        return saga_id

    @classmethod
    def uninstall_saga(cls, saga_id):
        cls._store_sagas = [
            h for h in cls._store_sagas
            if h[0] != saga_id
        ]

    @staticmethod
    def all_store_types():
        return Store._store_types.values()

    @staticmethod
    def all_stores():
        stores = []
        for typename, type_objects in Store._store_registry.items():
            stores = stores + list(type_objects.values())
        return stores

    @staticmethod
    def store():
        complete_state = {}
        for typename, type_objects in Store._store_registry.items():
            typereg = complete_state.setdefault(typename, {})
            for obj_id, obj in type_objects.items():
                typereg[obj_id] = obj.state()
        return complete_state

    @staticmethod
    def find_store(store_type, store_id):
        return Store._store_registry.get(store_type, {}).get(store_id, None)

    @staticmethod
    def show_inspector(event_loop=None):
        from .inspector.inspector import Inspector
        inspector = Inspector(event_loop=event_loop)
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
        Store._store_asyncio_loop = asyncio.get_event_loop()


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
