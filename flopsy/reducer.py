
class reducer:
    """
    class to be used as a decorator for reducer methods.
    the name of the method is used as the action name, and the
    method is reassigned to a new name with a preceding _

    @reducer
    def MY_ACTION(self, action, state, previous_value):
        # this is a reducer for MY_ACTION, the method is now
        # present on cls._MY_ACTION(), cls.MY_ACTION is now
        # the string "MY_ACTION" (the action type name)
        pass

    if the reducer has args, they are interpreted as the
    state elements to run this reducer for. If there are
    no args it will get run for any state change.
    """
    def __init__(self, *args):
        self.owning_class = None
        self.func = None
        self.states = None
        self.action_name = None
        self.method_name = None

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

    # __set_name__ gets called because @reducer is a "descriptor",
    # at the right time in the init process
    def __set_name__(self, owner, name):
        self.owning_class = owner
        setattr(owner, self.method_name, self.func)
        setattr(owner, self.action_name, self.action_name)

        handlers = owner._store_reducers.setdefault(self.action_name, [])

        if self.states is None:
            self.states = self.owning_class.store_attrs

        reducer_id = self.owning_class._next_reducer_id
        self.owning_class._next_reducer_id += 1
        for state in self.states:
            handlers.append((reducer_id, state, self))
