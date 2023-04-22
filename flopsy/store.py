
import asyncio
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
    _store_reducers = {}
    _store_sagas = []
    _store_tasks = []

    _next_saga_id = 1
    _next_reducer_id = 1

    @classmethod
    def _setter_helper(cls, attr):
        def inner(self, newval):
            oldval = getattr(self, attr)
            setattr(self, attr, newval)
            return (attr, oldval)
        return inner

    def __init_subclass__(cls):
        if not hasattr(cls, 'store_attrs'):
            return

        Store._store_registry[cls.__name__] = {}

        for attr in cls.store_attrs:
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
        id_attr = getattr(self, "store_id_attr", "id")
        Store._store_registry[type(self).__name__][getattr(self, id_attr)] = self

    def action(self, action_label, **kwargs):
        return Action(self, action_label, kwargs)

    def state(self, label=None):
        if not label:
            return {
                attr: getattr(self, attr)
                for attr in self.store_attrs
            }
        return getattr(self, label)

    async def dispatch(self, action):
        handlers = self._store_reducers.get(action.type_name, [])
        state_diff = {}
        for callback_id, state_name, cb in handlers:
            old_value = getattr(self, state_name)
            new_value = cb(self, action, state_name, old_value)
            setattr(self, state_name, new_value)
            if old_value != new_value:
                state_diff[state_name] = (old_value, new_value)

        if not handlers:
            magic_handler_name = f"_{action.type_name}"
            if hasattr(type(self), magic_handler_name):
                magic_handler = getattr(self, magic_handler_name)
                new_value = action.payload.get("value", None)
                state_name, old_value = magic_handler(new_value)
                if old_value != new_value:
                    state_diff[state_name] = (old_value, new_value)

        changed_state_set = set(state_diff.keys())
        if not changed_state_set:
            return

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

        # save the new one
        Store._store_tasks.append(asyncio.create_task(task))

    async def _run_saga(self, saga):
        async for action in saga:
            if action and isinstance(action, Action):
                await self.dispatch(action)

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
        stores = []
        for typename, type_objects in Store._store_registry.items():
            if len(type_objects):
                stores.append(type(next(iter(type_objects.values()))))
        return stores

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
    def show_inspector():
        from .inspector.inspector import Inspector
        inspector = Inspector()
        inspector.start()
        return inspector

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
