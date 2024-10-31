
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
        # return a sequence of values.
        pass

    if the decorator has args, they are interpreted as the state
    elements that are connected to the saga. The saga will only
    be run after an action that affects the named state items. If
    there are no args it will get run after any action.
    """
    def __init__(self, *args, **kwargs):
        self.owning_class = None
        self.func = None
        self.states = None
        self.action_name = None
        self.method_name = None
        self.on_store_init = kwargs.get("on_init", False)

        # if no args to @reducer
        if len(args) == 1 and callable(args[0]):
            self._assign_func(args[0])
        else:
            self.states = args

    def __call__(self, *args, **kwargs):
        if len(args) == 1 and callable(args[0]):
            self._assign_func(args[0])
            return self
        else:
            return self.func(*args, **kwargs)

    def _assign_func(self, func):
        self.func = func
        self.action_name = func.__name__.upper()
        self.method_name = '_' + self.action_name

    # __set_name__ gets called because @saga is a "descriptor",
    # at the right time in the init process.
    def __set_name__(self, owner, name):
        from .store import Store

        self.owning_class = owner
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
        self.owning_class._store_sagas.append((saga_id, self, self.states, self.on_store_init))

